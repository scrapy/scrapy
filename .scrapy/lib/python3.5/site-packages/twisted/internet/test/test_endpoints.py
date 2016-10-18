# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test the C{I...Endpoint} implementations that wrap the L{IReactorTCP},
L{IReactorSSL}, and L{IReactorUNIX} interfaces found in
L{twisted.internet.endpoints}.
"""
from __future__ import division, absolute_import

import socket

from errno import EPERM
from socket import AF_INET, AF_INET6, SOCK_STREAM, IPPROTO_TCP
from zope.interface import implementer
from zope.interface.verify import verifyObject, verifyClass
from types import FunctionType

from twisted.trial import unittest
from twisted.test.proto_helpers import MemoryReactorClock as MemoryReactor
from twisted.test.proto_helpers import RaisingMemoryReactor, StringTransport
from twisted.test.proto_helpers import StringTransportWithDisconnection

from twisted import plugins
from twisted.internet import error, interfaces, defer, endpoints, protocol
from twisted.internet import reactor, threads, stdio
from twisted.internet.address import IPv4Address, IPv6Address, UNIXAddress
from twisted.internet.address import _ProcessAddress, HostnameAddress
from twisted.internet.endpoints import StandardErrorBehavior
from twisted.internet.interfaces import IConsumer, IPushProducer, ITransport
from twisted.internet.protocol import ClientFactory, Protocol, Factory
from twisted.internet.stdio import PipeAddress
from twisted.internet.task import Clock
from twisted.plugin import getPlugins
from twisted.python import log
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.modules import getModule
from twisted.python.systemd import ListenFDs
from twisted.protocols import basic, policies
from twisted.test.iosim import connectedServerAndClient, connectableEndpoint
from twisted.internet.error import ConnectingCancelledError
from twisted.python.compat import nativeString

pemPath = getModule("twisted.test").filePath.sibling("server.pem")
casPath = getModule(__name__).filePath.sibling("fake_CAs")
chainPath = casPath.child("chain.pem")
escapedPEMPathName = endpoints.quoteStringArgument(pemPath.path)
escapedCAsPathName = endpoints.quoteStringArgument(casPath.path)
escapedChainPathName = endpoints.quoteStringArgument(chainPath.path)


try:
    from twisted.test.test_sslverify import makeCertificate
    from twisted.internet.ssl import (
        PrivateCertificate, Certificate, CertificateOptions, KeyPair,
        DiffieHellmanParameters
    )
    from twisted.protocols.tls import TLSMemoryBIOFactory
    from OpenSSL.SSL import (
        ContextType, SSLv23_METHOD, TLSv1_METHOD, OP_NO_SSLv3
    )
    testCertificate = Certificate.loadPEM(pemPath.getContent())
    testPrivateCertificate = PrivateCertificate.loadPEM(pemPath.getContent())

    skipSSL = False
except ImportError:
    skipSSL = "OpenSSL is required to construct SSL Endpoints"



class TestProtocol(Protocol):
    """
    Protocol whose only function is to callback deferreds on the
    factory when it is connected or disconnected.
    """

    def __init__(self):
        self.data = []
        self.connectionsLost = []
        self.connectionMadeCalls = 0


    def logPrefix(self):
        return "A Test Protocol"


    def connectionMade(self):
        self.connectionMadeCalls += 1


    def dataReceived(self, data):
        self.data.append(data)


    def connectionLost(self, reason):
        self.connectionsLost.append(reason)



@implementer(interfaces.IHalfCloseableProtocol)
class TestHalfCloseableProtocol(TestProtocol):
    """
    A Protocol that implements L{IHalfCloseableProtocol} and records whether
    its C{readConnectionLost} and {writeConnectionLost} methods are called.

    @ivar readLost: A C{bool} indicating whether C{readConnectionLost} has been
        called.

    @ivar writeLost: A C{bool} indicating whether C{writeConnectionLost} has
        been called.
    """

    def __init__(self):
        TestProtocol.__init__(self)
        self.readLost = False
        self.writeLost = False


    def readConnectionLost(self):
        self.readLost = True


    def writeConnectionLost(self):
        self.writeLost = True



@implementer(interfaces.IFileDescriptorReceiver)
class TestFileDescriptorReceiverProtocol(TestProtocol):
    """
    A Protocol that implements L{IFileDescriptorReceiver} and records how its
    C{fileDescriptorReceived} method is called.

    @ivar receivedDescriptors: A C{list} containing all of the file descriptors
        passed to C{fileDescriptorReceived} calls made on this instance.
    """

    def connectionMade(self):
        TestProtocol.connectionMade(self)
        self.receivedDescriptors = []


    def fileDescriptorReceived(self, descriptor):
        self.receivedDescriptors.append(descriptor)



class TestFactory(ClientFactory):
    """
    Simple factory to be used both when connecting and listening. It contains
    two deferreds which are called back when my protocol connects and
    disconnects.
    """
    protocol = TestProtocol



class NoneFactory(ClientFactory):
    """
    A one off factory whose C{buildProtocol} returns L{None}.
    """
    def buildProtocol(self, addr):
        return None



class WrappingFactoryTests(unittest.TestCase):
    """
    Test the behaviour of our ugly implementation detail C{_WrappingFactory}.
    """
    def test_doStart(self):
        """
        L{_WrappingFactory.doStart} passes through to the wrapped factory's
        C{doStart} method, allowing application-specific setup and logging.
        """
        factory = ClientFactory()
        wf = endpoints._WrappingFactory(factory)
        wf.doStart()
        self.assertEqual(1, factory.numPorts)


    def test_doStop(self):
        """
        L{_WrappingFactory.doStop} passes through to the wrapped factory's
        C{doStop} method, allowing application-specific cleanup and logging.
        """
        factory = ClientFactory()
        factory.numPorts = 3
        wf = endpoints._WrappingFactory(factory)
        wf.doStop()
        self.assertEqual(2, factory.numPorts)


    def test_failedBuildProtocol(self):
        """
        An exception raised in C{buildProtocol} of our wrappedFactory
        results in our C{onConnection} errback being fired.
        """
        class BogusFactory(ClientFactory):
            """
            A one off factory whose C{buildProtocol} raises an C{Exception}.
            """

            def buildProtocol(self, addr):
                raise ValueError("My protocol is poorly defined.")

        wf = endpoints._WrappingFactory(BogusFactory())

        wf.buildProtocol(None)

        d = self.assertFailure(wf._onConnection, ValueError)
        d.addCallback(lambda e: self.assertEqual(
            e.args,
            ("My protocol is poorly defined.",)))

        return d


    def test_buildNoneProtocol(self):
        """
        If the wrapped factory's C{buildProtocol} returns L{None} the
        C{onConnection} errback fires with L{error.NoProtocol}.
        """
        wrappingFactory = endpoints._WrappingFactory(NoneFactory())
        wrappingFactory.buildProtocol(None)
        self.failureResultOf(wrappingFactory._onConnection, error.NoProtocol)


    def test_buildProtocolReturnsNone(self):
        """
        If the wrapped factory's C{buildProtocol} returns L{None} then
        L{endpoints._WrappingFactory.buildProtocol} returns L{None}.
        """
        wrappingFactory = endpoints._WrappingFactory(NoneFactory())
        # Discard the failure this Deferred will get
        wrappingFactory._onConnection.addErrback(lambda reason: None)

        self.assertIsNone(wrappingFactory.buildProtocol(None))


    def test_logPrefixPassthrough(self):
        """
        If the wrapped protocol provides L{ILoggingContext}, whatever is
        returned from the wrapped C{logPrefix} method is returned from
        L{_WrappingProtocol.logPrefix}.
        """
        wf = endpoints._WrappingFactory(TestFactory())
        wp = wf.buildProtocol(None)
        self.assertEqual(wp.logPrefix(), "A Test Protocol")


    def test_logPrefixDefault(self):
        """
        If the wrapped protocol does not provide L{ILoggingContext}, the
        wrapped protocol's class name is returned from
        L{_WrappingProtocol.logPrefix}.
        """
        class NoProtocol(object):
            pass
        factory = TestFactory()
        factory.protocol = NoProtocol
        wf = endpoints._WrappingFactory(factory)
        wp = wf.buildProtocol(None)
        self.assertEqual(wp.logPrefix(), "NoProtocol")


    def test_wrappedProtocolDataReceived(self):
        """
        The wrapped C{Protocol}'s C{dataReceived} will get called when our
        C{_WrappingProtocol}'s C{dataReceived} gets called.
        """
        wf = endpoints._WrappingFactory(TestFactory())
        p = wf.buildProtocol(None)
        p.makeConnection(None)

        p.dataReceived(b'foo')
        self.assertEqual(p._wrappedProtocol.data, [b'foo'])

        p.dataReceived(b'bar')
        self.assertEqual(p._wrappedProtocol.data, [b'foo', b'bar'])


    def test_wrappedProtocolTransport(self):
        """
        Our transport is properly hooked up to the wrappedProtocol when a
        connection is made.
        """
        wf = endpoints._WrappingFactory(TestFactory())
        p = wf.buildProtocol(None)

        dummyTransport = object()

        p.makeConnection(dummyTransport)

        self.assertEqual(p.transport, dummyTransport)

        self.assertEqual(p._wrappedProtocol.transport, dummyTransport)


    def test_wrappedProtocolConnectionLost(self):
        """
        Our wrappedProtocol's connectionLost method is called when
        L{_WrappingProtocol.connectionLost} is called.
        """
        tf = TestFactory()
        wf = endpoints._WrappingFactory(tf)
        p = wf.buildProtocol(None)

        p.connectionLost("fail")

        self.assertEqual(p._wrappedProtocol.connectionsLost, ["fail"])


    def test_clientConnectionFailed(self):
        """
        Calls to L{_WrappingFactory.clientConnectionLost} should errback the
        L{_WrappingFactory._onConnection} L{Deferred}
        """
        wf = endpoints._WrappingFactory(TestFactory())
        expectedFailure = Failure(error.ConnectError(string="fail"))

        wf.clientConnectionFailed(None, expectedFailure)

        errors = []

        def gotError(f):
            errors.append(f)

        wf._onConnection.addErrback(gotError)

        self.assertEqual(errors, [expectedFailure])


    def test_wrappingProtocolFileDescriptorReceiver(self):
        """
        Our L{_WrappingProtocol} should be an L{IFileDescriptorReceiver} if the
        wrapped protocol is.
        """
        connectedDeferred = None
        applicationProtocol = TestFileDescriptorReceiverProtocol()
        wrapper = endpoints._WrappingProtocol(
            connectedDeferred, applicationProtocol)
        self.assertTrue(interfaces.IFileDescriptorReceiver.providedBy(wrapper))
        self.assertTrue(
            verifyObject(interfaces.IFileDescriptorReceiver, wrapper))


    def test_wrappingProtocolNotFileDescriptorReceiver(self):
        """
        Our L{_WrappingProtocol} does not provide L{IHalfCloseableProtocol} if
        the wrapped protocol doesn't.
        """
        tp = TestProtocol()
        p = endpoints._WrappingProtocol(None, tp)
        self.assertFalse(interfaces.IFileDescriptorReceiver.providedBy(p))


    def test_wrappedProtocolFileDescriptorReceived(self):
        """
        L{_WrappingProtocol.fileDescriptorReceived} calls the wrapped
        protocol's C{fileDescriptorReceived} method.
        """
        wrappedProtocol = TestFileDescriptorReceiverProtocol()
        wrapper = endpoints._WrappingProtocol(
            defer.Deferred(), wrappedProtocol)
        wrapper.makeConnection(StringTransport())
        wrapper.fileDescriptorReceived(42)
        self.assertEqual(wrappedProtocol.receivedDescriptors, [42])


    def test_wrappingProtocolHalfCloseable(self):
        """
        Our L{_WrappingProtocol} should be an L{IHalfCloseableProtocol} if the
        C{wrappedProtocol} is.
        """
        cd = object()
        hcp = TestHalfCloseableProtocol()
        p = endpoints._WrappingProtocol(cd, hcp)
        self.assertEqual(
            interfaces.IHalfCloseableProtocol.providedBy(p), True)


    def test_wrappingProtocolNotHalfCloseable(self):
        """
        Our L{_WrappingProtocol} should not provide L{IHalfCloseableProtocol}
        if the C{WrappedProtocol} doesn't.
        """
        tp = TestProtocol()
        p = endpoints._WrappingProtocol(None, tp)
        self.assertEqual(
            interfaces.IHalfCloseableProtocol.providedBy(p), False)


    def test_wrappedProtocolReadConnectionLost(self):
        """
        L{_WrappingProtocol.readConnectionLost} should proxy to the wrapped
        protocol's C{readConnectionLost}
        """
        hcp = TestHalfCloseableProtocol()
        p = endpoints._WrappingProtocol(None, hcp)
        p.readConnectionLost()
        self.assertTrue(hcp.readLost)


    def test_wrappedProtocolWriteConnectionLost(self):
        """
        L{_WrappingProtocol.writeConnectionLost} should proxy to the wrapped
        protocol's C{writeConnectionLost}
        """
        hcp = TestHalfCloseableProtocol()
        p = endpoints._WrappingProtocol(None, hcp)
        p.writeConnectionLost()
        self.assertTrue(hcp.writeLost)



class ClientEndpointTestCaseMixin(object):
    """
    Generic test methods to be mixed into all client endpoint test classes.
    """
    def test_interface(self):
        """
        The endpoint provides L{interfaces.IStreamClientEndpoint}
        """
        clientFactory = object()
        ep, ignoredArgs, address = self.createClientEndpoint(
            MemoryReactor(), clientFactory)
        self.assertTrue(verifyObject(interfaces.IStreamClientEndpoint, ep))


    def retrieveConnectedFactory(self, reactor):
        """
        Retrieve a single factory that has connected using the given reactor.
        (This behavior is valid for TCP and SSL but needs to be overridden for
        UNIX.)

        @param reactor: a L{MemoryReactor}
        """
        return self.expectedClients(reactor)[0][2]


    def test_endpointConnectSuccess(self):
        """
        A client endpoint can connect and returns a deferred who gets called
        back with a protocol instance.
        """
        proto = object()
        mreactor = MemoryReactor()

        clientFactory = object()

        ep, expectedArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)

        receivedProtos = []

        def checkProto(p):
            receivedProtos.append(p)

        d.addCallback(checkProto)

        factory = self.retrieveConnectedFactory(mreactor)
        factory._onConnection.callback(proto)
        self.assertEqual(receivedProtos, [proto])

        expectedClients = self.expectedClients(mreactor)

        self.assertEqual(len(expectedClients), 1)
        self.assertConnectArgs(expectedClients[0], expectedArgs)


    def test_endpointConnectFailure(self):
        """
        If an endpoint tries to connect to a non-listening port it gets
        a C{ConnectError} failure.
        """
        expectedError = error.ConnectError(string="Connection Failed")

        mreactor = RaisingMemoryReactor(connectException=expectedError)

        clientFactory = object()

        ep, ignoredArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)

        receivedExceptions = []

        def checkFailure(f):
            receivedExceptions.append(f.value)

        d.addErrback(checkFailure)

        self.assertEqual(receivedExceptions, [expectedError])


    def test_endpointConnectingCancelled(self):
        """
        Calling L{Deferred.cancel} on the L{Deferred} returned from
        L{IStreamClientEndpoint.connect} is errbacked with an expected
        L{ConnectingCancelledError} exception.
        """
        mreactor = MemoryReactor()

        clientFactory = object()

        ep, ignoredArgs, address = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)

        receivedFailures = []

        def checkFailure(f):
            receivedFailures.append(f)

        d.addErrback(checkFailure)

        d.cancel()
        # When canceled, the connector will immediately notify its factory that
        # the connection attempt has failed due to a UserError.
        attemptFactory = self.retrieveConnectedFactory(mreactor)
        attemptFactory.clientConnectionFailed(None, Failure(error.UserError()))
        # This should be a feature of MemoryReactor: <http://tm.tl/5630>.

        self.assertEqual(len(receivedFailures), 1)

        failure = receivedFailures[0]

        self.assertIsInstance(failure.value, error.ConnectingCancelledError)
        self.assertEqual(failure.value.address, address)


    def test_endpointConnectNonDefaultArgs(self):
        """
        The endpoint should pass it's connectArgs parameter to the reactor's
        listen methods.
        """
        factory = object()

        mreactor = MemoryReactor()

        ep, expectedArgs, ignoredHost = self.createClientEndpoint(
            mreactor, factory,
            **self.connectArgs())

        ep.connect(factory)

        expectedClients = self.expectedClients(mreactor)

        self.assertEqual(len(expectedClients), 1)
        self.assertConnectArgs(expectedClients[0], expectedArgs)



class ServerEndpointTestCaseMixin(object):
    """
    Generic test methods to be mixed into all client endpoint test classes.
    """
    def test_interface(self):
        """
        The endpoint provides L{interfaces.IStreamServerEndpoint}.
        """
        factory = object()
        ep, ignoredArgs, ignoredDest = self.createServerEndpoint(
            MemoryReactor(), factory)
        self.assertTrue(verifyObject(interfaces.IStreamServerEndpoint, ep))


    def test_endpointListenSuccess(self):
        """
        An endpoint can listen and returns a deferred that gets called back
        with a port instance.
        """
        mreactor = MemoryReactor()

        factory = object()

        ep, expectedArgs, expectedHost = self.createServerEndpoint(
            mreactor, factory)

        d = ep.listen(factory)

        receivedHosts = []

        def checkPortAndServer(port):
            receivedHosts.append(port.getHost())

        d.addCallback(checkPortAndServer)

        self.assertEqual(receivedHosts, [expectedHost])
        self.assertEqual(self.expectedServers(mreactor), [expectedArgs])


    def test_endpointListenFailure(self):
        """
        When an endpoint tries to listen on an already listening port, a
        C{CannotListenError} failure is errbacked.
        """
        factory = object()
        exception = error.CannotListenError('', 80, factory)
        mreactor = RaisingMemoryReactor(listenException=exception)

        ep, ignoredArgs, ignoredDest = self.createServerEndpoint(
            mreactor, factory)

        d = ep.listen(object())

        receivedExceptions = []

        def checkFailure(f):
            receivedExceptions.append(f.value)

        d.addErrback(checkFailure)

        self.assertEqual(receivedExceptions, [exception])


    def test_endpointListenNonDefaultArgs(self):
        """
        The endpoint should pass it's listenArgs parameter to the reactor's
        listen methods.
        """
        factory = object()

        mreactor = MemoryReactor()

        ep, expectedArgs, ignoredHost = self.createServerEndpoint(
            mreactor, factory,
            **self.listenArgs())

        ep.listen(factory)

        expectedServers = self.expectedServers(mreactor)

        self.assertEqual(expectedServers, [expectedArgs])



class EndpointTestCaseMixin(ServerEndpointTestCaseMixin,
                            ClientEndpointTestCaseMixin):
    """
    Generic test methods to be mixed into all endpoint test classes.
    """



class SpecificFactory(Factory):
    """
    An L{IProtocolFactory} whose C{buildProtocol} always returns its
    C{specificProtocol} and sets C{passedAddress}.

    Raising an exception if C{specificProtocol} has already been used.
    """
    def __init__(self, specificProtocol):
        self.specificProtocol = specificProtocol


    def buildProtocol(self, addr):
        if hasattr(self.specificProtocol, 'passedAddress'):
            raise ValueError("specificProtocol already used.")
        self.specificProtocol.passedAddress = addr
        return self.specificProtocol



class FakeStdio(object):
    """
    A L{stdio.StandardIO} like object that simply captures its constructor
    arguments.
    """
    def __init__(self, protocolInstance, reactor=None):
        """
        @param protocolInstance: like the first argument of L{stdio.StandardIO}

        @param reactor: like the reactor keyword argument of
            L{stdio.StandardIO}
        """
        self.protocolInstance = protocolInstance
        self.reactor = reactor



class StandardIOEndpointsTests(unittest.TestCase):
    """
    Tests for Standard I/O Endpoints
    """

    def setUp(self):
        """
        Construct a L{StandardIOEndpoint} with a dummy reactor and a fake
        L{stdio.StandardIO} like object.  Listening on it with a
        L{SpecificFactory}.
        """
        self.reactor = object()
        endpoint = endpoints.StandardIOEndpoint(self.reactor)
        self.assertIs(endpoint._stdio, stdio.StandardIO)

        endpoint._stdio = FakeStdio
        self.specificProtocol = Protocol()

        self.fakeStdio = self.successResultOf(
            endpoint.listen(SpecificFactory(self.specificProtocol))
        )


    def test_protocolCreation(self):
        """
        L{StandardIOEndpoint} returns a L{Deferred} that fires with an instance
        of a L{stdio.StandardIO} like object that was passed the result of
        L{SpecificFactory.buildProtocol} which was passed a L{PipeAddress}.
        """
        self.assertIs(self.fakeStdio.protocolInstance,
                             self.specificProtocol)
        self.assertIsInstance(self.fakeStdio.protocolInstance.passedAddress,
                              PipeAddress)


    def test_passedReactor(self):
        """
        L{StandardIOEndpoint} passes its C{reactor} argument to the constructor
        of its L{stdio.StandardIO} like object.
        """
        self.assertIs(self.fakeStdio.reactor, self.reactor)



class StubApplicationProtocol(protocol.Protocol):
    """
    An L{IProtocol} provider.
    """
    def dataReceived(self, data):
        """
        @param data: The data received by the protocol.
        @type data: str
        """
        self.data = data


    def connectionLost(self, reason):
        """
        @type reason: L{twisted.python.failure.Failure}
        """
        self.reason = reason



@implementer(interfaces.IProcessTransport)
class MemoryProcessTransport(StringTransportWithDisconnection, object):
    """
    A fake L{IProcessTransport} provider to be used in tests.
    """

    def __init__(self, protocol=None):
        super(MemoryProcessTransport, self).__init__(
            hostAddress=_ProcessAddress(),
            peerAddress=_ProcessAddress())
        self.signals = []
        self.closedChildFDs = set()
        self.protocol = Protocol()


    def writeToChild(self, childFD, data):
        if childFD == 0:
            self.write(data)


    def closeStdin(self):
        self.closeChildFD(0)


    def closeStdout(self):
        self.closeChildFD(1)


    def closeStderr(self):
        self.closeChildFD(2)


    def closeChildFD(self, fd):
        self.closedChildFDs.add(fd)


    def signalProcess(self, signal):
        self.signals.append(signal)



verifyClass(interfaces.IConsumer, MemoryProcessTransport)
verifyClass(interfaces.IPushProducer, MemoryProcessTransport)
verifyClass(interfaces.IProcessTransport, MemoryProcessTransport)



@implementer(interfaces.IReactorProcess)
class MemoryProcessReactor(object):
    """
    A fake L{IReactorProcess} provider to be used in tests.
    """
    def spawnProcess(self, processProtocol, executable, args=(), env={},
                     path=None, uid=None, gid=None, usePTY=0, childFDs=None):
        """
        @ivar processProtocol: Stores the protocol passed to the reactor.
        @return: An L{IProcessTransport} provider.
        """
        self.processProtocol = processProtocol
        self.executable = executable
        self.args = args
        self.env = env
        self.path = path
        self.uid = uid
        self.gid = gid
        self.usePTY = usePTY
        self.childFDs = childFDs

        self.processTransport = MemoryProcessTransport()
        self.processProtocol.makeConnection(self.processTransport)
        return self.processTransport



class ProcessEndpointsTests(unittest.TestCase):
    """
    Tests for child process endpoints.
    """

    def setUp(self):
        self.reactor = MemoryProcessReactor()
        self.ep = endpoints.ProcessEndpoint(self.reactor, b'/bin/executable')
        self.factory = protocol.Factory()
        self.factory.protocol = StubApplicationProtocol


    def test_constructorDefaults(self):
        """
        Default values are set for the optional parameters in the endpoint.
        """
        self.assertIsInstance(self.ep._reactor, MemoryProcessReactor)
        self.assertEqual(self.ep._executable, b'/bin/executable')
        self.assertEqual(self.ep._args, ())
        self.assertEqual(self.ep._env, {})
        self.assertIsNone(self.ep._path)
        self.assertIsNone(self.ep._uid)
        self.assertIsNone(self.ep._gid)
        self.assertEqual(self.ep._usePTY, 0)
        self.assertIsNone(self.ep._childFDs)
        self.assertEqual(self.ep._errFlag, StandardErrorBehavior.LOG)


    def test_constructorNonDefaults(self):
        """
        The parameters passed to the endpoint are stored in it.
        """
        environ = {b'HOME': None}
        ep = endpoints.ProcessEndpoint(
            MemoryProcessReactor(), b'/bin/executable',
            [b'/bin/executable'], {b'HOME': environ[b'HOME']},
            b'/runProcessHere/', 1, 2, True, {3: 'w', 4: 'r', 5: 'r'},
            StandardErrorBehavior.DROP)

        self.assertIsInstance(ep._reactor, MemoryProcessReactor)
        self.assertEqual(ep._executable, b'/bin/executable')
        self.assertEqual(ep._args, [b'/bin/executable'])
        self.assertEqual(ep._env, {b'HOME': environ[b'HOME']})
        self.assertEqual(ep._path, b'/runProcessHere/')
        self.assertEqual(ep._uid, 1)
        self.assertEqual(ep._gid, 2)
        self.assertTrue(ep._usePTY)
        self.assertEqual(ep._childFDs, {3: 'w', 4: 'r', 5: 'r'})
        self.assertEqual(ep._errFlag, StandardErrorBehavior.DROP)


    def test_wrappedProtocol(self):
        """
        The wrapper function _WrapIProtocol gives an IProcessProtocol
        implementation that wraps over an IProtocol.
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol
        self.assertIsInstance(wpp, endpoints._WrapIProtocol)


    def test_spawnProcess(self):
        """
        The parameters for spawnProcess stored in the endpoint are passed when
        the endpoint's connect method is invoked.
        """
        environ = {b'HOME': None}

        memoryReactor = MemoryProcessReactor()
        ep = endpoints.ProcessEndpoint(
            memoryReactor, b'/bin/executable',
            [b'/bin/executable'], {b'HOME': environ[b'HOME']},
            b'/runProcessHere/', 1, 2, True, {3: 'w', 4: 'r', 5: 'r'})
        d = ep.connect(self.factory)
        self.successResultOf(d)

        self.assertIsInstance(memoryReactor.processProtocol,
                              endpoints._WrapIProtocol)
        self.assertEqual(memoryReactor.executable, ep._executable)
        self.assertEqual(memoryReactor.args, ep._args)
        self.assertEqual(memoryReactor.env, ep._env)
        self.assertEqual(memoryReactor.path, ep._path)
        self.assertEqual(memoryReactor.uid, ep._uid)
        self.assertEqual(memoryReactor.gid, ep._gid)
        self.assertEqual(memoryReactor.usePTY, ep._usePTY)
        self.assertEqual(memoryReactor.childFDs, ep._childFDs)


    def test_processAddress(self):
        """
        The address passed to the factory's buildProtocol in the endpoint is a
        _ProcessAddress instance.
        """

        class TestAddrFactory(protocol.Factory):
            protocol = StubApplicationProtocol
            address = None

            def buildProtocol(self, addr):
                self.address = addr
                p = self.protocol()
                p.factory = self
                return p

        myFactory = TestAddrFactory()
        d = self.ep.connect(myFactory)
        self.successResultOf(d)
        self.assertIsInstance(myFactory.address, _ProcessAddress)


    def test_connect(self):
        """
        L{ProcessEndpoint.connect} returns a Deferred with the connected
        protocol.
        """
        proto = self.successResultOf(self.ep.connect(self.factory))
        self.assertIsInstance(proto, StubApplicationProtocol)


    def test_connectFailure(self):
        """
        In case of failure, L{ProcessEndpoint.connect} returns a Deferred that
        fails.
        """

        def testSpawnProcess(pp, executable, args, env, path,
                             uid, gid, usePTY, childFDs):
            raise Exception()

        self.ep._spawnProcess = testSpawnProcess
        d = self.ep.connect(self.factory)
        error = self.failureResultOf(d)
        error.trap(Exception)



