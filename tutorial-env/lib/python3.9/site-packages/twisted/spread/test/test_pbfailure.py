# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for error handling in PB.
"""

from io import StringIO

from twisted.internet import defer, reactor
from twisted.python import log
from twisted.python.reflect import qual
from twisted.spread import flavors, jelly, pb
from twisted.trial import unittest

# Test exceptions


class AsynchronousException(Exception):
    """
    Helper used to test remote methods which return Deferreds which fail with
    exceptions which are not L{pb.Error} subclasses.
    """


class SynchronousException(Exception):
    """
    Helper used to test remote methods which raise exceptions which are not
    L{pb.Error} subclasses.
    """


class AsynchronousError(pb.Error):
    """
    Helper used to test remote methods which return Deferreds which fail with
    exceptions which are L{pb.Error} subclasses.
    """


class SynchronousError(pb.Error):
    """
    Helper used to test remote methods which raise exceptions which are
    L{pb.Error} subclasses.
    """


class JellyError(flavors.Jellyable, pb.Error, pb.RemoteCopy):
    pass


class SecurityError(pb.Error, pb.RemoteCopy):
    pass


pb.setUnjellyableForClass(JellyError, JellyError)
pb.setUnjellyableForClass(SecurityError, SecurityError)
pb.globalSecurity.allowInstancesOf(SecurityError)


# Server-side
class SimpleRoot(pb.Root):
    def remote_asynchronousException(self):
        """
        Fail asynchronously with a non-pb.Error exception.
        """
        return defer.fail(AsynchronousException("remote asynchronous exception"))

    def remote_synchronousException(self):
        """
        Fail synchronously with a non-pb.Error exception.
        """
        raise SynchronousException("remote synchronous exception")

    def remote_asynchronousError(self):
        """
        Fail asynchronously with a pb.Error exception.
        """
        return defer.fail(AsynchronousError("remote asynchronous error"))

    def remote_synchronousError(self):
        """
        Fail synchronously with a pb.Error exception.
        """
        raise SynchronousError("remote synchronous error")

    def remote_unknownError(self):
        """
        Fail with error that is not known to client.
        """

        class UnknownError(pb.Error):
            pass

        raise UnknownError("I'm not known to client!")

    def remote_jelly(self):
        self.raiseJelly()

    def remote_security(self):
        self.raiseSecurity()

    def remote_deferredJelly(self):
        d = defer.Deferred()
        d.addCallback(self.raiseJelly)
        d.callback(None)
        return d

    def remote_deferredSecurity(self):
        d = defer.Deferred()
        d.addCallback(self.raiseSecurity)
        d.callback(None)
        return d

    def raiseJelly(self, results=None):
        raise JellyError("I'm jellyable!")

    def raiseSecurity(self, results=None):
        raise SecurityError("I'm secure!")


class SaveProtocolServerFactory(pb.PBServerFactory):
    """
    A L{pb.PBServerFactory} that saves the latest connected client in
    C{protocolInstance}.
    """

    protocolInstance = None

    def clientConnectionMade(self, protocol):
        """
        Keep track of the given protocol.
        """
        self.protocolInstance = protocol


class PBConnTestCase(unittest.TestCase):
    unsafeTracebacks = 0

    def setUp(self):
        self._setUpServer()
        self._setUpClient()

    def _setUpServer(self):
        self.serverFactory = SaveProtocolServerFactory(SimpleRoot())
        self.serverFactory.unsafeTracebacks = self.unsafeTracebacks
        self.serverPort = reactor.listenTCP(
            0, self.serverFactory, interface="127.0.0.1"
        )

    def _setUpClient(self):
        portNo = self.serverPort.getHost().port
        self.clientFactory = pb.PBClientFactory()
        self.clientConnector = reactor.connectTCP(
            "127.0.0.1", portNo, self.clientFactory
        )

    def tearDown(self):
        if self.serverFactory.protocolInstance is not None:
            self.serverFactory.protocolInstance.transport.loseConnection()
        return defer.gatherResults([self._tearDownServer(), self._tearDownClient()])

    def _tearDownServer(self):
        return defer.maybeDeferred(self.serverPort.stopListening)

    def _tearDownClient(self):
        self.clientConnector.disconnect()
        return defer.succeed(None)


class PBFailureTests(PBConnTestCase):
    compare = unittest.TestCase.assertEqual

    def _exceptionTest(self, method, exceptionType, flush):
        def eb(err):
            err.trap(exceptionType)
            self.compare(err.traceback, "Traceback unavailable\n")
            if flush:
                errs = self.flushLoggedErrors(exceptionType)
                self.assertEqual(len(errs), 1)
            return (err.type, err.value, err.traceback)

        d = self.clientFactory.getRootObject()

        def gotRootObject(root):
            d = root.callRemote(method)
            d.addErrback(eb)
            return d

        d.addCallback(gotRootObject)
        return d

    def test_asynchronousException(self):
        """
        Test that a Deferred returned by a remote method which already has a
        Failure correctly has that error passed back to the calling side.
        """
        return self._exceptionTest("asynchronousException", AsynchronousException, True)

    def test_synchronousException(self):
        """
        Like L{test_asynchronousException}, but for a method which raises an
        exception synchronously.
        """
        return self._exceptionTest("synchronousException", SynchronousException, True)

    def test_asynchronousError(self):
        """
        Like L{test_asynchronousException}, but for a method which returns a
        Deferred failing with an L{pb.Error} subclass.
        """
        return self._exceptionTest("asynchronousError", AsynchronousError, False)

    def test_synchronousError(self):
        """
        Like L{test_asynchronousError}, but for a method which synchronously
        raises a L{pb.Error} subclass.
        """
        return self._exceptionTest("synchronousError", SynchronousError, False)

    def _success(self, result, expectedResult):
        self.assertEqual(result, expectedResult)
        return result

    def _addFailingCallbacks(self, remoteCall, expectedResult, eb):
        remoteCall.addCallbacks(self._success, eb, callbackArgs=(expectedResult,))
        return remoteCall

    def _testImpl(self, method, expected, eb, exc=None):
        """
        Call the given remote method and attach the given errback to the
        resulting Deferred.  If C{exc} is not None, also assert that one
        exception of that type was logged.
        """
        rootDeferred = self.clientFactory.getRootObject()

        def gotRootObj(obj):
            failureDeferred = self._addFailingCallbacks(
                obj.callRemote(method), expected, eb
            )
            if exc is not None:

                def gotFailure(err):
                    self.assertEqual(len(self.flushLoggedErrors(exc)), 1)
                    return err

                failureDeferred.addBoth(gotFailure)
            return failureDeferred

        rootDeferred.addCallback(gotRootObj)
        return rootDeferred

    def test_jellyFailure(self):
        """
        Test that an exception which is a subclass of L{pb.Error} has more
        information passed across the network to the calling side.
        """

        def failureJelly(fail):
            fail.trap(JellyError)
            self.assertNotIsInstance(fail.type, str)
            self.assertIsInstance(fail.value, fail.type)
            return 43

        return self._testImpl("jelly", 43, failureJelly)

    def test_deferredJellyFailure(self):
        """
        Test that a Deferred which fails with a L{pb.Error} is treated in
        the same way as a synchronously raised L{pb.Error}.
        """

        def failureDeferredJelly(fail):
            fail.trap(JellyError)
            self.assertNotIsInstance(fail.type, str)
            self.assertIsInstance(fail.value, fail.type)
            return 430

        return self._testImpl("deferredJelly", 430, failureDeferredJelly)

    def test_unjellyableFailure(self):
        """
        A non-jellyable L{pb.Error} subclass raised by a remote method is
        turned into a Failure with a type set to the FQPN of the exception
        type.
        """

        def failureUnjellyable(fail):
            self.assertEqual(
                fail.type, b"twisted.spread.test.test_pbfailure.SynchronousError"
            )
            return 431

        return self._testImpl("synchronousError", 431, failureUnjellyable)

    def test_unknownFailure(self):
        """
        Test that an exception which is a subclass of L{pb.Error} but not
        known on the client side has its type set properly.
        """

        def failureUnknown(fail):
            self.assertEqual(
                fail.type, b"twisted.spread.test.test_pbfailure.UnknownError"
            )
            return 4310

        return self._testImpl("unknownError", 4310, failureUnknown)

    def test_securityFailure(self):
        """
        Test that even if an exception is not explicitly jellyable (by being
        a L{pb.Jellyable} subclass), as long as it is an L{pb.Error}
        subclass it receives the same special treatment.
        """

        def failureSecurity(fail):
            fail.trap(SecurityError)
            self.assertNotIsInstance(fail.type, str)
            self.assertIsInstance(fail.value, fail.type)
            return 4300

        return self._testImpl("security", 4300, failureSecurity)

    def test_deferredSecurity(self):
        """
        Test that a Deferred which fails with a L{pb.Error} which is not
        also a L{pb.Jellyable} is treated in the same way as a synchronously
        raised exception of the same type.
        """

        def failureDeferredSecurity(fail):
            fail.trap(SecurityError)
            self.assertNotIsInstance(fail.type, str)
            self.assertIsInstance(fail.value, fail.type)
            return 43000

        return self._testImpl("deferredSecurity", 43000, failureDeferredSecurity)

    def test_noSuchMethodFailure(self):
        """
        Test that attempting to call a method which is not defined correctly
        results in an AttributeError on the calling side.
        """

        def failureNoSuch(fail):
            fail.trap(pb.NoSuchMethod)
            self.compare(fail.traceback, "Traceback unavailable\n")
            return 42000

        return self._testImpl("nosuch", 42000, failureNoSuch, AttributeError)

    def test_copiedFailureLogging(self):
        """
        Test that a copied failure received from a PB call can be logged
        locally.

        Note: this test needs some serious help: all it really tests is that
        log.err(copiedFailure) doesn't raise an exception.
        """
        d = self.clientFactory.getRootObject()

        def connected(rootObj):
            return rootObj.callRemote("synchronousException")

        d.addCallback(connected)

        def exception(failure):
            log.err(failure)
            errs = self.flushLoggedErrors(SynchronousException)
            self.assertEqual(len(errs), 2)

        d.addErrback(exception)

        return d

    def test_throwExceptionIntoGenerator(self):
        """
        L{pb.CopiedFailure.throwExceptionIntoGenerator} will throw a
        L{RemoteError} into the given paused generator at the point where it
        last yielded.
        """
        original = pb.CopyableFailure(AttributeError("foo"))
        copy = jelly.unjelly(jelly.jelly(original, invoker=DummyInvoker()))
        exception = []

        def generatorFunc():
            try:
                yield None
            except pb.RemoteError as exc:
                exception.append(exc)
            else:
                self.fail("RemoteError not raised")

        gen = generatorFunc()
        gen.send(None)
        self.assertRaises(StopIteration, copy.throwExceptionIntoGenerator, gen)
        self.assertEqual(len(exception), 1)
        exc = exception[0]
        self.assertEqual(exc.remoteType, qual(AttributeError).encode("ascii"))
        self.assertEqual(exc.args, ("foo",))
        self.assertEqual(exc.remoteTraceback, "Traceback unavailable\n")


class PBFailureUnsafeTests(PBFailureTests):
    compare = unittest.TestCase.failIfEquals
    unsafeTracebacks = 1


class DummyInvoker:
    """
    A behaviorless object to be used as the invoker parameter to
    L{jelly.jelly}.
    """

    serializingPerspective = None


class FailureJellyingTests(unittest.TestCase):
    """
    Tests for the interaction of jelly and failures.
    """

    def test_unjelliedFailureCheck(self):
        """
        An unjellied L{CopyableFailure} has a check method which behaves the
        same way as the original L{CopyableFailure}'s check method.
        """
        original = pb.CopyableFailure(ZeroDivisionError())
        self.assertIs(original.check(ZeroDivisionError), ZeroDivisionError)
        self.assertIs(original.check(ArithmeticError), ArithmeticError)
        copied = jelly.unjelly(jelly.jelly(original, invoker=DummyInvoker()))
        self.assertIs(copied.check(ZeroDivisionError), ZeroDivisionError)
        self.assertIs(copied.check(ArithmeticError), ArithmeticError)

    def test_twiceUnjelliedFailureCheck(self):
        """
        The object which results from jellying a L{CopyableFailure}, unjellying
        the result, creating a new L{CopyableFailure} from the result of that,
        jellying it, and finally unjellying the result of that has a check
        method which behaves the same way as the original L{CopyableFailure}'s
        check method.
        """
        original = pb.CopyableFailure(ZeroDivisionError())
        self.assertIs(original.check(ZeroDivisionError), ZeroDivisionError)
        self.assertIs(original.check(ArithmeticError), ArithmeticError)
        copiedOnce = jelly.unjelly(jelly.jelly(original, invoker=DummyInvoker()))
        derivative = pb.CopyableFailure(copiedOnce)
        copiedTwice = jelly.unjelly(jelly.jelly(derivative, invoker=DummyInvoker()))
        self.assertIs(copiedTwice.check(ZeroDivisionError), ZeroDivisionError)
        self.assertIs(copiedTwice.check(ArithmeticError), ArithmeticError)

    def test_printTracebackIncludesValue(self):
        """
        When L{CopiedFailure.printTraceback} is used to print a copied failure
        which was unjellied from a L{CopyableFailure} with C{unsafeTracebacks}
        set to C{False}, the string representation of the exception value is
        included in the output.
        """
        original = pb.CopyableFailure(Exception("some reason"))
        copied = jelly.unjelly(jelly.jelly(original, invoker=DummyInvoker()))
        output = StringIO()
        copied.printTraceback(output)
        exception = qual(Exception)
        expectedOutput = "Traceback from remote host -- " "{}: some reason\n".format(
            exception
        )
        self.assertEqual(expectedOutput, output.getvalue())
