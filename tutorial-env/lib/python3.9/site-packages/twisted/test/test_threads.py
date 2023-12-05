# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Test methods in twisted.internet.threads and reactor thread APIs.
"""


import os
import sys
import time
from unittest import skipIf

from twisted.internet import defer, error, interfaces, protocol, reactor, threads
from twisted.python import failure, log, threadable, threadpool
from twisted.trial.unittest import TestCase

try:
    import threading
except ImportError:
    pass


@skipIf(
    not interfaces.IReactorThreads(reactor, None),
    "No thread support, nothing to test here.",
)
class ReactorThreadsTests(TestCase):
    """
    Tests for the reactor threading API.
    """

    def test_suggestThreadPoolSize(self):
        """
        Try to change maximum number of threads.
        """
        reactor.suggestThreadPoolSize(34)
        self.assertEqual(reactor.threadpool.max, 34)
        reactor.suggestThreadPoolSize(4)
        self.assertEqual(reactor.threadpool.max, 4)

    def _waitForThread(self):
        """
        The reactor's threadpool is only available when the reactor is running,
        so to have a sane behavior during the tests we make a dummy
        L{threads.deferToThread} call.
        """
        return threads.deferToThread(time.sleep, 0)

    def test_callInThread(self):
        """
        Test callInThread functionality: set a C{threading.Event}, and check
        that it's not in the main thread.
        """

        def cb(ign):
            waiter = threading.Event()
            result = []

            def threadedFunc():
                result.append(threadable.isInIOThread())
                waiter.set()

            reactor.callInThread(threadedFunc)
            waiter.wait(120)
            if not waiter.isSet():
                self.fail("Timed out waiting for event.")
            else:
                self.assertEqual(result, [False])

        return self._waitForThread().addCallback(cb)

    def test_callFromThread(self):
        """
        Test callFromThread functionality: from the main thread, and from
        another thread.
        """

        def cb(ign):
            firedByReactorThread = defer.Deferred()
            firedByOtherThread = defer.Deferred()

            def threadedFunc():
                reactor.callFromThread(firedByOtherThread.callback, None)

            reactor.callInThread(threadedFunc)
            reactor.callFromThread(firedByReactorThread.callback, None)

            return defer.DeferredList(
                [firedByReactorThread, firedByOtherThread], fireOnOneErrback=True
            )

        return self._waitForThread().addCallback(cb)

    def test_wakerOverflow(self):
        """
        Try to make an overflow on the reactor waker using callFromThread.
        """

        def cb(ign):
            self.failure = None
            waiter = threading.Event()

            def threadedFunction():
                # Hopefully a hundred thousand queued calls is enough to
                # trigger the error condition
                for i in range(100000):
                    try:
                        reactor.callFromThread(lambda: None)
                    except BaseException:
                        self.failure = failure.Failure()
                        break
                waiter.set()

            reactor.callInThread(threadedFunction)
            waiter.wait(120)
            if not waiter.isSet():
                self.fail("Timed out waiting for event")
            if self.failure is not None:
                return defer.fail(self.failure)

        return self._waitForThread().addCallback(cb)

    def _testBlockingCallFromThread(self, reactorFunc):
        """
        Utility method to test L{threads.blockingCallFromThread}.
        """
        waiter = threading.Event()
        results = []
        errors = []

        def cb1(ign):
            def threadedFunc():
                try:
                    r = threads.blockingCallFromThread(reactor, reactorFunc)
                except Exception as e:
                    errors.append(e)
                else:
                    results.append(r)
                waiter.set()

            reactor.callInThread(threadedFunc)
            return threads.deferToThread(waiter.wait, self.getTimeout())

        def cb2(ign):
            if not waiter.isSet():
                self.fail("Timed out waiting for event")
            return results, errors

        return self._waitForThread().addCallback(cb1).addBoth(cb2)

    def test_blockingCallFromThread(self):
        """
        Test blockingCallFromThread facility: create a thread, call a function
        in the reactor using L{threads.blockingCallFromThread}, and verify the
        result returned.
        """

        def reactorFunc():
            return defer.succeed("foo")

        def cb(res):
            self.assertEqual(res[0][0], "foo")

        return self._testBlockingCallFromThread(reactorFunc).addCallback(cb)

    def test_asyncBlockingCallFromThread(self):
        """
        Test blockingCallFromThread as above, but be sure the resulting
        Deferred is not already fired.
        """

        def reactorFunc():
            d = defer.Deferred()
            reactor.callLater(0.1, d.callback, "egg")
            return d

        def cb(res):
            self.assertEqual(res[0][0], "egg")

        return self._testBlockingCallFromThread(reactorFunc).addCallback(cb)

    def test_errorBlockingCallFromThread(self):
        """
        Test error report for blockingCallFromThread.
        """

        def reactorFunc():
            return defer.fail(RuntimeError("bar"))

        def cb(res):
            self.assertIsInstance(res[1][0], RuntimeError)
            self.assertEqual(res[1][0].args[0], "bar")

        return self._testBlockingCallFromThread(reactorFunc).addCallback(cb)

    def test_asyncErrorBlockingCallFromThread(self):
        """
        Test error report for blockingCallFromThread as above, but be sure the
        resulting Deferred is not already fired.
        """

        def reactorFunc():
            d = defer.Deferred()
            reactor.callLater(0.1, d.errback, RuntimeError("spam"))
            return d

        def cb(res):
            self.assertIsInstance(res[1][0], RuntimeError)
            self.assertEqual(res[1][0].args[0], "spam")

        return self._testBlockingCallFromThread(reactorFunc).addCallback(cb)


class Counter:
    index = 0
    problem = 0

    def add(self):
        """A non thread-safe method."""
        next = self.index + 1
        # another thread could jump in here and increment self.index on us
        if next != self.index + 1:
            self.problem = 1
            raise ValueError
        # or here, same issue but we wouldn't catch it. We'd overwrite
        # their results, and the index will have lost a count. If
        # several threads get in here, we will actually make the count
        # go backwards when we overwrite it.
        self.index = next


@skipIf(
    not interfaces.IReactorThreads(reactor, None),
    "No thread support, nothing to test here.",
)
class DeferredResultTests(TestCase):
    """
    Test twisted.internet.threads.
    """

    def setUp(self):
        reactor.suggestThreadPoolSize(8)

    def tearDown(self):
        reactor.suggestThreadPoolSize(0)

    def test_callMultiple(self):
        """
        L{threads.callMultipleInThread} calls multiple functions in a thread.
        """
        L = []
        N = 10
        d = defer.Deferred()

        def finished():
            self.assertEqual(L, list(range(N)))
            d.callback(None)

        threads.callMultipleInThread(
            [(L.append, (i,), {}) for i in range(N)]
            + [(reactor.callFromThread, (finished,), {})]
        )
        return d

    def test_deferredResult(self):
        """
        L{threads.deferToThread} executes the function passed, and correctly
        handles the positional and keyword arguments given.
        """
        d = threads.deferToThread(lambda x, y=5: x + y, 3, y=4)
        d.addCallback(self.assertEqual, 7)
        return d

    def test_deferredFailure(self):
        """
        Check that L{threads.deferToThread} return a failure object
        with an appropriate exception instance when the called
        function raises an exception.
        """

        class NewError(Exception):
            pass

        def raiseError():
            raise NewError()

        d = threads.deferToThread(raiseError)
        return self.assertFailure(d, NewError)

    def test_deferredFailureAfterSuccess(self):
        """
        Check that a successful L{threads.deferToThread} followed by a one
        that raises an exception correctly result as a failure.
        """
        # set up a condition that causes cReactor to hang. These conditions
        # can also be set by other tests when the full test suite is run in
        # alphabetical order (test_flow.FlowTest.testThreaded followed by
        # test_internet.ReactorCoreTestCase.testStop, to be precise). By
        # setting them up explicitly here, we can reproduce the hang in a
        # single precise test case instead of depending upon side effects of
        # other tests.
        #
        # alas, this test appears to flunk the default reactor too

        d = threads.deferToThread(lambda: None)
        d.addCallback(lambda ign: threads.deferToThread(lambda: 1 // 0))
        return self.assertFailure(d, ZeroDivisionError)


class DeferToThreadPoolTests(TestCase):
    """
    Test L{twisted.internet.threads.deferToThreadPool}.
    """

    def setUp(self):
        self.tp = threadpool.ThreadPool(0, 8)
        self.tp.start()

    def tearDown(self):
        self.tp.stop()

    def test_deferredResult(self):
        """
        L{threads.deferToThreadPool} executes the function passed, and
        correctly handles the positional and keyword arguments given.
        """
        d = threads.deferToThreadPool(reactor, self.tp, lambda x, y=5: x + y, 3, y=4)
        d.addCallback(self.assertEqual, 7)
        return d

    def test_deferredFailure(self):
        """
        Check that L{threads.deferToThreadPool} return a failure object with an
        appropriate exception instance when the called function raises an
        exception.
        """

        class NewError(Exception):
            pass

        def raiseError():
            raise NewError()

        d = threads.deferToThreadPool(reactor, self.tp, raiseError)
        return self.assertFailure(d, NewError)


_callBeforeStartupProgram = """
import time
import %(reactor)s
%(reactor)s.install()