class ProcessEndpointTransportTests(unittest.TestCase):
    """
    Test the behaviour of the implementation detail
    L{endpoints._ProcessEndpointTransport}.
    """

    def setUp(self):
        self.reactor = MemoryProcessReactor()
        self.endpoint = endpoints.ProcessEndpoint(self.reactor,
                                                  b'/bin/executable')
        protocol = self.successResultOf(
            self.endpoint.connect(Factory.forProtocol(Protocol))
        )
        self.process = self.reactor.processTransport
        self.endpointTransport = protocol.transport


    def test_verifyConsumer(self):
        """
        L{_ProcessEndpointTransport}s provide L{IConsumer}.
        """
        verifyObject(IConsumer, self.endpointTransport)


    def test_verifyProducer(self):
        """
        L{_ProcessEndpointTransport}s provide L{IPushProducer}.
        """
        verifyObject(IPushProducer, self.endpointTransport)


    def test_verifyTransport(self):
        """
        L{_ProcessEndpointTransport}s provide L{ITransport}.
        """
        verifyObject(ITransport, self.endpointTransport)


    def test_constructor(self):
        """
        The L{_ProcessEndpointTransport} instance stores the process passed to
        it.
        """
        self.assertIs(self.endpointTransport._process, self.process)


    def test_registerProducer(self):
        """
        Registering a producer with the endpoint transport registers it with
        the underlying process transport.
        """
        @implementer(IPushProducer)
        class AProducer(object):
            pass
        aProducer = AProducer()
        self.endpointTransport.registerProducer(aProducer, False)
        self.assertIs(self.process.producer, aProducer)


    def test_pauseProducing(self):
        """
        Pausing the endpoint transport pauses the underlying process transport.
        """
        self.endpointTransport.pauseProducing()
        self.assertEqual(self.process.producerState, 'paused')


    def test_resumeProducing(self):
        """
        Resuming the endpoint transport resumes the underlying process
        transport.
        """
        self.test_pauseProducing()
        self.endpointTransport.resumeProducing()
        self.assertEqual(self.process.producerState, 'producing')


    def test_stopProducing(self):
        """
        Stopping the endpoint transport as a producer stops the underlying
        process transport.
        """
        self.endpointTransport.stopProducing()
        self.assertEqual(self.process.producerState, 'stopped')


    def test_unregisterProducer(self):
        """
        Unregistring the endpoint transport's producer unregisters the
        underlying process transport's producer.
        """
        self.test_registerProducer()
        self.endpointTransport.unregisterProducer()
        self.assertIsNone(self.process.producer)


    def test_extraneousAttributes(self):
        """
        L{endpoints._ProcessEndpointTransport} filters out extraneous
        attributes of its underlying transport, to present a more consistent
        cross-platform view of subprocesses and prevent accidental
        dependencies.
        """
        self.process.pipes = []
        self.assertRaises(AttributeError,
                          getattr, self.endpointTransport, 'pipes')


    def test_writeSequence(self):
        """
        The writeSequence method of L{_ProcessEndpointTransport} writes a list
        of string passed to it to the transport's stdin.
        """
        self.endpointTransport.writeSequence([b'test1', b'test2', b'test3'])
        self.assertEqual(self.process.io.getvalue(), b'test1test2test3')


    def test_write(self):
        """
        The write method of L{_ProcessEndpointTransport} writes a string of
        data passed to it to the child process's stdin.
        """
        self.endpointTransport.write(b'test')
        self.assertEqual(self.process.io.getvalue(), b'test')


    def test_loseConnection(self):
        """
        A call to the loseConnection method of a L{_ProcessEndpointTransport}
        instance returns a call to the process transport's loseConnection.
        """
        self.endpointTransport.loseConnection()
        self.assertFalse(self.process.connected)


    def test_getHost(self):
        """
        L{_ProcessEndpointTransport.getHost} returns a L{_ProcessAddress}
        instance matching the process C{getHost}.
        """
        host = self.endpointTransport.getHost()
        self.assertIsInstance(host, _ProcessAddress)
        self.assertIs(host, self.process.getHost())


    def test_getPeer(self):
        """
        L{_ProcessEndpointTransport.getPeer} returns a L{_ProcessAddress}
        instance matching the process C{getPeer}.
        """
        peer = self.endpointTransport.getPeer()
        self.assertIsInstance(peer, _ProcessAddress)
        self.assertIs(peer, self.process.getPeer())



