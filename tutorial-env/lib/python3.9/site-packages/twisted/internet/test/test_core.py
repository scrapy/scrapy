# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorCore}.
"""


import signal
import time
from types import FrameType
from typing import Callable, List, Optional, Tuple, Union, cast

from twisted.internet.abstract import FileDescriptor
from twisted.internet.defer import Deferred
from twisted.internet.error import ReactorAlreadyRunning, ReactorNotRestartable
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase


class SystemEventTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{IReactorCore.addSystemEventTrigger}
    and L{IReactorCore.fireSystemEvent}.
    """

    def test_stopWhenNotStarted(self) -> None:
        """
        C{reactor.stop()} raises L{RuntimeError} when called when the reactor
        has not been started.
        """
        reactor = self.buildReactor()
        cast(SynchronousTestCase, self).assertRaises(RuntimeError, reactor.stop)

    def test_stopWhenAlreadyStopped(self) -> None:
        """
        C{reactor.stop()} raises L{RuntimeError} when called after the reactor
        has been stopped.
        """
        reactor = self.buildReactor()
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        cast(SynchronousTestCase, self).assertRaises(RuntimeError, reactor.stop)

    def test_callWhenRunningOrder(self) -> None:
        """
        Functions are run in the order that they were passed to
        L{reactor.callWhenRunning}.
        """
        reactor = self.buildReactor()
        events: List[str] = []
        reactor.callWhenRunning(events.append, "first")
        reactor.callWhenRunning(events.append, "second")
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        cast(SynchronousTestCase, self).assertEqual(events, ["first", "second"])

    def test_runningForStartupEvents(self) -> None:
        """
        The reactor is not running when C{"before"} C{"startup"} triggers are
        called and is running when C{"during"} and C{"after"} C{"startup"}
        triggers are called.
        """
        reactor = self.buildReactor()
        state = {}

        def beforeStartup() -> None:
            state["before"] = reactor.running

        def duringStartup() -> None:
            state["during"] = reactor.running

        def afterStartup() -> None:
            state["after"] = reactor.running

        testCase = cast(SynchronousTestCase, self)

        reactor.addSystemEventTrigger("before", "startup", beforeStartup)
        reactor.addSystemEventTrigger("during", "startup", duringStartup)
        reactor.addSystemEventTrigger("after", "startup", afterStartup)
        reactor.callWhenRunning(reactor.stop)
        testCase.assertEqual(state, {})
        self.runReactor(reactor)
        testCase.assertEqual(state, {"before": False, "during": True, "after": True})

    def test_signalHandlersInstalledDuringStartup(self) -> None:
        """
        Signal handlers are installed in responsed to the C{"during"}
        C{"startup"}.
        """
        reactor = self.buildReactor()
        phase: Optional[str] = None

        def beforeStartup() -> None:
            nonlocal phase
            phase = "before"

        def afterStartup() -> None:
            nonlocal phase
            phase = "after"

        reactor.addSystemEventTrigger("before", "startup", beforeStartup)
        reactor.addSystemEventTrigger("after", "startup", afterStartup)

        sawPhase = []

        def fakeSignal(signum: int, action: Callable[[int, FrameType], None]) -> None:
            sawPhase.append(phase)

        testCase = cast(SynchronousTestCase, self)

        testCase.patch(signal, "signal", fakeSignal)
        reactor.callWhenRunning(reactor.stop)
        testCase.assertIsNone(phase)
        testCase.assertEqual(sawPhase, [])
        self.runReactor(reactor)
        testCase.assertIn("before", sawPhase)
        testCase.assertEqual(phase, "after")

    def test_stopShutDownEvents(self) -> None:
        """
        C{reactor.stop()} fires all three phases of shutdown event triggers
        before it makes C{reactor.run()} return.
        """
        reactor = self.buildReactor()
        events = []
        reactor.addSystemEventTrigger(
            "before", "shutdown", lambda: events.append(("before", "shutdown"))
        )
        reactor.addSystemEventTrigger(
            "during", "shutdown", lambda: events.append(("during", "shutdown"))
        )
        reactor.addSystemEventTrigger(
            "after", "shutdown", lambda: events.append(("after", "shutdown"))
        )
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        cast(SynchronousTestCase, self).assertEqual(
            events,
            [("before", "shutdown"), ("during", "shutdown"), ("after", "shutdown")],
        )

    def test_shutdownFiresTriggersAsynchronously(self) -> None:
        """
        C{"before"} C{"shutdown"} triggers are not run synchronously from
        L{reactor.stop}.
        """
        reactor = self.buildReactor()
        events: List[str] = []
        reactor.addSystemEventTrigger(
            "before", "shutdown", events.append, "before shutdown"
        )

        def stopIt() -> None:
            reactor.stop()
            events.append("stopped")

        testCase = cast(SynchronousTestCase, self)

        reactor.callWhenRunning(stopIt)
        testCase.assertEqual(events, [])
        self.runReactor(reactor)
        testCase.assertEqual(events, ["stopped", "before shutdown"])

    def test_shutdownDisconnectsCleanly(self) -> None:
        """
        A L{IFileDescriptor.connectionLost} implementation which raises an
        exception does not prevent the remaining L{IFileDescriptor}s from
        having their C{connectionLost} method called.
        """
        lostOK = [False]

        # Subclass FileDescriptor to get logPrefix
        class ProblematicFileDescriptor(FileDescriptor):
            def connectionLost(self, reason: Failure) -> None:
                raise RuntimeError("simulated connectionLost error")

        class OKFileDescriptor(FileDescriptor):
            def connectionLost(self, reason: Failure) -> None:
                lostOK[0] = True

        testCase = cast(SynchronousTestCase, self)
        reactor = self.buildReactor()

        # Unfortunately, it is necessary to patch removeAll to directly control
        # the order of the returned values.  The test is only valid if
        # ProblematicFileDescriptor comes first.  Also, return these
        # descriptors only the first time removeAll is called so that if it is
        # called again the file descriptors aren't re-disconnected.
        fds = iter([ProblematicFileDescriptor(), OKFileDescriptor()])
        reactor.removeAll = lambda: fds
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        testCase.assertEqual(len(testCase.flushLoggedErrors(RuntimeError)), 1)
        testCase.assertTrue(lostOK[0])

    def test_multipleRun(self) -> None:
        """
        C{reactor.run()} raises L{ReactorAlreadyRunning} when called when
        the reactor is already running.
        """
        events: List[str] = []

        testCase = cast(SynchronousTestCase, self)

        def reentrantRun() -> None:
            testCase.assertRaises(ReactorAlreadyRunning, reactor.run)
            events.append("tested")

        reactor = self.buildReactor()
        reactor.callWhenRunning(reentrantRun)
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        testCase.assertEqual(events, ["tested"])

    def test_runWithAsynchronousBeforeStartupTrigger(self) -> None:
        """
        When there is a C{'before'} C{'startup'} trigger which returns an
        unfired L{Deferred}, C{reactor.run()} starts the reactor and does not
        return until after C{reactor.stop()} is called
        """
        events = []

        def trigger() -> Deferred[object]:
            events.append("trigger")
            d: Deferred[object] = Deferred()
            d.addCallback(callback)
            reactor.callLater(0, d.callback, None)
            return d

        def callback(ignored: object) -> None:
            events.append("callback")
            reactor.stop()

        reactor = self.buildReactor()
        reactor.addSystemEventTrigger("before", "startup", trigger)
        self.runReactor(reactor)
        cast(SynchronousTestCase, self).assertEqual(events, ["trigger", "callback"])

    def test_iterate(self) -> None:
        """
        C{reactor.iterate()} does not block.
        """
        reactor = self.buildReactor()
        t = reactor.callLater(5, reactor.crash)

        start = time.time()
        reactor.iterate(0)  # Shouldn't block
        elapsed = time.time() - start

        cast(SynchronousTestCase, self).assertTrue(elapsed < 2)
        t.cancel()

    def test_crash(self) -> None:
        """
        C{reactor.crash()} stops the reactor and does not fire shutdown
        triggers.
        """
        reactor = self.buildReactor()
        events = []
        reactor.addSystemEventTrigger(
            "before", "shutdown", lambda: events.append(("before", "shutdown"))
        )
        reactor.callWhenRunning(reactor.callLater, 0, reactor.crash)
        self.runReactor(reactor)
        testCase = cast(SynchronousTestCase, self)
        testCase.assertFalse(reactor.running)
        testCase.assertFalse(
            events, "Shutdown triggers invoked but they should not have been."
        )

    def test_runAfterCrash(self) -> None:
        """
        C{reactor.run()} restarts the reactor after it has been stopped by
        C{reactor.crash()}.
        """
        events: List[Union[str, Tuple[str, bool]]] = []

        def crash() -> None:
            events.append("crash")
            reactor.crash()

        reactor = self.buildReactor()
        reactor.callWhenRunning(crash)
        self.runReactor(reactor)

        def stop() -> None:
            events.append(("stop", reactor.running))
            reactor.stop()

        reactor.callWhenRunning(stop)
        self.runReactor(reactor)
        cast(SynchronousTestCase, self).assertEqual(events, ["crash", ("stop", True)])

    def test_runAfterStop(self) -> None:
        """
        C{reactor.run()} raises L{ReactorNotRestartable} when called when
        the reactor is being run after getting stopped priorly.
        """
        events: List[str] = []

        testCase = cast(SynchronousTestCase, self)

        def restart() -> None:
            testCase.assertRaises(ReactorNotRestartable, reactor.run)
            events.append("tested")

        reactor = self.buildReactor()
        reactor.callWhenRunning(reactor.stop)
        reactor.addSystemEventTrigger("after", "shutdown", restart)
        self.runReactor(reactor)
        testCase.assertEqual(events, ["tested"])


globals().update(SystemEventTestsBuilder.makeTestCaseClasses())
