# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorCore}.
"""

from __future__ import division, absolute_import

__metaclass__ = type

import signal
import time
import inspect

from twisted.internet.abstract import FileDescriptor
from twisted.internet.error import ReactorAlreadyRunning, ReactorNotRestartable
from twisted.internet.defer import Deferred
from twisted.internet.test.reactormixins import ReactorBuilder


class ObjectModelIntegrationMixin(object):
    """
    Helpers for tests about the object model of reactor-related objects.
    """
    def assertFullyNewStyle(self, instance):
        """
        Assert that the given object is an instance of a new-style class and
        that there are no classic classes in the inheritance hierarchy of
        that class.

        This is a beneficial condition because PyPy is better able to
        optimize attribute lookup on such classes.
        """
        self.assertIsInstance(instance, object)
        mro = inspect.getmro(type(instance))
        for subclass in mro:
            self.assertTrue(
                issubclass(subclass, object),
                "%r is not new-style" % (subclass,))



class ObjectModelIntegrationTests(ReactorBuilder, ObjectModelIntegrationMixin):
    """
    Test details of object model integration against all reactors.
    """

    def test_newstyleReactor(self):
        """
        Checks that all reactors on a platform have method resolution order
        containing only new style classes.
        """
        reactor = self.buildReactor()
        self.assertFullyNewStyle(reactor)



class SystemEventTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{IReactorCore.addSystemEventTrigger}
    and L{IReactorCore.fireSystemEvent}.
    """
    def test_stopWhenNotStarted(self):
        """
        C{reactor.stop()} raises L{RuntimeError} when called when the reactor
        has not been started.
        """
        reactor = self.buildReactor()
        self.assertRaises(RuntimeError, reactor.stop)


    def test_stopWhenAlreadyStopped(self):
        """
        C{reactor.stop()} raises L{RuntimeError} when called after the reactor
        has been stopped.
        """
        reactor = self.buildReactor()
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertRaises(RuntimeError, reactor.stop)


    def test_callWhenRunningOrder(self):
        """
        Functions are run in the order that they were passed to
        L{reactor.callWhenRunning}.
        """
        reactor = self.buildReactor()
        events = []
        reactor.callWhenRunning(events.append, "first")
        reactor.callWhenRunning(events.append, "second")
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertEqual(events, ["first", "second"])


    def test_runningForStartupEvents(self):
        """
        The reactor is not running when C{"before"} C{"startup"} triggers are
        called and is running when C{"during"} and C{"after"} C{"startup"}
        triggers are called.
        """
        reactor = self.buildReactor()
        state = {}
        def beforeStartup():
            state['before'] = reactor.running
        def duringStartup():
            state['during'] = reactor.running
        def afterStartup():
            state['after'] = reactor.running
        reactor.addSystemEventTrigger("before", "startup", beforeStartup)
        reactor.addSystemEventTrigger("during", "startup", duringStartup)
        reactor.addSystemEventTrigger("after", "startup", afterStartup)
        reactor.callWhenRunning(reactor.stop)
        self.assertEqual(state, {})
        self.runReactor(reactor)
        self.assertEqual(
            state,
            {"before": False,
             "during": True,
             "after": True})


    def test_signalHandlersInstalledDuringStartup(self):
        """
        Signal handlers are installed in responsed to the C{"during"}
        C{"startup"}.
        """
        reactor = self.buildReactor()
        phase = [None]
        def beforeStartup():
            phase[0] = "before"
        def afterStartup():
            phase[0] = "after"
        reactor.addSystemEventTrigger("before", "startup", beforeStartup)
        reactor.addSystemEventTrigger("after", "startup", afterStartup)

        sawPhase = []
        def fakeSignal(signum, action):
            sawPhase.append(phase[0])
        self.patch(signal, 'signal', fakeSignal)
        reactor.callWhenRunning(reactor.stop)
        self.assertIsNone(phase[0])
        self.assertEqual(sawPhase, [])
        self.runReactor(reactor)
        self.assertIn("before", sawPhase)
        self.assertEqual(phase[0], "after")


    def test_stopShutDownEvents(self):
        """
        C{reactor.stop()} fires all three phases of shutdown event triggers
        before it makes C{reactor.run()} return.
        """
        reactor = self.buildReactor()
        events = []
        reactor.addSystemEventTrigger(
            "before", "shutdown",
            lambda: events.append(("before", "shutdown")))
        reactor.addSystemEventTrigger(
            "during", "shutdown",
            lambda: events.append(("during", "shutdown")))
        reactor.addSystemEventTrigger(
            "after", "shutdown",
            lambda: events.append(("after", "shutdown")))
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertEqual(events, [("before", "shutdown"),
                                   ("during", "shutdown"),
                                   ("after", "shutdown")])


    def test_shutdownFiresTriggersAsynchronously(self):
        """
        C{"before"} C{"shutdown"} triggers are not run synchronously from
        L{reactor.stop}.
        """
        reactor = self.buildReactor()
        events = []
        reactor.addSystemEventTrigger(
            "before", "shutdown", events.append, "before shutdown")
        def stopIt():
            reactor.stop()
            events.append("stopped")
        reactor.callWhenRunning(stopIt)
        self.assertEqual(events, [])
        self.runReactor(reactor)
        self.assertEqual(events, ["stopped", "before shutdown"])


    def test_shutdownDisconnectsCleanly(self):
        """
        A L{IFileDescriptor.connectionLost} implementation which raises an
        exception does not prevent the remaining L{IFileDescriptor}s from
        having their C{connectionLost} method called.
        """
        lostOK = [False]

        # Subclass FileDescriptor to get logPrefix
        class ProblematicFileDescriptor(FileDescriptor):
            def connectionLost(self, reason):
                raise RuntimeError("simulated connectionLost error")

        class OKFileDescriptor(FileDescriptor):
            def connectionLost(self, reason):
                lostOK[0] = True

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
        self.assertEqual(len(self.flushLoggedErrors(RuntimeError)), 1)
        self.assertTrue(lostOK[0])


    def test_multipleRun(self):
        """
        C{reactor.run()} raises L{ReactorAlreadyRunning} when called when
        the reactor is already running.
        """
        events = []
        def reentrantRun():
            self.assertRaises(ReactorAlreadyRunning, reactor.run)
            events.append("tested")
        reactor = self.buildReactor()
        reactor.callWhenRunning(reentrantRun)
        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertEqual(events, ["tested"])


    def test_runWithAsynchronousBeforeStartupTrigger(self):
        """
        When there is a C{'before'} C{'startup'} trigger which returns an
        unfired L{Deferred}, C{reactor.run()} starts the reactor and does not
        return until after C{reactor.stop()} is called
        """
        events = []
        def trigger():
            events.append('trigger')
            d = Deferred()
            d.addCallback(callback)
            reactor.callLater(0, d.callback, None)
            return d
        def callback(ignored):
            events.append('callback')
            reactor.stop()
        reactor = self.buildReactor()
        reactor.addSystemEventTrigger('before', 'startup', trigger)
        self.runReactor(reactor)
        self.assertEqual(events, ['trigger', 'callback'])


    def test_iterate(self):
        """
        C{reactor.iterate()} does not block.
        """
        reactor = self.buildReactor()
        t = reactor.callLater(5, reactor.crash)

        start = time.time()
        reactor.iterate(0) # Shouldn't block
        elapsed = time.time() - start

        self.assertTrue(elapsed < 2)
        t.cancel()


    def test_crash(self):
        """
        C{reactor.crash()} stops the reactor and does not fire shutdown
        triggers.
        """
        reactor = self.buildReactor()
        events = []
        reactor.addSystemEventTrigger(
            "before", "shutdown",
            lambda: events.append(("before", "shutdown")))
        reactor.callWhenRunning(reactor.callLater, 0, reactor.crash)
        self.runReactor(reactor)
        self.assertFalse(reactor.running)
        self.assertFalse(
            events,
            "Shutdown triggers invoked but they should not have been.")


    def test_runAfterCrash(self):
        """
        C{reactor.run()} restarts the reactor after it has been stopped by
        C{reactor.crash()}.
        """
        events = []
        def crash():
            events.append('crash')
            reactor.crash()
        reactor = self.buildReactor()
        reactor.callWhenRunning(crash)
        self.runReactor(reactor)
        def stop():
            events.append(('stop', reactor.running))
            reactor.stop()
        reactor.callWhenRunning(stop)
        self.runReactor(reactor)
        self.assertEqual(events, ['crash', ('stop', True)])


    def test_runAfterStop(self):
        """
        C{reactor.run()} raises L{ReactorNotRestartable} when called when
        the reactor is being run after getting stopped priorly.
        """
        events = []
        def restart():
            self.assertRaises(ReactorNotRestartable, reactor.run)
            events.append('tested')
        reactor = self.buildReactor()
        reactor.callWhenRunning(reactor.stop)
        reactor.addSystemEventTrigger('after', 'shutdown', restart)
        self.runReactor(reactor)
        self.assertEqual(events, ['tested'])



globals().update(SystemEventTestsBuilder.makeTestCaseClasses())
globals().update(ObjectModelIntegrationTests.makeTestCaseClasses())