class WrappedIProtocolTests(unittest.TestCase):
    """
    Test the behaviour of the implementation detail C{_WrapIProtocol}.
    """
    def setUp(self):
        self.reactor = MemoryProcessReactor()
        self.ep = endpoints.ProcessEndpoint(self.reactor, b'/bin/executable')
        self.eventLog = None
        self.factory = protocol.Factory()
        self.factory.protocol = StubApplicationProtocol


    def test_constructor(self):
        """
        Stores an L{IProtocol} provider and the flag to log/drop stderr
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol
        self.assertIsInstance(wpp.protocol, StubApplicationProtocol)
        self.assertEqual(wpp.errFlag, self.ep._errFlag)


    def test_makeConnection(self):
        """
        Our process transport is properly hooked up to the wrappedIProtocol
        when a connection is made.
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol
        self.assertEqual(wpp.protocol.transport, wpp.transport)


    def _stdLog(self, eventDict):
        """
        A log observer.
        """
        self.eventLog = eventDict


    def test_logStderr(self):
        """
        When the _errFlag is set to L{StandardErrorBehavior.LOG},
        L{endpoints._WrapIProtocol} logs stderr (in childDataReceived).
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol
        log.addObserver(self._stdLog)
        self.addCleanup(log.removeObserver, self._stdLog)

        wpp.childDataReceived(2, b'stderr1')
        self.assertEqual(self.eventLog['executable'], wpp.executable)
        self.assertEqual(self.eventLog['data'], b'stderr1')
        self.assertEqual(self.eventLog['protocol'], wpp.protocol)
        self.assertIn(
            'wrote stderr unhandled by',
            log.textFromEventDict(self.eventLog))


    def test_stderrSkip(self):
        """
        When the _errFlag is set to L{StandardErrorBehavior.DROP},
        L{endpoints._WrapIProtocol} ignores stderr.
        """
        self.ep._errFlag = StandardErrorBehavior.DROP
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol
        log.addObserver(self._stdLog)
        self.addCleanup(log.removeObserver, self._stdLog)

        wpp.childDataReceived(2, b'stderr2')
        self.assertIsNone(self.eventLog)


    def test_stdout(self):
        """
        In childDataReceived of L{_WrappedIProtocol} instance, the protocol's
        dataReceived is called when stdout is generated.
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol

        wpp.childDataReceived(1, b'stdout')
        self.assertEqual(wpp.protocol.data, b'stdout')


    def test_processDone(self):
        """
        L{error.ProcessDone} with status=0 is turned into a clean disconnect
        type, i.e. L{error.ConnectionDone}.
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol

        wpp.processEnded(Failure(error.ProcessDone(0)))
        self.assertEqual(
            wpp.protocol.reason.check(error.ConnectionDone),
            error.ConnectionDone)


    def test_processEnded(self):
        """
        Exceptions other than L{error.ProcessDone} with status=0 are turned
        into L{error.ConnectionLost}.
        """
        d = self.ep.connect(self.factory)
        self.successResultOf(d)
        wpp = self.reactor.processProtocol

        wpp.processEnded(Failure(error.ProcessTerminated()))
        self.assertEqual(wpp.protocol.reason.check(error.ConnectionLost),
                         error.ConnectionLost)



class TCP4EndpointsTests(EndpointTestCaseMixin, unittest.TestCase):
    """
    Tests for TCP IPv4 Endpoints.
    """

    def expectedServers(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.listenTCP}
        """
        return reactor.tcpServers


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.connectTCP}
        """
        return reactor.tcpClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, timeout, and bindAddress in C{receivedArgs}
        to C{expectedArgs}.  We ignore the factory because we don't
        only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that was passed to
            L{IReactorTCP.connectTCP}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that we expect to have been passed
            to L{IReactorTCP.connectTCP}.
        """
        (host, port, ignoredFactory, timeout, bindAddress) = receivedArgs
        (expectedHost, expectedPort, _ignoredFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def listenArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to listen
        """
        return {'backlog': 100, 'interface': '127.0.0.1'}


    def createServerEndpoint(self, reactor, factory, **listenArgs):
        """
        Create an L{TCP4ServerEndpoint} and return the values needed to verify
        its behaviour.

        @param reactor: A fake L{IReactorTCP} that L{TCP4ServerEndpoint} can
            call L{IReactorTCP.listenTCP} on.
        @param factory: The thing that we expect to be passed to our
            L{IStreamServerEndpoint.listen} implementation.
        @param listenArgs: Optional dictionary of arguments to
            L{IReactorTCP.listenTCP}.
        """
        address = IPv4Address("TCP", "0.0.0.0", 0)

        if listenArgs is None:
            listenArgs = {}

        return (endpoints.TCP4ServerEndpoint(reactor,
                                             address.port,
                                             **listenArgs),
                (address.port, factory,
                 listenArgs.get('backlog', 50),
                 listenArgs.get('interface', '')),
                address)


    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Create an L{TCP4ClientEndpoint} and return the values needed to verify
        its behavior.

        @param reactor: A fake L{IReactorTCP} that L{TCP4ClientEndpoint} can
            call L{IReactorTCP.connectTCP} on.
        @param clientFactory: The thing that we expect to be passed to our
            L{IStreamClientEndpoint.connect} implementation.
        @param connectArgs: Optional dictionary of arguments to
            L{IReactorTCP.connectTCP}
        """
        address = IPv4Address("TCP", "localhost", 80)

        return (endpoints.TCP4ClientEndpoint(reactor,
                                             address.host,
                                             address.port,
                                             **connectArgs),
                (address.host, address.port, clientFactory,
                 connectArgs.get('timeout', 30),
                 connectArgs.get('bindAddress', None)),
                address)



class TCP6EndpointsTests(EndpointTestCaseMixin, unittest.TestCase):
    """
    Tests for TCP IPv6 Endpoints.
    """

    def expectedServers(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.listenTCP}
        """
        return reactor.tcpServers


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.connectTCP}
        """
        return reactor.tcpClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, timeout, and bindAddress in C{receivedArgs}
        to C{expectedArgs}.  We ignore the factory because we don't
        only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that was passed to
            L{IReactorTCP.connectTCP}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that we expect to have been passed
            to L{IReactorTCP.connectTCP}.
        """
        (host, port, ignoredFactory, timeout, bindAddress) = receivedArgs
        (expectedHost, expectedPort, _ignoredFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def listenArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to listen
        """
        return {'backlog': 100, 'interface': '::1'}


    def createServerEndpoint(self, reactor, factory, **listenArgs):
        """
        Create a L{TCP6ServerEndpoint} and return the values needed to verify
        its behaviour.

        @param reactor: A fake L{IReactorTCP} that L{TCP6ServerEndpoint} can
            call L{IReactorTCP.listenTCP} on.
        @param factory: The thing that we expect to be passed to our
            L{IStreamServerEndpoint.listen} implementation.
        @param listenArgs: Optional dictionary of arguments to
            L{IReactorTCP.listenTCP}.
        """
        interface = listenArgs.get('interface', '::')
        address = IPv6Address("TCP", interface, 0)

        if listenArgs is None:
            listenArgs = {}

        return (endpoints.TCP6ServerEndpoint(reactor,
                                             address.port,
                                             **listenArgs),
                (address.port, factory,
                 listenArgs.get('backlog', 50),
                 interface),
                address)


    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Create a L{TCP6ClientEndpoint} and return the values needed to verify
        its behavior.

        @param reactor: A fake L{IReactorTCP} that L{TCP6ClientEndpoint} can
            call L{IReactorTCP.connectTCP} on.
        @param clientFactory: The thing that we expect to be passed to our
            L{IStreamClientEndpoint.connect} implementation.
        @param connectArgs: Optional dictionary of arguments to
            L{IReactorTCP.connectTCP}
        """
        address = IPv6Address("TCP", "::1", 80)

        return (endpoints.TCP6ClientEndpoint(reactor,
                                             address.host,
                                             address.port,
                                             **connectArgs),
                (address.host, address.port, clientFactory,
                 connectArgs.get('timeout', 30),
                 connectArgs.get('bindAddress', None)),
                address)



class TCP6EndpointNameResolutionTests(ClientEndpointTestCaseMixin,
                                      unittest.TestCase):
    """
    Tests for a TCP IPv6 Client Endpoint pointed at a hostname instead
    of an IPv6 address literal.
    """
    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Create a L{TCP6ClientEndpoint} and return the values needed to verify
        its behavior.

        @param reactor: A fake L{IReactorTCP} that L{TCP6ClientEndpoint} can
            call L{IReactorTCP.connectTCP} on.
        @param clientFactory: The thing that we expect to be passed to our
            L{IStreamClientEndpoint.connect} implementation.
        @param connectArgs: Optional dictionary of arguments to
            L{IReactorTCP.connectTCP}
        """
        address = IPv6Address("TCP", "::2", 80)
        self.ep = endpoints.TCP6ClientEndpoint(
            reactor, 'ipv6.example.com', address.port, **connectArgs)

        def testNameResolution(host):
            self.assertEqual("ipv6.example.com", host)
            data = [(AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('::2', 0, 0, 0)),
                    (AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('::3', 0, 0, 0)),
                    (AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('::4', 0, 0, 0))]
            return defer.succeed(data)

        self.ep._nameResolution = testNameResolution

        return (self.ep,
                (address.host, address.port, clientFactory,
                 connectArgs.get('timeout', 30),
                 connectArgs.get('bindAddress', None)),
                address)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.connectTCP}
        """
        return reactor.tcpClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, timeout, and bindAddress in C{receivedArgs}
        to C{expectedArgs}.  We ignore the factory because we don't
        only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that was passed to
            L{IReactorTCP.connectTCP}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that we expect to have been passed
            to L{IReactorTCP.connectTCP}.
        """
        (host, port, ignoredFactory, timeout, bindAddress) = receivedArgs
        (expectedHost, expectedPort, _ignoredFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def test_freeFunctionDeferToThread(self):
        """
        By default, L{TCP6ClientEndpoint._deferToThread} is
        L{threads.deferToThread}.
        """
        ep = endpoints.TCP6ClientEndpoint(None, 'www.example.com', 1234)
        self.assertEqual(ep._deferToThread, threads.deferToThread)


    def test_nameResolution(self):
        """
        While resolving hostnames, _nameResolution calls
        _deferToThread with _getaddrinfo.
        """
        calls = []

        def fakeDeferToThread(f, *args, **kwargs):
            calls.append((f, args, kwargs))
            return defer.Deferred()

        endpoint = endpoints.TCP6ClientEndpoint(
            reactor, 'ipv6.example.com', 1234)
        fakegetaddrinfo = object()
        endpoint._getaddrinfo = fakegetaddrinfo
        endpoint._deferToThread = fakeDeferToThread
        endpoint.connect(TestFactory())
        self.assertEqual(
            [(fakegetaddrinfo, ("ipv6.example.com", 0, AF_INET6), {})], calls)



class RaisingMemoryReactorWithClock(RaisingMemoryReactor, Clock):
    """
    An extension of L{RaisingMemoryReactor} with L{task.Clock}.
    """
    def __init__(self, listenException=None, connectException=None):
        Clock.__init__(self)
        RaisingMemoryReactor.__init__(self, listenException, connectException)



class HostnameEndpointsOneIPv4Tests(ClientEndpointTestCaseMixin,
                                    unittest.TestCase):
    """
    Tests for the hostname based endpoints when GAI returns only one
    (IPv4) address.
    """
    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Creates a L{HostnameEndpoint} instance where the hostname is resolved
        into a single IPv4 address.
        """
        address = HostnameAddress(b"example.com", 80)
        endpoint = endpoints.HostnameEndpoint(reactor, b"example.com",
                                           address.port, **connectArgs)

        def testNameResolution(host, port):
            self.assertEqual(b"example.com", host)
            data = [(AF_INET, SOCK_STREAM, IPPROTO_TCP, '', ('1.2.3.4', port))]
            return defer.succeed(data)

        endpoint._nameResolution = testNameResolution

        return (endpoint, ('1.2.3.4', address.port, clientFactory,
                connectArgs.get('timeout', 30),
                connectArgs.get('bindAddress', None)),
                address)


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.connectTCP}
        """
        return reactor.tcpClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, timeout, and bindAddress in C{receivedArgs}
        to C{expectedArgs}.  We ignore the factory because we don't
        only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that was passed to
            L{IReactorTCP.connectTCP}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that we expect to have been passed
            to L{IReactorTCP.connectTCP}.
        """
        (host, port, ignoredFactory, timeout, bindAddress) = receivedArgs
        (expectedHost, expectedPort, _ignoredFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def test_freeFunctionDeferToThread(self):
        """
        By default, L{HostnameEndpoint._deferToThread} is
        L{threads.deferToThread}.
        """
        mreactor = None
        clientFactory = None
        ep, ignoredArgs, address = self.createClientEndpoint(
                mreactor, clientFactory)

        self.assertEqual(ep._deferToThread, threads.deferToThread)


    def test_defaultGAI(self):
        """
        By default, L{HostnameEndpoint._getaddrinfo} is L{socket.getaddrinfo}.
        """
        mreactor = None
        clientFactory = None
        ep, ignoredArgs, address = self.createClientEndpoint(mreactor,
                clientFactory)
        self.assertEqual(ep._getaddrinfo, socket.getaddrinfo)


    def test_endpointConnectingCancelled(self, advance=None):
        """
        Calling L{Deferred.cancel} on the L{Deferred} returned from
        L{IStreamClientEndpoint.connect} will cause it to be errbacked with a
        L{ConnectingCancelledError} exception.
        """
        mreactor = MemoryReactor()

        clientFactory = protocol.Factory()
        clientFactory.protocol = protocol.Protocol

        ep, ignoredArgs, address = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)
        if advance is not None:
            mreactor.advance(advance)
        d.cancel()
        # When canceled, the connector will immediately notify its factory that
        # the connection attempt has failed due to a UserError.
        attemptFactory = self.retrieveConnectedFactory(mreactor)
        attemptFactory.clientConnectionFailed(None, Failure(error.UserError()))
        # This should be a feature of MemoryReactor: <http://tm.tl/5630>.

        failure = self.failureResultOf(d)

        self.assertIsInstance(failure.value, error.ConnectingCancelledError)
        self.assertEqual(failure.value.address, address)
        self.assertTrue(mreactor.tcpClients[0][2]._connector.stoppedConnecting)
        self.assertEqual([], mreactor.getDelayedCalls())


    def test_endpointConnectingCancelledAfterAllAttemptsStarted(self):
        """
        Calling L{Deferred.cancel} on the L{Deferred} returned from
        L{IStreamClientEndpoint.connect} after enough time has passed that all
        connection attempts have been initiated will cause it to be errbacked
        with a L{ConnectingCancelledError} exception.
        """
        oneBetween = endpoints.HostnameEndpoint._DEFAULT_ATTEMPT_DELAY
        advance = oneBetween + (oneBetween / 2.0)
        self.test_endpointConnectingCancelled(advance=advance)


    def test_endpointConnectFailure(self):
        """
        If L{HostnameEndpoint.connect} is invoked and there is no server
        listening for connections, the returned L{Deferred} will fail with
        C{ConnectError}.
        """
        expectedError = error.ConnectError(string="Connection Failed")

        mreactor = RaisingMemoryReactorWithClock(
                connectException=expectedError)

        clientFactory = object()

        ep, ignoredArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)
        mreactor.advance(endpoints.HostnameEndpoint._DEFAULT_ATTEMPT_DELAY)
        self.assertEqual(self.failureResultOf(d).value, expectedError)
        self.assertEqual([], mreactor.getDelayedCalls())


    def test_endpointConnectFailureAfterIteration(self):
        """
        If a connection attempt initiated by
        L{HostnameEndpoint.connect} fails only after
        L{HostnameEndpoint} has exhausted the list of possible server
        addresses, the returned L{Deferred} will fail with
        C{ConnectError}.
        """
        expectedError = error.ConnectError(string="Connection Failed")

        mreactor = MemoryReactor()

        clientFactory = object()

        ep, ignoredArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)
        mreactor.advance(0.3)
        host, port, factory, timeout, bindAddress = mreactor.tcpClients[0]
        factory.clientConnectionFailed(mreactor.connectors[0], expectedError)
        self.assertEqual(self.failureResultOf(d).value, expectedError)
        self.assertEqual([], mreactor.getDelayedCalls())


    def test_endpointConnectSuccessAfterIteration(self):
        """
        If a connection attempt initiated by
        L{HostnameEndpoint.connect} succeeds only after
        L{HostnameEndpoint} has exhausted the list of possible server
        addresses, the returned L{Deferred} will fire with the
        connected protocol instance and the endpoint will leave no
        delayed calls in the reactor.
        """
        proto = object()
        mreactor = MemoryReactor()

        clientFactory = object()

        ep, expectedArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)

        receivedProtos = []

        def checkProto(p):
            receivedProtos.append(p)

        d.addCallback(checkProto)

        factory = self.retrieveConnectedFactory(mreactor)

        mreactor.advance(0.3)

        factory._onConnection.callback(proto)
        self.assertEqual(receivedProtos, [proto])

        expectedClients = self.expectedClients(mreactor)

        self.assertEqual(len(expectedClients), 1)
        self.assertConnectArgs(expectedClients[0], expectedArgs)
        self.assertEqual([], mreactor.getDelayedCalls())


    def test_nameResolution(self):
        """
        While resolving hostnames, _nameResolution calls _deferToThread with
        _getaddrinfo.
        """
        calls = []
        clientFactory = object()

        def fakeDeferToThread(f, *args, **kwargs):
            calls.append((f, args, kwargs))
            return defer.Deferred()

        endpoint = endpoints.HostnameEndpoint(reactor, b'ipv4.example.com',
            1234)
        fakegetaddrinfo = object()
        endpoint._getaddrinfo = fakegetaddrinfo
        endpoint._deferToThread = fakeDeferToThread
        endpoint.connect(clientFactory)
        self.assertEqual(
            [(fakegetaddrinfo, (b"ipv4.example.com", 1234, 0, SOCK_STREAM),
                {})], calls)



class HostnameEndpointsOneIPv6Tests(ClientEndpointTestCaseMixin,
                                    unittest.TestCase):
    """
    Tests for the hostname based endpoints when GAI returns only one
    (IPv6) address.
    """
    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Creates a L{HostnameEndpoint} instance where the hostname is resolved
        into a single IPv6 address.
        """
        address = HostnameAddress(b"ipv6.example.com", 80)
        endpoint = endpoints.HostnameEndpoint(reactor, b"ipv6.example.com",
                                              address.port, **connectArgs)

        def testNameResolution(host, port):
            self.assertEqual(b"ipv6.example.com", host)
            data = [(AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('1:2::3:4', port,
                0, 0))]
            return defer.succeed(data)

        endpoint._nameResolution = testNameResolution

        return (endpoint, ('1:2::3:4', address.port, clientFactory,
                connectArgs.get('timeout', 30),
                connectArgs.get('bindAddress', None)),
                address)


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorTCP.connectTCP}
        """
        return reactor.tcpClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, timeout, and bindAddress in C{receivedArgs}
        to C{expectedArgs}.  We ignore the factory because we don't
        only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that was passed to
            L{IReactorTCP.connectTCP}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{timeout}, C{bindAddress}) that we expect to have been passed
            to L{IReactorTCP.connectTCP}.
        """
        (host, port, ignoredFactory, timeout, bindAddress) = receivedArgs
        (expectedHost, expectedPort, _ignoredFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def test_endpointConnectingCancelled(self):
        """
        Calling L{Deferred.cancel} on the L{Deferred} returned from
        L{IStreamClientEndpoint.connect} is errbacked with an expected
        L{ConnectingCancelledError} exception.
        """
        mreactor = MemoryReactor()
        clientFactory = protocol.Factory()
        clientFactory.protocol = protocol.Protocol

        ep, ignoredArgs, address = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)
        d.cancel()
        # When canceled, the connector will immediately notify its factory that
        # the connection attempt has failed due to a UserError.
        attemptFactory = self.retrieveConnectedFactory(mreactor)
        attemptFactory.clientConnectionFailed(None, Failure(error.UserError()))
        # This should be a feature of MemoryReactor: <http://tm.tl/5630>.

        failure = self.failureResultOf(d)

        self.assertIsInstance(failure.value, error.ConnectingCancelledError)
        self.assertEqual(failure.value.address, address)
        self.assertTrue(mreactor.tcpClients[0][2]._connector.stoppedConnecting)
        self.assertEqual([], mreactor.getDelayedCalls())


    def test_endpointConnectFailure(self):
        """
        If an endpoint tries to connect to a non-listening port it gets
        a C{ConnectError} failure.
        """
        expectedError = error.ConnectError(string="Connection Failed")
        mreactor = RaisingMemoryReactorWithClock(connectException=expectedError)
        clientFactory = object()

        ep, ignoredArgs, ignoredDest = self.createClientEndpoint(
            mreactor, clientFactory)

        d = ep.connect(clientFactory)
        mreactor.advance(0.3)
        self.assertEqual(self.failureResultOf(d).value, expectedError)
        self.assertEqual([], mreactor.getDelayedCalls())