from twisted.internet import reactor

def threadedCall():
    print('threaded call')

reactor.callInThread(threadedCall)

# Spin very briefly to try to give the thread a chance to run, if it
# is going to.  Is there a better way to achieve this behavior?
for i in range(100):
    time.sleep(0.0)
"""


class ThreadStartupProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, finished):
        self.finished = finished
        self.out = []
        self.err = []

    def outReceived(self, out):
        self.out.append(out)

    def errReceived(self, err):
        self.err.append(err)

    def processEnded(self, reason):
        self.finished.callback((self.out, self.err, reason))


@skipIf(
    not interfaces.IReactorThreads(reactor, None),
    "No thread support, nothing to test here.",
)
@skipIf(
    not interfaces.IReactorProcess(reactor, None),
    "No process support, cannot run subprocess thread tests.",
)
class StartupBehaviorTests(TestCase):
    """
    Test cases for the behavior of the reactor threadpool near startup
    boundary conditions.

    In particular, this asserts that no threaded calls are attempted
    until the reactor starts up, that calls attempted before it starts
    are in fact executed once it has started, and that in both cases,
    the reactor properly cleans itself up (which is tested for
    somewhat implicitly, by requiring a child process be able to exit,
    something it cannot do unless the threadpool has been properly
    torn down).
    """

    def testCallBeforeStartupUnexecuted(self):
        progname = self.mktemp()
        with open(progname, "w") as progfile:
            progfile.write(_callBeforeStartupProgram % {"reactor": reactor.__module__})

        def programFinished(result):
            (out, err, reason) = result
            if reason.check(error.ProcessTerminated):
                self.fail(f"Process did not exit cleanly (out: {out} err: {err})")

            if err:
                log.msg(f"Unexpected output on standard error: {err}")
            self.assertFalse(out, f"Expected no output, instead received:\n{out}")

        def programTimeout(err):
            err.trap(error.TimeoutError)
            proto.signalProcess("KILL")
            return err

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        d = defer.Deferred().addCallbacks(programFinished, programTimeout)
        proto = ThreadStartupProcessProtocol(d)
        reactor.spawnProcess(proto, sys.executable, ("python", progname), env)
        return d
