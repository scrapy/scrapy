# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utilities for unit testing reactor implementations.

The main feature of this module is L{ReactorBuilder}, a base class for use when
writing interface/blackbox tests for reactor implementations.  Test case classes
for reactor features should subclass L{ReactorBuilder} instead of
L{SynchronousTestCase}.  All of the features of L{SynchronousTestCase} will be
available.  Additionally, the tests will automatically be applied to all
available reactor implementations.
"""


__all__ = ["TestTimeoutError", "ReactorBuilder", "needsRunningReactor"]

import os
import signal
import time
from typing import TYPE_CHECKING, Dict, Optional, Sequence, Type, Union

from zope.interface import Interface

from twisted.python import log
from twisted.python.deprecate import _fullyQualifiedName as fullyQualifiedName
from twisted.python.failure import Failure
from twisted.python.reflect import namedAny
from twisted.python.runtime import platform
from twisted.trial.unittest import SkipTest, SynchronousTestCase
from twisted.trial.util import DEFAULT_TIMEOUT_DURATION, acquireAttribute

if TYPE_CHECKING:
    # Only bring in this name to support the type annotation below.  We don't
    # really want to import a reactor module this early at runtime.
    from twisted.internet import asyncioreactor

# Access private APIs.
try:
    from twisted.internet import process as _process
except ImportError:
    process = None
else:
    process = _process


class TestTimeoutError(Exception):
    """
    The reactor was still running after the timeout period elapsed in
    L{ReactorBuilder.runReactor}.
    """


def needsRunningReactor(reactor, thunk):
    """
    Various functions within these tests need an already-running reactor at
    some point.  They need to stop the reactor when the test has completed, and
    that means calling reactor.stop().  However, reactor.stop() raises an
    exception if the reactor isn't already running, so if the L{Deferred} that
    a particular API under test returns fires synchronously (as especially an
    endpoint's C{connect()} method may do, if the connect is to a local
    interface address) then the test won't be able to stop the reactor being
    tested and finish.  So this calls C{thunk} only once C{reactor} is running.

    (This is just an alias for
    L{twisted.internet.interfaces.IReactorCore.callWhenRunning} on the given
    reactor parameter, in order to centrally reference the above paragraph and
    repeating it everywhere as a comment.)

    @param reactor: the L{twisted.internet.interfaces.IReactorCore} under test

    @param thunk: a 0-argument callable, which eventually finishes the test in
        question, probably in a L{Deferred} callback.
    """
    reactor.callWhenRunning(thunk)


def stopOnError(case, reactor, publisher=None):
    """
    Stop the reactor as soon as any error is logged on the given publisher.

    This is beneficial for tests which will wait for a L{Deferred} to fire
    before completing (by passing or failing).  Certain implementation bugs may
    prevent the L{Deferred} from firing with any result at all (consider a
    protocol's {dataReceived} method that raises an exception: this exception
    is logged but it won't ever cause a L{Deferred} to fire).  In that case the
    test would have to complete by timing out which is a much less desirable
    outcome than completing as soon as the unexpected error is encountered.

    @param case: A L{SynchronousTestCase} to use to clean up the necessary log
        observer when the test is over.
    @param reactor: The reactor to stop.
    @param publisher: A L{LogPublisher} to watch for errors.  If L{None}, the
        global log publisher will be watched.
    """
    if publisher is None:
        from twisted.python import log as publisher
    running = [None]

    def stopIfError(event):
        if running and event.get("isError"):
            running.pop()
            reactor.stop()

    publisher.addObserver(stopIfError)
    case.addCleanup(publisher.removeObserver, stopIfError)


class ReactorBuilder:
    """
    L{SynchronousTestCase} mixin which provides a reactor-creation API.  This
    mixin defines C{setUp} and C{tearDown}, so mix it in before
    L{SynchronousTestCase} or call its methods from the overridden ones in the
    subclass.

    @cvar skippedReactors: A dict mapping FQPN strings of reactors for
        which the tests defined by this class will be skipped to strings
        giving the skip message.
    @cvar requiredInterfaces: A C{list} of interfaces which the reactor must
        provide or these tests will be skipped.  The default, L{None}, means
        that no interfaces are required.
    @ivar reactorFactory: A no-argument callable which returns the reactor to
        use for testing.
    @ivar originalHandler: The SIGCHLD handler which was installed when setUp
        ran and which will be re-installed when tearDown runs.
    @ivar _reactors: A list of FQPN strings giving the reactors for which
        L{SynchronousTestCase}s will be created.
    """

    _reactors = [
        # Select works everywhere
        "twisted.internet.selectreactor.SelectReactor",
    ]

    if platform.isWindows():
        # PortableGtkReactor is only really interesting on Windows,
        # but not really Windows specific; if you want you can
        # temporarily move this up to the all-platforms list to test
        # it on other platforms.  It's not there in general because
        # it's not _really_ worth it to support on other platforms,
        # since no one really wants to use it on other platforms.
        _reactors.extend(
            [
                "twisted.internet.gtk2reactor.PortableGtkReactor",
                "twisted.internet.gireactor.PortableGIReactor",
                "twisted.internet.gtk3reactor.PortableGtk3Reactor",
                "twisted.internet.win32eventreactor.Win32Reactor",
                "twisted.internet.iocpreactor.reactor.IOCPReactor",
            ]
        )
    else:
        _reactors.extend(
            [
                "twisted.internet.glib2reactor.Glib2Reactor",
                "twisted.internet.gtk2reactor.Gtk2Reactor",
                "twisted.internet.gireactor.GIReactor",
                "twisted.internet.gtk3reactor.Gtk3Reactor",
            ]
        )

        _reactors.append("twisted.internet.test.reactormixins.AsyncioSelectorReactor")

        if platform.isMacOSX():
            _reactors.append("twisted.internet.cfreactor.CFReactor")
        else:
            _reactors.extend(
                [
                    "twisted.internet.pollreactor.PollReactor",
                    "twisted.internet.epollreactor.EPollReactor",
                ]
            )
            if not platform.isLinux():
                # Presumably Linux is not going to start supporting kqueue, so
                # skip even trying this configuration.
                _reactors.extend(
                    [
                        # Support KQueue on non-OS-X POSIX platforms for now.
                        "twisted.internet.kqreactor.KQueueReactor",
                    ]
                )

    reactorFactory = None
    originalHandler = None
    requiredInterfaces: Optional[Sequence[Type[Interface]]] = None
    skippedReactors: Dict[str, str] = {}

    def setUp(self):
        """
        Clear the SIGCHLD handler, if there is one, to ensure an environment
        like the one which exists prior to a call to L{reactor.run}.
        """
        if not platform.isWindows():
            self.originalHandler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)

    def tearDown(self):
        """
        Restore the original SIGCHLD handler and reap processes as long as
        there seem to be any remaining.
        """
        if self.originalHandler is not None:
            signal.signal(signal.SIGCHLD, self.originalHandler)
        if process is not None:
            begin = time.time()
            while process.reapProcessHandlers:
                log.msg(
                    "ReactorBuilder.tearDown reaping some processes %r"
                    % (process.reapProcessHandlers,)
                )
                process.reapAllProcesses()

                # The process should exit on its own.  However, if it
                # doesn't, we're stuck in this loop forever.  To avoid
                # hanging the test suite, eventually give the process some
                # help exiting and move on.
                time.sleep(0.001)
                if time.time() - begin > 60:
                    for pid in process.reapProcessHandlers:
                        os.kill(pid, signal.SIGKILL)
                    raise Exception(
                        "Timeout waiting for child processes to exit: %r"
                        % (process.reapProcessHandlers,)
                    )

    def unbuildReactor(self, reactor):
        """
        Clean up any resources which may have been allocated for the given
        reactor by its creation or by a test which used it.
        """
        # Chris says:
        #
        # XXX These explicit calls to clean up the waker (and any other
        # internal readers) should become obsolete when bug #3063 is
        # fixed. -radix, 2008-02-29. Fortunately it should probably cause an
        # error when bug #3063 is fixed, so it should be removed in the same
        # branch that fixes it.
        #
        # -exarkun
        reactor._uninstallHandler()
        if getattr(reactor, "_internalReaders", None) is not None:
            for reader in reactor._internalReaders:
                reactor.removeReader(reader)
                reader.connectionLost(None)
            reactor._internalReaders.clear()

        # Here's an extra thing unrelated to wakers but necessary for
        # cleaning up after the reactors we make.  -exarkun
        reactor.disconnectAll()

        # It would also be bad if any timed calls left over were allowed to
        # run.
        calls = reactor.getDelayedCalls()
        for c in calls:
            c.cancel()

    def buildReactor(self):
        """
        Create and return a reactor using C{self.reactorFactory}.
        """
        try:
            from twisted.internet import reactor as globalReactor
            from twisted.internet.cfreactor import CFReactor
        except ImportError:
            pass
        else:
            if (
                isinstance(globalReactor, CFReactor)
                and self.reactorFactory is CFReactor
            ):
                raise SkipTest(
                    "CFReactor uses APIs which manipulate global state, "
                    "so it's not safe to run its own reactor-builder tests "
                    "under itself"
                )
        try:
            reactor = self.reactorFactory()
        except BaseException:
            # Unfortunately, not all errors which result in a reactor
            # being unusable are detectable without actually
            # instantiating the reactor.  So we catch some more here
            # and skip the test if necessary.  We also log it to aid
            # with debugging, but flush the logged error so the test
            # doesn't fail.
            log.err(None, "Failed to install reactor")
            self.flushLoggedErrors()
            raise SkipTest(Failure().getErrorMessage())
        else:
            if self.requiredInterfaces is not None:
                missing = [
                    required
                    for required in self.requiredInterfaces
                    if not required.providedBy(reactor)
                ]
                if missing:
                    self.unbuildReactor(reactor)
                    raise SkipTest(
                        "%s does not provide %s"
                        % (
                            fullyQualifiedName(reactor.__class__),
                            ",".join([fullyQualifiedName(x) for x in missing]),
                        )
                    )
        self.addCleanup(self.unbuildReactor, reactor)
        return reactor

    def getTimeout(self):
        """
        Determine how long to run the test before considering it failed.

        @return: A C{int} or C{float} giving a number of seconds.
        """
        return acquireAttribute(self._parents, "timeout", DEFAULT_TIMEOUT_DURATION)

    def runReactor(self, reactor, timeout=None):
        """
        Run the reactor for at most the given amount of time.

        @param reactor: The reactor to run.

        @type timeout: C{int} or C{float}
        @param timeout: The maximum amount of time, specified in seconds, to
            allow the reactor to run.  If the reactor is still running after
            this much time has elapsed, it will be stopped and an exception
            raised.  If L{None}, the default test method timeout imposed by
            Trial will be used.  This depends on the L{IReactorTime}
            implementation of C{reactor} for correct operation.

        @raise TestTimeoutError: If the reactor is still running after
            C{timeout} seconds.
        """
        if timeout is None:
            timeout = self.getTimeout()

        timedOut = []

        def stop():
            timedOut.append(None)
            reactor.stop()

        timedOutCall = reactor.callLater(timeout, stop)
        reactor.run()
        if timedOut:
            raise TestTimeoutError(f"reactor still running after {timeout} seconds")
        else:
            timedOutCall.cancel()

    @classmethod
    def makeTestCaseClasses(
        cls: Type["ReactorBuilder"],
    ) -> Dict[str, Union[Type["ReactorBuilder"], Type[SynchronousTestCase]]]:
        """
        Create a L{SynchronousTestCase} subclass which mixes in C{cls} for each
        known reactor and return a dict mapping their names to them.
        """
        classes: Dict[
            str, Union[Type["ReactorBuilder"], Type[SynchronousTestCase]]
        ] = {}
        for reactor in cls._reactors:
            shortReactorName = reactor.split(".")[-1]
            name = (cls.__name__ + "." + shortReactorName + "Tests").replace(".", "_")

            class testcase(cls, SynchronousTestCase):  # type: ignore[valid-type,misc]
                __module__ = cls.__module__
                if reactor in cls.skippedReactors:
                    skip = cls.skippedReactors[reactor]
                try:
                    reactorFactory = namedAny(reactor)
                except BaseException:
                    skip = Failure().getErrorMessage()

            testcase.__name__ = name
            testcase.__qualname__ = ".".join(cls.__qualname__.split()[0:-1] + [name])
            classes[testcase.__name__] = testcase
        return classes


def asyncioSelectorReactor(self: object) -> "asyncioreactor.AsyncioSelectorReactor":
    """
    Make a new asyncio reactor associated with a new event loop.

    The test suite prefers this constructor because having a new event loop
    for each reactor provides better test isolation.  The real constructor
    prefers to re-use (or create) a global loop because of how this interacts
    with other asyncio-based libraries and applications (though maybe it
    shouldn't).

    @param self: The L{ReactorBuilder} subclass this is being called on.  We
        don't use this parameter but we get called with it anyway.
    """
    from asyncio import new_event_loop, set_event_loop

    from twisted.internet import asyncioreactor

    loop = new_event_loop()
    set_event_loop(loop)

    return asyncioreactor.AsyncioSelectorReactor(loop)


# Give it an alias that makes the names of the generated test classes fit the
# pattern.
AsyncioSelectorReactor = asyncioSelectorReactor