class HostnameEndpointsGAIFailureTests(unittest.TestCase):
    """
    Tests for the hostname based endpoints when GAI returns no address.
    """
    def test_failure(self):
        """
        If no address is returned by GAI for a hostname, the connection attempt
        fails with L{error.DNSLookupError}.
        """
        endpoint = endpoints.HostnameEndpoint(Clock(), b"example.com", 80)

        def testNameResolution(host, port):
            self.assertEqual(b"example.com", host)
            data = error.DNSLookupError("Problems")
            return defer.fail(data)

        endpoint._nameResolution = testNameResolution
        clientFactory = object()
        dConnect = endpoint.connect(clientFactory)
        return self.assertFailure(dConnect, error.DNSLookupError)



class HostnameEndpointsFasterConnectionTests(unittest.TestCase):
    """
    Tests for the hostname based endpoints when gai returns an IPv4 and
    an IPv6 address, and one connection takes less time than the other.
    """
    def setUp(self):
        self.mreactor = MemoryReactor()
        self.endpoint = endpoints.HostnameEndpoint(self.mreactor,
                b"www.example.com", 80)

        def nameResolution(host, port):
            self.assertEqual(b"www.example.com", host)
            data = [
                (AF_INET, SOCK_STREAM, IPPROTO_TCP, '', ('1.2.3.4', port)),
                (AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('1:2::3:4', port, 0, 0))
                ]
            return defer.succeed(data)

        self.endpoint._nameResolution = nameResolution


    def test_ignoreUnknownAddressFamilies(self):
        """
        If an address family other than AF_INET and AF_INET6 is returned by
        on address resolution, the endpoint ignores that address.
        """
        self.mreactor = MemoryReactor()
        self.endpoint = endpoints.HostnameEndpoint(self.mreactor,
                b"www.example.com", 80)
        AF_INX = None  # An arbitrary name for testing

        def nameResolution(host, port):
            self.assertEqual(b"www.example.com", host)
            data = [
                (AF_INET, SOCK_STREAM, IPPROTO_TCP, '', ('1.2.3.4', port)),
                (AF_INX, SOCK_STREAM, 'SOME_PROTOCOL_IN_FUTURE', '',
                    ('a.b.c.d', port)),
                (AF_INET6, SOCK_STREAM, IPPROTO_TCP, '', ('1:2::3:4', port, 0,
                    0))]
            return defer.succeed(data)

        self.endpoint._nameResolution = nameResolution
        clientFactory = None

        self.endpoint.connect(clientFactory)

        self.mreactor.advance(0.3)
        (host, port, factory, timeout, bindAddress) = self.mreactor.tcpClients[1]
        self.assertEqual(len(self.mreactor.tcpClients), 2)
        self.assertEqual(host, '1:2::3:4')
        self.assertEqual(port, 80)


    def test_IPv4IsFaster(self):
        """
        The endpoint returns a connection to the IPv4 address.

        IPv4 ought to be the first attempt, since nameResolution (standing in
        for GAI here) returns it first. The IPv4 attempt succeeds, the
        connection is established, and a Deferred fires with the protocol
        constructed.
        """
        clientFactory = protocol.Factory()
        clientFactory.protocol = protocol.Protocol

        d = self.endpoint.connect(clientFactory)
        results = []
        d.addCallback(results.append)
        (host, port, factory, timeout, bindAddress) = self.mreactor.tcpClients[0]

        self.assertEqual(host, '1.2.3.4')
        self.assertEqual(port, 80)

        proto = factory.buildProtocol((host, port))
        fakeTransport = object()

        self.assertEqual(results, [])

        proto.makeConnection(fakeTransport)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].factory, clientFactory)
        self.assertEqual([], self.mreactor.getDelayedCalls())


    def test_IPv6IsFaster(self):
        """
        The endpoint returns a connection to the IPv6 address.

        IPv6 ought to be the second attempt, since nameResolution (standing in
        for GAI here) returns it second. The IPv6 attempt succeeds, a
        connection is established, and a Deferred fires with the protocol
        constructed.
        """
        clientFactory = protocol.Factory()
        clientFactory.protocol = protocol.Protocol

        d = self.endpoint.connect(clientFactory)
        results = []
        d.addCallback(results.append)

        self.mreactor.advance(0.3)
        (host, port, factory, timeout, bindAddress) = self.mreactor.tcpClients[1]

        self.assertEqual(host, '1:2::3:4')
        self.assertEqual(port, 80)

        proto = factory.buildProtocol((host, port))
        fakeTransport = object()

        self.assertEqual(results, [])

        proto.makeConnection(fakeTransport)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].factory, clientFactory)
        self.assertEqual([], self.mreactor.getDelayedCalls())


    def test_otherConnectionsCancelled(self):
        """
        Once the endpoint returns a successful connection, all the other
        pending connections are cancelled.

        Here, the second connection attempt, i.e. IPv6, succeeds, and the
        pending first attempt, i.e. IPv4, is cancelled.
        """
        clientFactory = protocol.Factory()
        clientFactory.protocol = protocol.Protocol

        d = self.endpoint.connect(clientFactory)
        results = []
        d.addCallback(results.append)

        self.mreactor.advance(0.3)
        (host, port, factory, timeout, bindAddress) = self.mreactor.tcpClients[1]

        proto = factory.buildProtocol((host, port))
        fakeTransport = object()

        proto.makeConnection(fakeTransport)

        self.assertEqual(True,
                self.mreactor.tcpClients[0][2]._connector.stoppedConnecting)
        self.assertEqual([], self.mreactor.getDelayedCalls())



