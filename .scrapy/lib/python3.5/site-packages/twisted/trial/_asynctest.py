# -*- test-case-name: twisted.trial.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Things likely to be used by writers of unit tests.

Maintainer: Jonathan Lange
"""

from __future__ import division, absolute_import

import inspect
import warnings

from zope.interface import implementer

# We can't import reactor at module-level because this code runs before trial
# installs a user-specified reactor, installing the default reactor and
# breaking reactor installation. See also #6047.
from twisted.internet import defer, utils
from twisted.python import failure

from twisted.trial import itrial, util
from twisted.trial._synctest import (
    FailTest, SkipTest, SynchronousTestCase)

_wait_is_running = []

@implementer(itrial.ITestCase)
class TestCase(SynchronousTestCase):
    """
    A unit test. The atom of the unit testing universe.

    This class extends L{SynchronousTestCase} which extends C{unittest.TestCase}
    from the standard library. The main feature is the ability to return
    C{Deferred}s from tests and fixture methods and to have the suite wait for
    those C{Deferred}s to fire.  Also provides new assertions such as
    L{assertFailure}.

    @ivar timeout: A real number of seconds. If set, the test will
    raise an error if it takes longer than C{timeout} seconds.
    If not set, util.DEFAULT_TIMEOUT_DURATION is used.
    """

    def __init__(self, methodName='runTest'):
        """
        Construct an asynchronous test case for C{methodName}.

        @param methodName: The name of a method on C{self}. This method should
        be a unit test. That is, it should be a short method that calls some of
        the assert* methods. If C{methodName} is unspecified,
        L{SynchronousTestCase.runTest} will be used as the test method. This is
        mostly useful for testing Trial.
        """
        super(TestCase, self).__init__(methodName)


    def assertFailure(self, deferred, *expectedFailures):
        """
        Fail if C{deferred} does not errback with one of C{expectedFailures}.
        Returns the original Deferred with callbacks added. You will need
        to return this Deferred from your test case.
        """
        def _cb(ignore):
            raise self.failureException(
                "did not catch an error, instead got %r" % (ignore,))

        def _eb(failure):
            if failure.check(*expectedFailures):
                return failure.value
            else:
                output = ('\nExpected: %r\nGot:\n%s'
                          % (expectedFailures, str(failure)))
                raise self.failureException(output)
        return deferred.addCallbacks(_cb, _eb)
    failUnlessFailure = assertFailure


    def _run(self, methodName, result):
        from twisted.internet import reactor
        timeout = self.getTimeout()
        def onTimeout(d):
            e = defer.TimeoutError("%r (%s) still running at %s secs"
                % (self, methodName, timeout))
            f = failure.Failure(e)
            # try to errback the deferred that the test returns (for no gorram
            # reason) (see issue1005 and test_errorPropagation in
            # test_deferred)
            try:
                d.errback(f)
            except defer.AlreadyCalledError:
                # if the deferred has been called already but the *back chain
                # is still unfinished, crash the reactor and report timeout
                # error ourself.
                reactor.crash()
                self._timedOut = True # see self._wait
                todo = self.getTodo()
                if todo is not None and todo.expected(f):
                    result.addExpectedFailure(self, f, todo)
                else:
                    result.addError(self, f)
        onTimeout = utils.suppressWarnings(
            onTimeout, util.suppress(category=DeprecationWarning))
        method = getattr(self, methodName)
        if inspect.isgeneratorfunction(method):
            exc = TypeError(
                '%r is a generator function and therefore will never run' % (
                    method,))
            return defer.fail(exc)
        d = defer.maybeDeferred(
            utils.runWithWarningsSuppressed, self._getSuppress(), method)
        call = reactor.callLater(timeout, onTimeout, d)
        d.addBoth(lambda x : call.active() and call.cancel() or x)
        return d


    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)


    def deferSetUp(self, ignored, result):
        d = self._run('setUp', result)
        d.addCallbacks(self.deferTestMethod, self._ebDeferSetUp,
                       callbackArgs=(result,),
                       errbackArgs=(result,))
        return d


    def _ebDeferSetUp(self, failure, result):
        if failure.check(SkipTest):
            result.addSkip(self, self._getSkipReason(self.setUp, failure.value))
        else:
            result.addError(self, failure)
            if failure.check(KeyboardInterrupt):
                result.stop()
        return self.deferRunCleanups(None, result)


    def deferTestMethod(self, ignored, result):
        d = self._run(self._testMethodName, result)
        d.addCallbacks(self._cbDeferTestMethod, self._ebDeferTestMethod,
                       callbackArgs=(result,),
                       errbackArgs=(result,))
        d.addBoth(self.deferRunCleanups, result)
        d.addBoth(self.deferTearDown, result)
        return d


    def _cbDeferTestMethod(self, ignored, result):
        if self.getTodo() is not None:
            result.addUnexpectedSuccess(self, self.getTodo())
        else:
            self._passed = True
        return ignored


    def _ebDeferTestMethod(self, f, result):
        todo = self.getTodo()
        if todo is not None and todo.expected(f):
            result.addExpectedFailure(self, f, todo)
        elif f.check(self.failureException, FailTest):
            result.addFailure(self, f)
        elif f.check(KeyboardInterrupt):
            result.addError(self, f)
            result.stop()
        elif f.check(SkipTest):
            result.addSkip(
                self,
                self._getSkipReason(getattr(self, self._testMethodName), f.value))
        else:
            result.addError(self, f)


    def deferTearDown(self, ignored, result):
        d = self._run('tearDown', result)
        d.addErrback(self._ebDeferTearDown, result)
        return d


    def _ebDeferTearDown(self, failure, result):
        result.addError(self, failure)
        if failure.check(KeyboardInterrupt):
            result.stop()
        self._passed = False


    def deferRunCleanups(self, ignored, result):
        """
        Run any scheduled cleanups and report errors (if any to the result
        object.
        """
        d = self._runCleanups()
        d.addCallback(self._cbDeferRunCleanups, result)
        return d


    def _cbDeferRunCleanups(self, cleanupResults, result):
        for flag, testFailure in cleanupResults:
            if flag == defer.FAILURE:
                result.addError(self, testFailure)
                if testFailure.check(KeyboardInterrupt):
                    result.stop()
                self._passed = False


    def _cleanUp(self, result):
        try:
            clean = util._Janitor(self, result).postCaseCleanup()
            if not clean:
                self._passed = False
        except:
            result.addError(self, failure.Failure())
            self._passed = False
        for error in self._observer.getErrors():
            result.addError(self, error)
            self._passed = False
        self.flushLoggedErrors()
        self._removeObserver()
        if self._passed:
            result.addSuccess(self)


    def _classCleanUp(self, result):
        try:
            util._Janitor(self, result).postClassCleanup()
        except:
            result.addError(self, failure.Failure())


    def _makeReactorMethod(self, name):
        """
        Create a method which wraps the reactor method C{name}. The new
        method issues a deprecation warning and calls the original.
        """
        def _(*a, **kw):
            warnings.warn("reactor.%s cannot be used inside unit tests. "
                          "In the future, using %s will fail the test and may "
                          "crash or hang the test run."
                          % (name, name),
                          stacklevel=2, category=DeprecationWarning)
            return self._reactorMethods[name](*a, **kw)
        return _


    def _deprecateReactor(self, reactor):
        """
        Deprecate C{iterate}, C{crash} and C{stop} on C{reactor}. That is,
        each method is wrapped in a function that issues a deprecation
        warning, then calls the original.

        @param reactor: The Twisted reactor.
        """
        self._reactorMethods = {}
        for name in ['crash', 'iterate', 'stop']:
            self._reactorMethods[name] = getattr(reactor, name)
            setattr(reactor, name, self._makeReactorMethod(name))


    def _undeprecateReactor(self, reactor):
        """
        Restore the deprecated reactor methods. Undoes what
        L{_deprecateReactor} did.

        @param reactor: The Twisted reactor.
        """
        for name, method in self._reactorMethods.items():
            setattr(reactor, name, method)
        self._reactorMethods = {}


    def _runCleanups(self):
        """
        Run the cleanups added with L{addCleanup} in order.

        @return: A C{Deferred} that fires when all cleanups are run.
        """
        def _makeFunction(f, args, kwargs):
            return lambda: f(*args, **kwargs)
        callables = []
        while len(self._cleanups) > 0:
            f, args, kwargs = self._cleanups.pop()
            callables.append(_makeFunction(f, args, kwargs))
        return util._runSequentially(callables)


    def _runFixturesAndTest(self, result):
        """
        Really run C{setUp}, the test method, and C{tearDown}.  Any of these may
        return L{defer.Deferred}s. After they complete, do some reactor cleanup.

        @param result: A L{TestResult} object.
        """
        from twisted.internet import reactor
        self._deprecateReactor(reactor)
        self._timedOut = False
        try:
            d = self.deferSetUp(None, result)
            try:
                self._wait(d)
            finally:
                self._cleanUp(result)
                self._classCleanUp(result)
        finally:
            self._undeprecateReactor(reactor)


    def addCleanup(self, f, *args, **kwargs):
        """
        Extend the base cleanup feature with support for cleanup functions which
        return Deferreds.

        If the function C{f} returns a Deferred, C{TestCase} will wait until the
        Deferred has fired before proceeding to the next function.
        """
        return super(TestCase, self).addCleanup(f, *args, **kwargs)


    def getSuppress(self):
        return self._getSuppress()


    def getTimeout(self):
        """
        Returns the timeout value set on this test. Checks on the instance
        first, then the class, then the module, then packages. As soon as it
        finds something with a C{timeout} attribute, returns that. Returns
        L{util.DEFAULT_TIMEOUT_DURATION} if it cannot find anything. See
        L{TestCase} docstring for more details.
        """
        timeout =  util.acquireAttribute(self._parents, 'timeout',
                                         util.DEFAULT_TIMEOUT_DURATION)
        try:
            return float(timeout)
        except (ValueError, TypeError):
            # XXX -- this is here because sometimes people will have methods
            # called 'timeout', or set timeout to 'orange', or something
            # Particularly, test_news.NewsTestCase and ReactorCoreTestCase
            # both do this.
            warnings.warn("'timeout' attribute needs to be a number.",
                          category=DeprecationWarning)
            return util.DEFAULT_TIMEOUT_DURATION


    def _wait(self, d, running=_wait_is_running):
        """Take a Deferred that only ever callbacks. Block until it happens.
        """
        if running:
            raise RuntimeError("_wait is not reentrant")

        from twisted.internet import reactor
        results = []
        def append(any):
            if results is not None:
                results.append(any)
        def crash(ign):
            if results is not None:
                reactor.crash()
        crash = utils.suppressWarnings(
            crash, util.suppress(message=r'reactor\.crash cannot be used.*',
                                 category=DeprecationWarning))
        def stop():
            reactor.crash()
        stop = utils.suppressWarnings(
            stop, util.suppress(message=r'reactor\.crash cannot be used.*',
                                category=DeprecationWarning))

        running.append(None)
        try:
            d.addBoth(append)
            if results:
                # d might have already been fired, in which case append is
                # called synchronously. Avoid any reactor stuff.
                return
            d.addBoth(crash)
            reactor.stop = stop
            try:
                reactor.run()
            finally:
                del reactor.stop

            # If the reactor was crashed elsewhere due to a timeout, hopefully
            # that crasher also reported an error. Just return.
            # _timedOut is most likely to be set when d has fired but hasn't
            # completed its callback chain (see self._run)
            if results or self._timedOut: #defined in run() and _run()
                return

            # If the timeout didn't happen, and we didn't get a result or
            # a failure, then the user probably aborted the test, so let's
            # just raise KeyboardInterrupt.

            # FIXME: imagine this:
            # web/test/test_webclient.py:
            # exc = self.assertRaises(error.Error, wait, method(url))
            #
            # wait() will raise KeyboardInterrupt, and assertRaises will
            # swallow it. Therefore, wait() raising KeyboardInterrupt is
            # insufficient to stop trial. A suggested solution is to have
            # this code set a "stop trial" flag, or otherwise notify trial
            # that it should really try to stop as soon as possible.
            raise KeyboardInterrupt()
        finally:
            results = None
            running.pop()
