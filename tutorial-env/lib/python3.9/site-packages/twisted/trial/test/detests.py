# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for Deferred handling by L{twisted.trial.unittest.TestCase}.
"""


from twisted.internet import defer, reactor, threads
from twisted.python.util import runWithWarningsSuppressed
from twisted.trial import unittest
from twisted.trial.util import suppress as SUPPRESS


class DeferredSetUpOK(unittest.TestCase):
    def setUp(self):
        d = defer.succeed("value")
        d.addCallback(self._cb_setUpCalled)
        return d

    def _cb_setUpCalled(self, ignored):
        self._setUpCalled = True

    def test_ok(self):
        self.assertTrue(self._setUpCalled)


class DeferredSetUpFail(unittest.TestCase):
    testCalled = False

    def setUp(self):
        return defer.fail(unittest.FailTest("i fail"))

    def test_ok(self):
        DeferredSetUpFail.testCalled = True
        self.fail("I should not get called")


class DeferredSetUpCallbackFail(unittest.TestCase):
    testCalled = False

    def setUp(self):
        d = defer.succeed("value")
        d.addCallback(self._cb_setUpCalled)
        return d

    def _cb_setUpCalled(self, ignored):
        self.fail("deliberate failure")

    def test_ok(self):
        DeferredSetUpCallbackFail.testCalled = True


class DeferredSetUpError(unittest.TestCase):
    testCalled = False

    def setUp(self):
        return defer.fail(RuntimeError("deliberate error"))

    def test_ok(self):
        DeferredSetUpError.testCalled = True


class DeferredSetUpNeverFire(unittest.TestCase):
    testCalled = False

    def setUp(self):
        return defer.Deferred()

    def test_ok(self):
        DeferredSetUpNeverFire.testCalled = True


class DeferredSetUpSkip(unittest.TestCase):
    testCalled = False

    def setUp(self):
        d = defer.succeed("value")
        d.addCallback(self._cb1)
        return d

    def _cb1(self, ignored):
        raise unittest.SkipTest("skip me")

    def test_ok(self):
        DeferredSetUpSkip.testCalled = True


class DeferredTests(unittest.TestCase):
    touched = False

    def _cb_fail(self, reason):
        self.fail(reason)

    def _cb_error(self, reason):
        raise RuntimeError(reason)

    def _cb_skip(self, reason):
        raise unittest.SkipTest(reason)

    def _touchClass(self, ignored):
        self.__class__.touched = True

    def setUp(self):
        self.__class__.touched = False

    def test_pass(self):
        return defer.succeed("success")

    def test_passGenerated(self):
        self._touchClass(None)
        yield None

    test_passGenerated = runWithWarningsSuppressed(
        [
            SUPPRESS(
                message="twisted.internet.defer.deferredGenerator was " "deprecated"
            )
        ],
        defer.deferredGenerator,
        test_passGenerated,
    )

    @defer.inlineCallbacks
    def test_passInlineCallbacks(self):
        """
        Test case that is decorated with L{defer.inlineCallbacks}.
        """
        self._touchClass(None)
        yield None

    def test_fail(self):
        return defer.fail(self.failureException("I fail"))

    def test_failureInCallback(self):
        d = defer.succeed("fail")
        d.addCallback(self._cb_fail)
        return d

    def test_errorInCallback(self):
        d = defer.succeed("error")
        d.addCallback(self._cb_error)
        return d

    def test_skip(self):
        d = defer.succeed("skip")
        d.addCallback(self._cb_skip)
        d.addCallback(self._touchClass)
        return d

    def test_thread(self):
        return threads.deferToThread(lambda: None)

    def test_expectedFailure(self):
        d = defer.succeed("todo")
        d.addCallback(self._cb_error)
        return d

    test_expectedFailure.todo = "Expected failure"  # type: ignore[attr-defined]


class TimeoutTests(unittest.TestCase):
    timedOut = None

    def test_pass(self):
        d = defer.Deferred()
        reactor.callLater(0, d.callback, "hoorj!")
        return d

    test_pass.timeout = 2  # type: ignore[attr-defined]

    def test_passDefault(self):
        # test default timeout
        d = defer.Deferred()
        reactor.callLater(0, d.callback, "hoorj!")
        return d

    def test_timeout(self):
        return defer.Deferred()

    test_timeout.timeout = 0.1  # type: ignore[attr-defined]

    def test_timeoutZero(self):
        return defer.Deferred()

    test_timeoutZero.timeout = 0  # type: ignore[attr-defined]

    def test_expectedFailure(self):
        return defer.Deferred()

    test_expectedFailure.timeout = 0.1  # type: ignore[attr-defined]
    test_expectedFailure.todo = "i will get it right, eventually"  # type: ignore[attr-defined]

    def test_skip(self):
        return defer.Deferred()

    test_skip.timeout = 0.1  # type: ignore[attr-defined]
    test_skip.skip = "i will get it right, eventually"  # type: ignore[attr-defined]

    def test_errorPropagation(self):
        def timedOut(err):
            self.__class__.timedOut = err
            return err

        d = defer.Deferred()
        d.addErrback(timedOut)
        return d

    test_errorPropagation.timeout = 0.1  # type: ignore[attr-defined]

    def test_calledButNeverCallback(self):
        d = defer.Deferred()

        def neverFire(r):
            return defer.Deferred()

        d.addCallback(neverFire)
        d.callback(1)
        return d

    test_calledButNeverCallback.timeout = 0.1  # type: ignore[attr-defined]


class TestClassTimeoutAttribute(unittest.TestCase):
    timeout = 0.2

    def setUp(self):
        self.d = defer.Deferred()

    def testMethod(self):
        self.methodCalled = True
        return self.d