class SSL4EndpointsTests(EndpointTestCaseMixin,
                         unittest.TestCase):
    """
    Tests for SSL Endpoints.
    """
    if skipSSL:
        skip = skipSSL

    def expectedServers(self, reactor):
        """
        @return: List of calls to L{IReactorSSL.listenSSL}
        """
        return reactor.sslServers


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorSSL.connectSSL}
        """
        return reactor.sslClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare host, port, contextFactory, timeout, and bindAddress in
        C{receivedArgs} to C{expectedArgs}.  We ignore the factory because we
        don't only care what protocol comes out of the
        C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{contextFactory}, C{timeout}, C{bindAddress}) that was passed to
            L{IReactorSSL.connectSSL}.
        @param expectedArgs: C{tuple} of (C{host}, C{port}, C{factory},
            C{contextFactory}, C{timeout}, C{bindAddress}) that we expect to
            have been passed to L{IReactorSSL.connectSSL}.
        """
        (host, port, ignoredFactory, contextFactory, timeout,
         bindAddress) = receivedArgs

        (expectedHost, expectedPort, _ignoredFactory, expectedContextFactory,
         expectedTimeout, expectedBindAddress) = expectedArgs

        self.assertEqual(host, expectedHost)
        self.assertEqual(port, expectedPort)
        self.assertEqual(contextFactory, expectedContextFactory)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(bindAddress, expectedBindAddress)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'bindAddress': ('localhost', 49595)}


    def listenArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to listen
        """
        return {'backlog': 100, 'interface': '127.0.0.1'}


    def setUp(self):
        """
        Set up client and server SSL contexts for use later.
        """
        self.sKey, self.sCert = makeCertificate(
            O="Server Test Certificate",
            CN="server")
        self.cKey, self.cCert = makeCertificate(
            O="Client Test Certificate",
            CN="client")
        self.serverSSLContext = CertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            requireCertificate=False)
        self.clientSSLContext = CertificateOptions(
            requireCertificate=False)


    def createServerEndpoint(self, reactor, factory, **listenArgs):
        """
        Create an L{SSL4ServerEndpoint} and return the tools to verify its
        behaviour.

        @param factory: The thing that we expect to be passed to our
            L{IStreamServerEndpoint.listen} implementation.
        @param reactor: A fake L{IReactorSSL} that L{SSL4ServerEndpoint} can
            call L{IReactorSSL.listenSSL} on.
        @param listenArgs: Optional dictionary of arguments to
            L{IReactorSSL.listenSSL}.
        """
        address = IPv4Address("TCP", "0.0.0.0", 0)

        return (endpoints.SSL4ServerEndpoint(reactor,
                                             address.port,
                                             self.serverSSLContext,
                                             **listenArgs),
                (address.port, factory, self.serverSSLContext,
                 listenArgs.get('backlog', 50),
                 listenArgs.get('interface', '')),
                address)


    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Create an L{SSL4ClientEndpoint} and return the values needed to verify
        its behaviour.

        @param reactor: A fake L{IReactorSSL} that L{SSL4ClientEndpoint} can
            call L{IReactorSSL.connectSSL} on.
        @param clientFactory: The thing that we expect to be passed to our
            L{IStreamClientEndpoint.connect} implementation.
        @param connectArgs: Optional dictionary of arguments to
            L{IReactorSSL.connectSSL}
        """
        address = IPv4Address("TCP", "localhost", 80)

        if connectArgs is None:
            connectArgs = {}

        return (endpoints.SSL4ClientEndpoint(reactor,
                                             address.host,
                                             address.port,
                                             self.clientSSLContext,
                                             **connectArgs),
                (address.host, address.port, clientFactory,
                 self.clientSSLContext,
                 connectArgs.get('timeout', 30),
                 connectArgs.get('bindAddress', None)),
                address)



class UNIXEndpointsTests(EndpointTestCaseMixin,
                         unittest.TestCase):
    """
    Tests for UnixSocket Endpoints.
    """

    def retrieveConnectedFactory(self, reactor):
        """
        Override L{EndpointTestCaseMixin.retrieveConnectedFactory} to account
        for different index of 'factory' in C{connectUNIX} args.
        """
        return self.expectedClients(reactor)[0][1]

    def expectedServers(self, reactor):
        """
        @return: List of calls to L{IReactorUNIX.listenUNIX}
        """
        return reactor.unixServers


    def expectedClients(self, reactor):
        """
        @return: List of calls to L{IReactorUNIX.connectUNIX}
        """
        return reactor.unixClients


    def assertConnectArgs(self, receivedArgs, expectedArgs):
        """
        Compare path, timeout, checkPID in C{receivedArgs} to C{expectedArgs}.
        We ignore the factory because we don't only care what protocol comes
        out of the C{IStreamClientEndpoint.connect} call.

        @param receivedArgs: C{tuple} of (C{path}, C{timeout}, C{checkPID})
            that was passed to L{IReactorUNIX.connectUNIX}.
        @param expectedArgs: C{tuple} of (C{path}, C{timeout}, C{checkPID})
            that we expect to have been passed to L{IReactorUNIX.connectUNIX}.
        """

        (path, ignoredFactory, timeout, checkPID) = receivedArgs

        (expectedPath, _ignoredFactory, expectedTimeout,
         expectedCheckPID) = expectedArgs

        self.assertEqual(path, expectedPath)
        self.assertEqual(timeout, expectedTimeout)
        self.assertEqual(checkPID, expectedCheckPID)


    def connectArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to connect.
        """
        return {'timeout': 10, 'checkPID': 1}


    def listenArgs(self):
        """
        @return: C{dict} of keyword arguments to pass to listen
        """
        return {'backlog': 100, 'mode': 0o600, 'wantPID': 1}


    def createServerEndpoint(self, reactor, factory, **listenArgs):
        """
        Create an L{UNIXServerEndpoint} and return the tools to verify its
        behaviour.

        @param reactor: A fake L{IReactorUNIX} that L{UNIXServerEndpoint} can
            call L{IReactorUNIX.listenUNIX} on.
        @param factory: The thing that we expect to be passed to our
            L{IStreamServerEndpoint.listen} implementation.
        @param listenArgs: Optional dictionary of arguments to
            L{IReactorUNIX.listenUNIX}.
        """
        address = UNIXAddress(self.mktemp())

        return (endpoints.UNIXServerEndpoint(reactor, address.name,
                                             **listenArgs),
                (address.name, factory,
                 listenArgs.get('backlog', 50),
                 listenArgs.get('mode', 0o666),
                 listenArgs.get('wantPID', 0)),
                address)


    def createClientEndpoint(self, reactor, clientFactory, **connectArgs):
        """
        Create an L{UNIXClientEndpoint} and return the values needed to verify
        its behaviour.

        @param reactor: A fake L{IReactorUNIX} that L{UNIXClientEndpoint} can
            call L{IReactorUNIX.connectUNIX} on.
        @param clientFactory: The thing that we expect to be passed to our
            L{IStreamClientEndpoint.connect} implementation.
        @param connectArgs: Optional dictionary of arguments to
            L{IReactorUNIX.connectUNIX}
        """
        address = UNIXAddress(self.mktemp())

        return (endpoints.UNIXClientEndpoint(reactor, address.name,
                                             **connectArgs),
                (address.name, clientFactory,
                 connectArgs.get('timeout', 30),
                 connectArgs.get('checkPID', 0)),
                address)



class ParserTests(unittest.TestCase):
    """
    Tests for L{endpoints._parseServer}, the low-level parsing logic.
    """

    f = "Factory"

    def parse(self, *a, **kw):
        """
        Provide a hook for test_strports to substitute the deprecated API.
        """
        return endpoints._parseServer(*a, **kw)


    def test_simpleTCP(self):
        """
        Simple strings with a 'tcp:' prefix should be parsed as TCP.
        """
        self.assertEqual(
            self.parse('tcp:80', self.f),
            ('TCP', (80, self.f), {'interface': '', 'backlog': 50}))


    def test_interfaceTCP(self):
        """
        TCP port descriptions parse their 'interface' argument as a string.
        """
        self.assertEqual(
            self.parse('tcp:80:interface=127.0.0.1', self.f),
            ('TCP', (80, self.f), {'interface': '127.0.0.1', 'backlog': 50}))


    def test_backlogTCP(self):
        """
        TCP port descriptions parse their 'backlog' argument as an integer.
        """
        self.assertEqual(
            self.parse('tcp:80:backlog=6', self.f),
            ('TCP', (80, self.f), {'interface': '', 'backlog': 6}))


    def test_simpleUNIX(self):
        """
        L{endpoints._parseServer} returns a C{'UNIX'} port description with
        defaults for C{'mode'}, C{'backlog'}, and C{'wantPID'} when passed a
        string with the C{'unix:'} prefix and no other parameter values.
        """
        self.assertEqual(
            self.parse('unix:/var/run/finger', self.f),
            ('UNIX', ('/var/run/finger', self.f),
             {'mode': 0o666, 'backlog': 50, 'wantPID': True}))


    def test_modeUNIX(self):
        """
        C{mode} can be set by including C{"mode=<some integer>"}.
        """
        self.assertEqual(
            self.parse('unix:/var/run/finger:mode=0660', self.f),
            ('UNIX', ('/var/run/finger', self.f),
             {'mode': 0o660, 'backlog': 50, 'wantPID': True}))


    def test_wantPIDUNIX(self):
        """
        C{wantPID} can be set to false by included C{"lockfile=0"}.
        """
        self.assertEqual(
            self.parse('unix:/var/run/finger:lockfile=0', self.f),
            ('UNIX', ('/var/run/finger', self.f),
             {'mode': 0o666, 'backlog': 50, 'wantPID': False}))


    def test_escape(self):
        """
        Backslash can be used to escape colons and backslashes in port
        descriptions.
        """
        self.assertEqual(
            self.parse('unix:foo\x5c:bar\x5c=baz\x5c:qux\x5c\x5c', self.f),
            ('UNIX', ('foo:bar=baz:qux\x5c', self.f),
             {'mode': 0o666, 'backlog': 50, 'wantPID': True}))


    def test_quoteStringArgument(self):
        """
        L{endpoints.quoteStringArgument} should quote backslashes and colons
        for interpolation into L{endpoints.serverFromString} and
        L{endpoints.clientFactory} arguments.
        """
        self.assertEqual(endpoints.quoteStringArgument("some : stuff \x5c"),
                         "some \x5c: stuff \x5c\x5c")


    def test_impliedEscape(self):
        """
        In strports descriptions, '=' in a parameter value does not need to be
        quoted; it will simply be parsed as part of the value.
        """
        self.assertEqual(
            self.parse(r'unix:address=foo=bar', self.f),
            ('UNIX', ('foo=bar', self.f),
             {'mode': 0o666, 'backlog': 50, 'wantPID': True}))


    def test_nonstandardDefault(self):
        """
        For compatibility with the old L{twisted.application.strports.parse},
        the third 'mode' argument may be specified to L{endpoints.parse} to
        indicate a default other than TCP.
        """
        self.assertEqual(
            self.parse('filename', self.f, 'unix'),
            ('UNIX', ('filename', self.f),
             {'mode': 0o666, 'backlog': 50, 'wantPID': True}))


    def test_unknownType(self):
        """
        L{strports.parse} raises C{ValueError} when given an unknown endpoint
        type.
        """
        self.assertRaises(ValueError, self.parse, "bogus-type:nothing", self.f)



class ServerStringTests(unittest.TestCase):
    """
    Tests for L{twisted.internet.endpoints.serverFromString}.
    """

    def test_tcp(self):
        """
        When passed a TCP strports description, L{endpoints.serverFromString}
        returns a L{TCP4ServerEndpoint} instance initialized with the values
        from the string.
        """
        reactor = object()
        server = endpoints.serverFromString(
            reactor, "tcp:1234:backlog=12:interface=10.0.0.1")
        self.assertIsInstance(server, endpoints.TCP4ServerEndpoint)
        self.assertIs(server._reactor, reactor)
        self.assertEqual(server._port, 1234)
        self.assertEqual(server._backlog, 12)
        self.assertEqual(server._interface, "10.0.0.1")


    def test_ssl(self):
        """
        When passed an SSL strports description, L{endpoints.serverFromString}
        returns a L{SSL4ServerEndpoint} instance initialized with the values
        from the string.
        """
        reactor = object()
        server = endpoints.serverFromString(
            reactor,
            "ssl:1234:backlog=12:privateKey=%s:"
            "certKey=%s:sslmethod=TLSv1_METHOD:interface=10.0.0.1"
            % (escapedPEMPathName, escapedPEMPathName))
        self.assertIsInstance(server, endpoints.SSL4ServerEndpoint)
        self.assertIs(server._reactor, reactor)
        self.assertEqual(server._port, 1234)
        self.assertEqual(server._backlog, 12)
        self.assertEqual(server._interface, "10.0.0.1")
        self.assertEqual(server._sslContextFactory.method, TLSv1_METHOD)
        ctx = server._sslContextFactory.getContext()
        self.assertIsInstance(ctx, ContextType)


    def test_sslWithDefaults(self):
        """
        An SSL string endpoint description with minimal arguments returns
        a properly initialized L{SSL4ServerEndpoint} instance.
        """
        reactor = object()
        server = endpoints.serverFromString(
            reactor, "ssl:4321:privateKey=%s" % (escapedPEMPathName,))
        self.assertIsInstance(server, endpoints.SSL4ServerEndpoint)
        self.assertIs(server._reactor, reactor)
        self.assertEqual(server._port, 4321)
        self.assertEqual(server._backlog, 50)
        self.assertEqual(server._interface, "")
        self.assertEqual(server._sslContextFactory.method, SSLv23_METHOD)
        self.assertTrue(
            server._sslContextFactory._options & OP_NO_SSLv3,
        )
        ctx = server._sslContextFactory.getContext()
        self.assertIsInstance(ctx, ContextType)


    # Use a class variable to ensure we use the exactly same endpoint string
    # except for the chain file itself.
    SSL_CHAIN_TEMPLATE = "ssl:1234:privateKey=%s:extraCertChain=%s"


    def test_sslChainLoads(self):
        """
        Specifying a chain file loads the contained certificates in the right
        order.
        """
        server = endpoints.serverFromString(
            object(),
            self.SSL_CHAIN_TEMPLATE % (escapedPEMPathName,
                                       escapedChainPathName,)
        )
        # Test chain file is just a concatenation of thing1.pem and thing2.pem
        # so we can check that loading has succeeded and order has been
        # preserved.
        expectedChainCerts = [
            Certificate.loadPEM(casPath.child("thing%d.pem" % (n,))
                                .getContent())
            for n in [1, 2]
        ]
        cf = server._sslContextFactory
        self.assertEqual(cf.extraCertChain[0].digest('sha1'),
                         expectedChainCerts[0].digest('sha1'))
        self.assertEqual(cf.extraCertChain[1].digest('sha1'),
                         expectedChainCerts[1].digest('sha1'))


    def test_sslChainFileMustContainCert(self):
        """
        If C{extraCertChain} is passed, it has to contain at least one valid
        certificate in PEM format.
        """
        fp = FilePath(self.mktemp())
        fp.create().close()
        # The endpoint string is the same as in the valid case except for
        # a different chain file.  We use an empty temp file which obviously
        # will never contain any certificates.
        with self.assertRaises(ValueError) as caught:
            endpoints.serverFromString(
                object(),
                self.SSL_CHAIN_TEMPLATE % (
                    escapedPEMPathName,
                    endpoints.quoteStringArgument(fp.path),
                )
            )

        # The raised exception should list what file it is attempting to find
        # the chain in.
        self.assertEqual(str(caught.exception),
                         ("Specified chain file '%s' doesn't contain any valid"
                          " certificates in PEM format.") % (fp.path,))


    def test_sslDHparameters(self):
        """
        If C{dhParameters} are specified, they are passed as
        L{DiffieHellmanParameters} into L{CertificateOptions}.
        """
        fileName = 'someFile'
        reactor = object()
        server = endpoints.serverFromString(
            reactor,
            "ssl:4321:privateKey={0}:certKey={1}:dhParameters={2}"
            .format(escapedPEMPathName, escapedPEMPathName, fileName)
        )
        cf = server._sslContextFactory
        self.assertIsInstance(cf.dhParameters, DiffieHellmanParameters)
        self.assertEqual(FilePath(fileName), cf.dhParameters._dhFile)


    if skipSSL:
        test_ssl.skip = test_sslWithDefaults.skip = skipSSL
        test_sslChainLoads.skip = skipSSL
        test_sslChainFileMustContainCert.skip = skipSSL
        test_sslDHparameters.skip = skipSSL


    def test_unix(self):
        """
        When passed a UNIX strports description, L{endpoint.serverFromString}
        returns a L{UNIXServerEndpoint} instance initialized with the values
        from the string.
        """
        reactor = object()
        endpoint = endpoints.serverFromString(
            reactor,
            "unix:/var/foo/bar:backlog=7:mode=0123:lockfile=1")
        self.assertIsInstance(endpoint, endpoints.UNIXServerEndpoint)
        self.assertIs(endpoint._reactor, reactor)
        self.assertEqual(endpoint._address, "/var/foo/bar")
        self.assertEqual(endpoint._backlog, 7)
        self.assertEqual(endpoint._mode, 0o123)
        self.assertTrue(endpoint._wantPID)


    def test_implicitDefaultNotAllowed(self):
        """
        The older service-based API (L{twisted.internet.strports.service})
        allowed an implicit default of 'tcp' so that TCP ports could be
        specified as a simple integer, but we've since decided that's a bad
        idea, and the new API does not accept an implicit default argument; you
        have to say 'tcp:' now.  If you try passing an old implicit port number
        to the new API, you'll get a C{ValueError}.
        """
        value = self.assertRaises(
            ValueError, endpoints.serverFromString, None, "4321")
        self.assertEqual(
            str(value),
            "Unqualified strport description passed to 'service'."
            "Use qualified endpoint descriptions; for example, 'tcp:4321'.")


    def test_unknownType(self):
        """
        L{endpoints.serverFromString} raises C{ValueError} when given an
        unknown endpoint type.
        """
        value = self.assertRaises(
            # faster-than-light communication not supported
            ValueError, endpoints.serverFromString, None,
            "ftl:andromeda/carcosa/hali/2387")
        self.assertEqual(
            str(value),
            "Unknown endpoint type: 'ftl'")


    def test_typeFromPlugin(self):
        """
        L{endpoints.serverFromString} looks up plugins of type
        L{IStreamServerEndpoint} and constructs endpoints from them.
        """
        # Set up a plugin which will only be accessible for the duration of
        # this test.
        addFakePlugin(self)
        # Plugin is set up: now actually test.
        notAReactor = object()
        fakeEndpoint = endpoints.serverFromString(
            notAReactor, "fake:hello:world:yes=no:up=down")
        from twisted.plugins.fakeendpoint import fake
        self.assertIs(fakeEndpoint.parser, fake)
        self.assertEqual(fakeEndpoint.args, (notAReactor, 'hello', 'world'))
        self.assertEqual(fakeEndpoint.kwargs, dict(yes='no', up='down'))



def addFakePlugin(testCase, dropinSource="fakeendpoint.py"):
    """
    For the duration of C{testCase}, add a fake plugin to twisted.plugins which
    contains some sample endpoint parsers.
    """
    import sys
    savedModules = sys.modules.copy()
    savedPluginPath = list(plugins.__path__)

    def cleanup():
        sys.modules.clear()
        sys.modules.update(savedModules)
        plugins.__path__[:] = savedPluginPath

    testCase.addCleanup(cleanup)
    fp = FilePath(testCase.mktemp())
    fp.createDirectory()
    getModule(__name__).filePath.sibling(dropinSource).copyTo(
        fp.child(dropinSource))
    plugins.__path__.append(fp.path)



class ClientStringTests(unittest.TestCase):
    """
    Tests for L{twisted.internet.endpoints.clientFromString}.
    """

    def test_tcp(self):
        """
        When passed a TCP strports description, L{endpoints.clientFromString}
        returns a L{TCP4ClientEndpoint} instance initialized with the values
        from the string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "tcp:host=example.com:port=1234:timeout=7:bindAddress=10.0.0.2")
        self.assertIsInstance(client, endpoints.TCP4ClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._host, "example.com")
        self.assertEqual(client._port, 1234)
        self.assertEqual(client._timeout, 7)
        self.assertEqual(client._bindAddress, ("10.0.0.2", 0))


    def test_tcpPositionalArgs(self):
        """
        When passed a TCP strports description using positional arguments,
        L{endpoints.clientFromString} returns a L{TCP4ClientEndpoint} instance
        initialized with the values from the string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "tcp:example.com:1234:timeout=7:bindAddress=10.0.0.2")
        self.assertIsInstance(client, endpoints.TCP4ClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._host, "example.com")
        self.assertEqual(client._port, 1234)
        self.assertEqual(client._timeout, 7)
        self.assertEqual(client._bindAddress, ("10.0.0.2", 0))


    def test_tcpHostPositionalArg(self):
        """
        When passed a TCP strports description specifying host as a positional
        argument, L{endpoints.clientFromString} returns a L{TCP4ClientEndpoint}
        instance initialized with the values from the string.
        """
        reactor = object()

        client = endpoints.clientFromString(
            reactor,
            "tcp:example.com:port=1234:timeout=7:bindAddress=10.0.0.2")
        self.assertEqual(client._host, "example.com")
        self.assertEqual(client._port, 1234)


    def test_tcpPortPositionalArg(self):
        """
        When passed a TCP strports description specifying port as a positional
        argument, L{endpoints.clientFromString} returns a L{TCP4ClientEndpoint}
        instance initialized with the values from the string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "tcp:host=example.com:1234:timeout=7:bindAddress=10.0.0.2")
        self.assertEqual(client._host, "example.com")
        self.assertEqual(client._port, 1234)


    def test_tcpDefaults(self):
        """
        A TCP strports description may omit I{timeout} or I{bindAddress} to
        allow the default to be used.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "tcp:host=example.com:port=1234")
        self.assertEqual(client._timeout, 30)
        self.assertIsNone(client._bindAddress)


    def test_unix(self):
        """
        When passed a UNIX strports description, L{endpoints.clientFromString}
        returns a L{UNIXClientEndpoint} instance initialized with the values
        from the string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "unix:path=/var/foo/bar:lockfile=1:timeout=9")
        self.assertIsInstance(client, endpoints.UNIXClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._path, "/var/foo/bar")
        self.assertEqual(client._timeout, 9)
        self.assertTrue(client._checkPID)


    def test_unixDefaults(self):
        """
        A UNIX strports description may omit I{lockfile} or I{timeout} to allow
        the defaults to be used.
        """
        client = endpoints.clientFromString(
            object(), "unix:path=/var/foo/bar")
        self.assertEqual(client._timeout, 30)
        self.assertFalse(client._checkPID)


    def test_unixPathPositionalArg(self):
        """
        When passed a UNIX strports description specifying path as a positional
        argument, L{endpoints.clientFromString} returns a L{UNIXClientEndpoint}
        instance initialized with the values from the string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "unix:/var/foo/bar:lockfile=1:timeout=9")
        self.assertIsInstance(client, endpoints.UNIXClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._path, "/var/foo/bar")
        self.assertEqual(client._timeout, 9)
        self.assertTrue(client._checkPID)


    def test_typeFromPlugin(self):
        """
        L{endpoints.clientFromString} looks up plugins of type
        L{IStreamClientEndpoint} and constructs endpoints from them.
        """
        addFakePlugin(self)
        notAReactor = object()
        clientEndpoint = endpoints.clientFromString(
            notAReactor, "crfake:alpha:beta:cee=dee:num=1")
        from twisted.plugins.fakeendpoint import fakeClientWithReactor
        self.assertIs(clientEndpoint.parser, fakeClientWithReactor)
        self.assertEqual(clientEndpoint.args, (notAReactor, 'alpha', 'beta'))
        self.assertEqual(clientEndpoint.kwargs, dict(cee='dee', num='1'))


    def test_unknownType(self):
        """
        L{endpoints.clientFromString} raises C{ValueError} when given an
        unknown endpoint type.
        """
        value = self.assertRaises(
            # faster-than-light communication not supported
            ValueError, endpoints.clientFromString, None,
            "ftl:andromeda/carcosa/hali/2387")
        self.assertEqual(
            str(value),
            "Unknown endpoint type: 'ftl'")


    def test_stringParserWithReactor(self):
        """
        L{endpoints.clientFromString} will pass a reactor to plugins
        implementing the L{IStreamClientEndpointStringParserWithReactor}
        interface.
        """
        addFakePlugin(self)
        reactor = object()
        clientEndpoint = endpoints.clientFromString(
            reactor, 'crfake:alpha:beta:cee=dee:num=1')
        from twisted.plugins.fakeendpoint import fakeClientWithReactor
        self.assertEqual(
            (clientEndpoint.parser,
             clientEndpoint.args,
             clientEndpoint.kwargs),
            (fakeClientWithReactor,
             (reactor, 'alpha', 'beta'),
             dict(cee='dee', num='1')))



class SSLClientStringTests(unittest.TestCase):
    """
    Tests for L{twisted.internet.endpoints.clientFromString} which require SSL.
    """

    if skipSSL:
        skip = skipSSL

    def test_ssl(self):
        """
        When passed an SSL strports description, L{clientFromString} returns a
        L{SSL4ClientEndpoint} instance initialized with the values from the
        string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "ssl:host=example.net:port=4321:privateKey=%s:"
            "certKey=%s:bindAddress=10.0.0.3:timeout=3:caCertsDir=%s" %
            (escapedPEMPathName, escapedPEMPathName, escapedCAsPathName))
        self.assertIsInstance(client, endpoints.SSL4ClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._host, "example.net")
        self.assertEqual(client._port, 4321)
        self.assertEqual(client._timeout, 3)
        self.assertEqual(client._bindAddress, ("10.0.0.3", 0))
        certOptions = client._sslContextFactory
        self.assertIsInstance(certOptions, CertificateOptions)
        self.assertEqual(certOptions.method, SSLv23_METHOD)
        self.assertTrue(certOptions._options & OP_NO_SSLv3)
        ctx = certOptions.getContext()
        self.assertIsInstance(ctx, ContextType)
        self.assertEqual(Certificate(certOptions.certificate), testCertificate)
        privateCert = PrivateCertificate(certOptions.certificate)
        privateCert._setPrivateKey(KeyPair(certOptions.privateKey))
        self.assertEqual(privateCert, testPrivateCertificate)
        expectedCerts = [
            Certificate.loadPEM(x.getContent()) for x in
            [casPath.child("thing1.pem"), casPath.child("thing2.pem")]
            if x.basename().lower().endswith('.pem')
        ]
        addedCerts = []
        class ListCtx(object):
            def get_cert_store(self):
                class Store(object):
                    def add_cert(self, cert):
                        addedCerts.append(cert)
                return Store()
        certOptions.trustRoot._addCACertsToContext(ListCtx())
        self.assertEqual(
            sorted((Certificate(x) for x in addedCerts),
                   key=lambda cert: cert.digest()),
            sorted(expectedCerts,
                   key=lambda cert: cert.digest())
        )


    def test_sslPositionalArgs(self):
        """
        When passed an SSL strports description, L{clientFromString} returns a
        L{SSL4ClientEndpoint} instance initialized with the values from the
        string.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor,
            "ssl:example.net:4321:privateKey=%s:"
            "certKey=%s:bindAddress=10.0.0.3:timeout=3:caCertsDir=%s" %
            (escapedPEMPathName, escapedPEMPathName, escapedCAsPathName))
        self.assertIsInstance(client, endpoints.SSL4ClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._host, "example.net")
        self.assertEqual(client._port, 4321)
        self.assertEqual(client._timeout, 3)
        self.assertEqual(client._bindAddress, ("10.0.0.3", 0))


    def test_sslWithDefaults(self):
        """
        When passed an SSL strports description without extra arguments,
        L{clientFromString} returns a L{SSL4ClientEndpoint} instance
        whose context factory is initialized with default values.
        """
        reactor = object()
        client = endpoints.clientFromString(reactor, "ssl:example.net:4321")
        self.assertIsInstance(client, endpoints.SSL4ClientEndpoint)
        self.assertIs(client._reactor, reactor)
        self.assertEqual(client._host, "example.net")
        self.assertEqual(client._port, 4321)
        certOptions = client._sslContextFactory
        self.assertEqual(certOptions.method, SSLv23_METHOD)
        self.assertIsNone(certOptions.certificate)
        self.assertIsNone(certOptions.privateKey)


    def test_unreadableCertificate(self):
        """
        If a certificate in the directory is unreadable,
        L{endpoints._loadCAsFromDir} will ignore that certificate.
        """
        class UnreadableFilePath(FilePath):
            def getContent(self):
                data = FilePath.getContent(self)
                # There is a duplicate of thing2.pem, so ignore anything that
                # looks like it.
                if data == casPath.child("thing2.pem").getContent():
                    raise IOError(EPERM)
                else:
                    return data
        casPathClone = casPath.child("ignored").parent()
        casPathClone.clonePath = UnreadableFilePath
        self.assertEqual(
            [Certificate(x) for x in
             endpoints._loadCAsFromDir(casPathClone)._caCerts],
            [Certificate.loadPEM(casPath.child("thing1.pem").getContent())])


    def test_sslSimple(self):
        """
        When passed an SSL strports description without any extra parameters,
        L{clientFromString} returns a simple non-verifying endpoint that will
        speak SSL.
        """
        reactor = object()
        client = endpoints.clientFromString(
            reactor, "ssl:host=simple.example.org:port=4321")
        certOptions = client._sslContextFactory
        self.assertIsInstance(certOptions, CertificateOptions)
        self.assertFalse(certOptions.verify)
        ctx = certOptions.getContext()
        self.assertIsInstance(ctx, ContextType)



class AdoptedStreamServerEndpointTests(ServerEndpointTestCaseMixin,
                                       unittest.TestCase):
    """
    Tests for adopted socket-based stream server endpoints.
    """
    def _createStubbedAdoptedEndpoint(self, reactor, fileno, addressFamily):
        """
        Create an L{AdoptedStreamServerEndpoint} which may safely be used with
        an invalid file descriptor.  This is convenient for a number of unit
        tests.
        """
        e = endpoints.AdoptedStreamServerEndpoint(reactor, fileno,
                                                  addressFamily)
        # Stub out some syscalls which would fail, given our invalid file
        # descriptor.
        e._close = lambda fd: None
        e._setNonBlocking = lambda fd: None
        return e


    def createServerEndpoint(self, reactor, factory):
        """
        Create a new L{AdoptedStreamServerEndpoint} for use by a test.

        @return: A three-tuple:
            - The endpoint
            - A tuple of the arguments expected to be passed to the underlying
              reactor method
            - An IAddress object which will match the result of
              L{IListeningPort.getHost} on the port returned by the endpoint.
        """
        fileno = 12
        addressFamily = AF_INET
        endpoint = self._createStubbedAdoptedEndpoint(
            reactor, fileno, addressFamily)
        # Magic numbers come from the implementation of MemoryReactor
        address = IPv4Address("TCP", "0.0.0.0", 1234)
        return (endpoint, (fileno, addressFamily, factory), address)


    def expectedServers(self, reactor):
        """
        @return: The ports which were actually adopted by C{reactor} via calls
            to its L{IReactorSocket.adoptStreamPort} implementation.
        """
        return reactor.adoptedPorts


    def listenArgs(self):
        """
        @return: A C{dict} of additional keyword arguments to pass to the
            C{createServerEndpoint}.
        """
        return {}


    def test_singleUse(self):
        """
        L{AdoptedStreamServerEndpoint.listen} can only be used once.  The file
        descriptor given is closed after the first use, and subsequent calls to
        C{listen} return a L{Deferred} that fails with L{AlreadyListened}.
        """
        reactor = MemoryReactor()
        endpoint = self._createStubbedAdoptedEndpoint(reactor, 13, AF_INET)
        endpoint.listen(object())
        d = self.assertFailure(
            endpoint.listen(object()), error.AlreadyListened)

        def listenFailed(ignored):
            self.assertEqual(1, len(reactor.adoptedPorts))

        d.addCallback(listenFailed)
        return d


    def test_descriptionNonBlocking(self):
        """
        L{AdoptedStreamServerEndpoint.listen} sets the file description given
        to it to non-blocking.
        """
        reactor = MemoryReactor()
        endpoint = self._createStubbedAdoptedEndpoint(reactor, 13, AF_INET)
        events = []

        def setNonBlocking(fileno):
            events.append(("setNonBlocking", fileno))

        endpoint._setNonBlocking = setNonBlocking

        d = endpoint.listen(object())

        def listened(ignored):
            self.assertEqual([("setNonBlocking", 13)], events)

        d.addCallback(listened)
        return d


    def test_descriptorClosed(self):
        """
        L{AdoptedStreamServerEndpoint.listen} closes its file descriptor after
        adding it to the reactor with L{IReactorSocket.adoptStreamPort}.
        """
        reactor = MemoryReactor()
        endpoint = self._createStubbedAdoptedEndpoint(reactor, 13, AF_INET)
        events = []

        def close(fileno):
            events.append(("close", fileno, len(reactor.adoptedPorts)))

        endpoint._close = close

        d = endpoint.listen(object())

        def listened(ignored):
            self.assertEqual([("close", 13, 1)], events)

        d.addCallback(listened)
        return d



class SystemdEndpointPluginTests(unittest.TestCase):
    """
    Unit tests for the systemd stream server endpoint and endpoint string
    description parser.

    @see: U{systemd<http://www.freedesktop.org/wiki/Software/systemd>}
    """

    _parserClass = endpoints._SystemdParser

    def test_pluginDiscovery(self):
        """
        L{endpoints._SystemdParser} is found as a plugin for
        L{interfaces.IStreamServerEndpointStringParser} interface.
        """
        parsers = list(getPlugins(
            interfaces.IStreamServerEndpointStringParser))

        for p in parsers:
            if isinstance(p, self._parserClass):
                break
        else:
            self.fail("Did not find systemd parser in %r" % (parsers,))


    def test_interface(self):
        """
        L{endpoints._SystemdParser} instances provide
        L{interfaces.IStreamServerEndpointStringParser}.
        """
        parser = self._parserClass()
        self.assertTrue(verifyObject(
            interfaces.IStreamServerEndpointStringParser, parser))


    def _parseStreamServerTest(self, addressFamily, addressFamilyString):
        """
        Helper for unit tests for L{endpoints._SystemdParser.parseStreamServer}
        for different address families.

        Handling of the address family given will be verify.  If there is a
        problem a test-failing exception will be raised.

        @param addressFamily: An address family constant, like
            L{socket.AF_INET}.

        @param addressFamilyString: A string which should be recognized by the
            parser as representing C{addressFamily}.
        """
        reactor = object()
        descriptors = [5, 6, 7, 8, 9]
        index = 3

        parser = self._parserClass()
        parser._sddaemon = ListenFDs(descriptors)

        server = parser.parseStreamServer(
            reactor, domain=addressFamilyString, index=str(index))
        self.assertIs(server.reactor, reactor)
        self.assertEqual(server.addressFamily, addressFamily)
        self.assertEqual(server.fileno, descriptors[index])


    def test_parseStreamServerINET(self):
        """
        IPv4 can be specified using the string C{"INET"}.
        """
        self._parseStreamServerTest(AF_INET, "INET")


    def test_parseStreamServerINET6(self):
        """
        IPv6 can be specified using the string C{"INET6"}.
        """
        self._parseStreamServerTest(AF_INET6, "INET6")


    def test_parseStreamServerUNIX(self):
        """
        A UNIX domain socket can be specified using the string C{"UNIX"}.
        """
        try:
            from socket import AF_UNIX
        except ImportError:
            raise unittest.SkipTest("Platform lacks AF_UNIX support")
        else:
            self._parseStreamServerTest(AF_UNIX, "UNIX")



class TCP6ServerEndpointPluginTests(unittest.TestCase):
    """
    Unit tests for the TCP IPv6 stream server endpoint string description
    parser.
    """
    _parserClass = endpoints._TCP6ServerParser

    def test_pluginDiscovery(self):
        """
        L{endpoints._TCP6ServerParser} is found as a plugin for
        L{interfaces.IStreamServerEndpointStringParser} interface.
        """
        parsers = list(getPlugins(
            interfaces.IStreamServerEndpointStringParser))
        for p in parsers:
            if isinstance(p, self._parserClass):
                break
        else:
            self.fail(
                "Did not find TCP6ServerEndpoint parser in %r" % (parsers,))


    def test_interface(self):
        """
        L{endpoints._TCP6ServerParser} instances provide
        L{interfaces.IStreamServerEndpointStringParser}.
        """
        parser = self._parserClass()
        self.assertTrue(verifyObject(
            interfaces.IStreamServerEndpointStringParser, parser))


    def test_stringDescription(self):
        """
        L{serverFromString} returns a L{TCP6ServerEndpoint} instance with a
        'tcp6' endpoint string description.
        """
        ep = endpoints.serverFromString(
            MemoryReactor(), "tcp6:8080:backlog=12:interface=\:\:1")
        self.assertIsInstance(ep, endpoints.TCP6ServerEndpoint)
        self.assertIsInstance(ep._reactor, MemoryReactor)
        self.assertEqual(ep._port, 8080)
        self.assertEqual(ep._backlog, 12)
        self.assertEqual(ep._interface, '::1')



class StandardIOEndpointPluginTests(unittest.TestCase):
    """
    Unit tests for the Standard I/O endpoint string description parser.
    """
    _parserClass = endpoints._StandardIOParser

    def test_pluginDiscovery(self):
        """
        L{endpoints._StandardIOParser} is found as a plugin for
        L{interfaces.IStreamServerEndpointStringParser} interface.
        """
        parsers = list(getPlugins(
            interfaces.IStreamServerEndpointStringParser))
        for p in parsers:
            if isinstance(p, self._parserClass):
                break
        else:
            self.fail(
                "Did not find StandardIOEndpoint parser in %r" % (parsers,))


    def test_interface(self):
        """
        L{endpoints._StandardIOParser} instances provide
        L{interfaces.IStreamServerEndpointStringParser}.
        """
        parser = self._parserClass()
        self.assertTrue(verifyObject(
            interfaces.IStreamServerEndpointStringParser, parser))


    def test_stringDescription(self):
        """
        L{serverFromString} returns a L{StandardIOEndpoint} instance with a
        'stdio' endpoint string description.
        """
        ep = endpoints.serverFromString(MemoryReactor(), "stdio:")
        self.assertIsInstance(ep, endpoints.StandardIOEndpoint)
        self.assertIsInstance(ep._reactor, MemoryReactor)



class ConnectProtocolTests(unittest.TestCase):
    """
    Tests for C{connectProtocol}.
    """
    def test_connectProtocolCreatesFactory(self):
        """
        C{endpoints.connectProtocol} calls the given endpoint's C{connect()}
        method with a factory that will build the given protocol.
        """
        reactor = MemoryReactor()
        endpoint = endpoints.TCP4ClientEndpoint(reactor, "127.0.0.1", 0)
        theProtocol = object()
        endpoints.connectProtocol(endpoint, theProtocol)

        # A TCP connection was made via the given endpoint:
        self.assertEqual(len(reactor.tcpClients), 1)
        # TCP4ClientEndpoint uses a _WrapperFactory around the underlying
        # factory, so we need to unwrap it:
        factory = reactor.tcpClients[0][2]._wrappedFactory
        self.assertIsInstance(factory, protocol.Factory)
        self.assertIs(factory.buildProtocol(None), theProtocol)


    def test_connectProtocolReturnsConnectResult(self):
        """
        C{endpoints.connectProtocol} returns the result of calling the given
        endpoint's C{connect()} method.
        """
        result = defer.Deferred()
        class Endpoint:
            def connect(self, factory):
                """
                Return a marker object for use in our assertion.
                """
                return result

        endpoint = Endpoint()
        self.assertIs(result, endpoints.connectProtocol(endpoint, object()))



class UppercaseWrapperProtocol(policies.ProtocolWrapper, object):
    """
    A wrapper protocol which uppercases all strings passed through it.
    """

    def dataReceived(self, data):
        """
        Uppercase a string passed in from the transport.

        @param data: The string to uppercase.
        @type data: L{bytes}
        """
        super(UppercaseWrapperProtocol, self).dataReceived(data.upper())


    def write(self, data):
        """
        Uppercase a string passed out to the transport.

        @param data: The string to uppercase.
        @type data: L{bytes}
        """
        super(UppercaseWrapperProtocol, self).write(data.upper())


    def writeSequence(self, seq):
        """
        Uppercase a series of strings passed out to the transport.

        @param seq: An iterable of strings.
        """
        for data in seq:
            self.write(data)



class UppercaseWrapperFactory(policies.WrappingFactory, object):
    """
    A wrapper factory which uppercases all strings passed through it.
    """
    protocol = UppercaseWrapperProtocol



class NetstringTracker(basic.NetstringReceiver, object):
    """
    A netstring receiver which keeps track of the strings received.

    @ivar strings: A L{list} of received strings, in order.
    """

    def __init__(self):
        self.strings = []


    def stringReceived(self, string):
        """
        Receive a string and append it to C{self.strings}.

        @param string: The string to be appended to C{self.strings}.
        """
        self.strings.append(string)



class FakeError(Exception):
    """
    An error which isn't really an error.

    This is raised in the L{wrapClientTLS} tests in place of a
    'real' exception.
    """



class WrapperClientEndpointTests(unittest.TestCase):
    """
    Tests for L{_WrapperClientEndpoint}.
    """

    def setUp(self):
        self.endpoint, self.completer = connectableEndpoint()
        self.context = object()
        self.wrapper = endpoints._WrapperEndpoint(self.endpoint,
                                                  UppercaseWrapperFactory)
        self.factory = Factory.forProtocol(NetstringTracker)


    def test_wrappingBehavior(self):
        """
        Any modifications performed by the underlying L{ProtocolWrapper}
        propagate through to the wrapped L{Protocol}.
        """
        connecting = self.wrapper.connect(self.factory)
        pump = self.completer.succeedOnce()
        proto = self.successResultOf(connecting)
        pump.server.transport.write(b'5:hello,')
        pump.flush()
        self.assertEqual(proto.strings, [b'HELLO'])


    def test_methodsAvailable(self):
        """
        Methods defined on the wrapped L{Protocol} are accessible from the
        L{Protocol} returned from C{connect}'s L{Deferred}.
        """
        connecting = self.wrapper.connect(self.factory)
        pump = self.completer.succeedOnce()
        proto = self.successResultOf(connecting)
        proto.sendString(b'spam')
        self.assertEqual(pump.clientIO.getOutBuffer(), b'4:SPAM,')


    def test_connectionFailure(self):
        """
        Connection failures propagate upward to C{connect}'s L{Deferred}.
        """
        d = self.wrapper.connect(self.factory)
        self.assertNoResult(d)
        self.completer.failOnce(FakeError())
        self.failureResultOf(d, FakeError)


    def test_connectionCancellation(self):
        """
        Cancellation propagates upward to C{connect}'s L{Deferred}.
        """
        d = self.wrapper.connect(self.factory)
        self.assertNoResult(d)
        d.cancel()
        self.failureResultOf(d, ConnectingCancelledError)


    def test_transportOfTransportOfWrappedProtocol(self):
        """
        The transport of the wrapped L{Protocol}'s transport is the transport
        passed to C{makeConnection}.
        """
        connecting = self.wrapper.connect(self.factory)
        pump = self.completer.succeedOnce()
        proto = self.successResultOf(connecting)
        self.assertIs(
            proto.transport.transport, pump.clientIO)



def connectionCreatorFromEndpoint(memoryReactor, tlsEndpoint):
    """
    Given a L{MemoryReactor} and the result of calling L{wrapClientTLS},
    extract the L{IOpenSSLClientConnectionCreator} associated with it.

    Implementation presently uses private attributes but could (and should) be
    refactored to just call C{.connect()} on the endpoint, when
    L{HostnameEndpoint} starts directing its C{getaddrinfo} call through the
    reactor it is passed somehow rather than via the global threadpool.

    @param memoryReactor: the reactor attached to the given endpoint.
        (Presently unused, but included so tests won't need to be modified to
        honor it.)

    @param tlsEndpoint: The result of calling L{wrapClientTLS}.

    @return: the client connection creator associated with the endpoint
        wrapper.
    @rtype: L{IOpenSSLClientConnectionCreator}
    """
    return tlsEndpoint._wrapperFactory(None)._connectionCreator



def makeHostnameEndpointSynchronous(hostnameEndpoint):
    """
    Make the given L{HostnameEndpoint} fire its L{defer.Deferred} from
    C{connect} synchronously by patching its C{_deferToThread} implementation
    to return an already-succeeded Deferred.

    @param hostnameEndpoint: The hostname endpoint to patch.
    """
    family = AF_INET
    socktype = SOCK_STREAM
    proto = IPPROTO_TCP
    canonname = b''
    sockaddr = ('127.0.0.1', 4321)
    gaiResult = family, socktype, proto, canonname, sockaddr
    def synchronousDeferToThreadForGAI(*args):
        return defer.succeed([gaiResult])
    hostnameEndpoint._deferToThread = synchronousDeferToThreadForGAI



class WrapClientTLSParserTests(unittest.TestCase):
    """
    Tests for L{_TLSClientEndpointParser}.
    """

    if skipSSL:
        skip = skipSSL

    def test_hostnameEndpointConstruction(self):
        """
        A L{HostnameEndpoint} is constructed from parameters passed to
        L{clientFromString}.
        """
        reactor = object()
        endpoint = endpoints.clientFromString(
            reactor,
            nativeString(
                'tls:example.com:443:timeout=10:bindAddress=127.0.0.1'))
        hostnameEndpoint = endpoint._wrappedEndpoint
        self.assertIs(hostnameEndpoint._reactor, reactor)
        self.assertEqual(hostnameEndpoint._host, b'example.com')
        self.assertEqual(hostnameEndpoint._port, 443)
        self.assertEqual(hostnameEndpoint._timeout, 10)
        self.assertEqual(hostnameEndpoint._bindAddress,
                         nativeString('127.0.0.1'))


    def test_utf8Encoding(self):
        """
        The hostname passed to L{clientFromString} is treated as utf-8 bytes;
        it is then encoded as IDNA when it is passed along to
        L{HostnameEndpoint}, and passed as unicode to L{optionsForClientTLS}.
        """
        reactor = object()
        endpoint = endpoints.clientFromString(
            reactor, b'tls:\xc3\xa9xample.example.com:443'
        )
        self.assertEqual(
            endpoint._wrappedEndpoint._host, b'xn--xample-9ua.example.com')
        connectionCreator = connectionCreatorFromEndpoint(reactor, endpoint)
        self.assertEqual(connectionCreator._hostname,
                         u'\xe9xample.example.com')


    def test_tls(self):
        """
        When passed a string endpoint description beginning with C{tls:},
        L{clientFromString} returns a client endpoint initialized with the
        values from the string.
        """
        # We can't peer into the unknowable chaos of the heart of OpenSSL
        # (there's no public API to extract from a Context what its trust roots
        # or certificate is); instead, we have to somehow extract information
        # about this stuff from how the context behaves.  So this test is an
        # integration test.

        # There are good examples of how to construct relevant test-fixture
        # data in
        # twisted.test.test_sslverify.certificatesForAuthorityAndServer; that
        # more directly tests the nuances of this code.  Remember that this
        # should test both positive and negative cases.

        reactor = MemoryReactor()

        # The certificate in question here is a self-signed certificate for
        # 'localhost', so use 'localhost' as a hostname and the directory
        # containing the cert itself for the CAs list.
        endpoint = endpoints.clientFromString(
            reactor,
            'tls:localhost:4321:privateKey={}:certificate={}:trustRoots={}'
            .format(
                escapedPEMPathName, escapedPEMPathName,
                endpoints.quoteStringArgument(pemPath.parent().path)
            ).encode('ascii')
        )
        makeHostnameEndpointSynchronous(endpoint._wrappedEndpoint)
        d = endpoint.connect(Factory.forProtocol(Protocol))
        host, port, factory, timeout, bindAddress = reactor.tcpClients.pop()
        clientProtocol = factory.buildProtocol(None)
        self.assertNoResult(d)
        assert clientProtocol is not None
        serverCert = PrivateCertificate.loadPEM(pemPath.getContent())
        serverOptions = CertificateOptions(
            privateKey=serverCert.privateKey.original,
            certificate=serverCert.original,
            extraCertChain=[
                Certificate.loadPEM(chainPath.getContent()).original],
            trustRoot=serverCert,
        )
        plainServer = Protocol()
        serverProtocol = TLSMemoryBIOFactory(
            serverOptions, isClient=False,
            wrappedFactory=Factory.forProtocol(lambda: plainServer)
        ).buildProtocol(None)
        sProto, cProto, pump = connectedServerAndClient(
            lambda: serverProtocol,
            lambda: clientProtocol,
        )
        # verify privateKey
        plainServer.transport.write(b"hello\r\n")
        plainClient = self.successResultOf(d)
        plainClient.transport.write(b"hi you too\r\n")
        pump.flush()
        self.assertFalse(plainServer.transport.disconnecting)
        self.assertFalse(plainClient.transport.disconnecting)
        self.assertFalse(plainServer.transport.disconnected)
        self.assertFalse(plainClient.transport.disconnected)
        peerCertificate = Certificate.peerFromTransport(plainServer.transport)
        self.assertEqual(peerCertificate,
                         Certificate.loadPEM(pemPath.getContent()))


    def test_tlsWithDefaults(self):
        """
        When passed a C{tls:} strports description without extra arguments,
        L{clientFromString} returns a client endpoint whose context factory is
        initialized with default values.
        """
        reactor = object()
        endpoint = endpoints.clientFromString(reactor, b'tls:example.com:443')
        creator = connectionCreatorFromEndpoint(reactor, endpoint)
        self.assertEqual(creator._hostname, u'example.com')
        self.assertEqual(endpoint._wrappedEndpoint._host, b'example.com')



def replacingGlobals(function, **newGlobals):
    """
    Create a copy of the given function with the given globals substituted.

    The globals must already exist in the function's existing global scope.

    @param function: any function object.
    @type function: L{types.FunctionType}

    @param newGlobals: each keyword argument should be a global to set in the
        new function's returned scope.
    @type newGlobals: L{dict}

    @return: a new function, like C{function}, but with new global scope.
    """
    try:
        codeObject = function.func_code
        funcGlobals = function.func_globals
    except AttributeError:
        codeObject = function.__code__
        funcGlobals = function.__globals__
    for key in newGlobals:
        if key not in funcGlobals:
            raise TypeError(
                "Name bound by replacingGlobals but not present in module: {}"
                .format(key)
            )
    mergedGlobals = {}
    mergedGlobals.update(funcGlobals)
    mergedGlobals.update(newGlobals)
    newFunction = FunctionType(codeObject, mergedGlobals)
    mergedGlobals[function.__name__] = newFunction
    return newFunction



class WrapClientTLSTests(unittest.TestCase):
    """
    Tests for the error-reporting behavior of L{wrapClientTLS} when
    C{pyOpenSSL} is unavailable.
    """

    def test_noOpenSSL(self):
        """
        If SSL is not supported, L{TLSMemoryBIOFactory} will be L{None}, which
        causes C{_wrapper} to also be L{None}.  If C{_wrapper} is L{None}, then
        an exception is raised.
        """
        replaced = replacingGlobals(endpoints.wrapClientTLS,
                                    TLSMemoryBIOFactory=None)
        notImplemented = self.assertRaises(NotImplementedError, replaced,
                                           None, None)
        self.assertIn("OpenSSL not available", str(notImplemented))
