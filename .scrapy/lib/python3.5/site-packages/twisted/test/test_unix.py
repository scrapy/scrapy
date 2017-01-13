# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorUNIX} and L{IReactorUNIXDatagram}.
"""

from __future__ import division, absolute_import

import os
import sys
import types
import socket

from twisted.internet import interfaces, reactor, protocol, error, address
from twisted.internet import defer, utils
from twisted.python import lockfile
from twisted.python.compat import _PY3, networkString
from twisted.python.filepath import FilePath
from twisted.trial import unittest

from twisted.test.test_tcp import MyServerFactory, MyClientFactory


class FailedConnectionClientFactory(protocol.ClientFactory):
    def __init__(self, onFail):
        self.onFail = onFail

    def clientConnectionFailed(self, connector, reason):
        self.onFail.errback(reason)



class UnixSocketTests(unittest.TestCase):
    """
    Test unix sockets.
    """
    def test_peerBind(self):
        """
        The address passed to the server factory's C{buildProtocol} method and
        the address returned by the connected protocol's transport's C{getPeer}
        method match the address the client socket is bound to.
        """
        filename = self.mktemp()
        peername = self.mktemp()
        serverFactory = MyServerFactory()
        connMade = serverFactory.protocolConnectionMade = defer.Deferred()
        unixPort = reactor.listenUNIX(filename, serverFactory)
        self.addCleanup(unixPort.stopListening)
        unixSocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(unixSocket.close)
        unixSocket.bind(peername)
        unixSocket.connect(filename)
        def cbConnMade(proto):
            expected = address.UNIXAddress(peername)
            self.assertEqual(serverFactory.peerAddresses, [expected])
            self.assertEqual(proto.transport.getPeer(), expected)
        connMade.addCallback(cbConnMade)
        return connMade


    def test_dumber(self):
        """
        L{IReactorUNIX.connectUNIX} can be used to connect a client to a server
        started with L{IReactorUNIX.listenUNIX}.
        """
        filename = self.mktemp()
        serverFactory = MyServerFactory()
        serverConnMade = defer.Deferred()
        serverFactory.protocolConnectionMade = serverConnMade
        unixPort = reactor.listenUNIX(filename, serverFactory)
        self.addCleanup(unixPort.stopListening)
        clientFactory = MyClientFactory()
        clientConnMade = defer.Deferred()
        clientFactory.protocolConnectionMade = clientConnMade
        reactor.connectUNIX(filename, clientFactory)
        d = defer.gatherResults([serverConnMade, clientConnMade])
        def allConnected(args):
            serverProtocol, clientProtocol = args
            # Incidental assertion which may or may not be redundant with some
            # other test.  This probably deserves its own test method.
            self.assertEqual(clientFactory.peerAddresses,
                             [address.UNIXAddress(filename)])

            clientProtocol.transport.loseConnection()
            serverProtocol.transport.loseConnection()
        d.addCallback(allConnected)
        return d


    def test_pidFile(self):
        """
        A lockfile is created and locked when L{IReactorUNIX.listenUNIX} is
        called and released when the Deferred returned by the L{IListeningPort}
        provider's C{stopListening} method is called back.
        """
        filename = self.mktemp()
        serverFactory = MyServerFactory()
        serverConnMade = defer.Deferred()
        serverFactory.protocolConnectionMade = serverConnMade
        unixPort = reactor.listenUNIX(filename, serverFactory, wantPID=True)
        self.assertTrue(lockfile.isLocked(filename + ".lock"))

        # XXX This part would test something about the checkPID parameter, but
        # it doesn't actually.  It should be rewritten to test the several
        # different possible behaviors.  -exarkun
        clientFactory = MyClientFactory()
        clientConnMade = defer.Deferred()
        clientFactory.protocolConnectionMade = clientConnMade
        reactor.connectUNIX(filename, clientFactory, checkPID=1)

        d = defer.gatherResults([serverConnMade, clientConnMade])
        def _portStuff(args):
            serverProtocol, clientProto = args

            # Incidental assertion which may or may not be redundant with some
            # other test.  This probably deserves its own test method.
            self.assertEqual(clientFactory.peerAddresses,
                             [address.UNIXAddress(filename)])

            clientProto.transport.loseConnection()
            serverProtocol.transport.loseConnection()
            return unixPort.stopListening()
        d.addCallback(_portStuff)

        def _check(ignored):
            self.assertFalse(lockfile.isLocked(filename + ".lock"), 'locked')
        d.addCallback(_check)
        return d


    def test_socketLocking(self):
        """
        L{IReactorUNIX.listenUNIX} raises L{error.CannotListenError} if passed
        the name of a file on which a server is already listening.
        """
        filename = self.mktemp()
        serverFactory = MyServerFactory()
        unixPort = reactor.listenUNIX(filename, serverFactory, wantPID=True)

        self.assertRaises(
            error.CannotListenError,
            reactor.listenUNIX, filename, serverFactory, wantPID=True)

        def stoppedListening(ign):
            unixPort = reactor.listenUNIX(filename, serverFactory, wantPID=True)
            return unixPort.stopListening()

        return unixPort.stopListening().addCallback(stoppedListening)


    def _uncleanSocketTest(self, callback):
        self.filename = self.mktemp()
        source = networkString((
            "from twisted.internet import protocol, reactor\n"
            "reactor.listenUNIX(%r, protocol.ServerFactory(),"
            "wantPID=True)\n") % (self.filename,))
        env = {b'PYTHONPATH': FilePath(
            os.pathsep.join(sys.path)).asBytesMode().path}
        pyExe = FilePath(sys.executable).asBytesMode().path

        d = utils.getProcessValue(pyExe, (b"-u", b"-c", source), env=env)
        d.addCallback(callback)
        return d


    def test_uncleanServerSocketLocking(self):
        """
        If passed C{True} for the C{wantPID} parameter, a server can be started
        listening with L{IReactorUNIX.listenUNIX} when passed the name of a
        file on which a previous server which has not exited cleanly has been
        listening using the C{wantPID} option.
        """
        def ranStupidChild(ign):
            # If this next call succeeds, our lock handling is correct.
            p = reactor.listenUNIX(self.filename, MyServerFactory(), wantPID=True)
            return p.stopListening()
        return self._uncleanSocketTest(ranStupidChild)


    def test_connectToUncleanServer(self):
        """
        If passed C{True} for the C{checkPID} parameter, a client connection
        attempt made with L{IReactorUNIX.connectUNIX} fails with
        L{error.BadFileError}.
        """
        def ranStupidChild(ign):
            d = defer.Deferred()
            f = FailedConnectionClientFactory(d)
            reactor.connectUNIX(self.filename, f, checkPID=True)
            return self.assertFailure(d, error.BadFileError)
        return self._uncleanSocketTest(ranStupidChild)


    def _reprTest(self, serverFactory, factoryName):
        """
        Test the C{__str__} and C{__repr__} implementations of a UNIX port when
        used with the given factory.
        """
        filename = self.mktemp()
        unixPort = reactor.listenUNIX(filename, serverFactory)

        connectedString = "<%s on %r>" % (factoryName, filename)
        self.assertEqual(repr(unixPort), connectedString)
        self.assertEqual(str(unixPort), connectedString)

        d = defer.maybeDeferred(unixPort.stopListening)
        def stoppedListening(ign):
            unconnectedString = "<%s (not listening)>" % (factoryName,)
            self.assertEqual(repr(unixPort), unconnectedString)
            self.assertEqual(str(unixPort), unconnectedString)
        d.addCallback(stoppedListening)
        return d


    def test_reprWithClassicFactory(self):
        """
        The two string representations of the L{IListeningPort} returned by
        L{IReactorUNIX.listenUNIX} contains the name of the classic factory
        class being used and the filename on which the port is listening or
        indicates that the port is not listening.
        """
        class ClassicFactory:
            def doStart(self):
                pass

            def doStop(self):
                pass

        # Sanity check
        self.assertIsInstance(ClassicFactory, types.ClassType)

        return self._reprTest(
            ClassicFactory(), "twisted.test.test_unix.ClassicFactory")

    if _PY3:
        test_reprWithClassicFactory.skip = (
            "Classic classes do not exist on Python 3.")


    def test_reprWithNewStyleFactory(self):
        """
        The two string representations of the L{IListeningPort} returned by
        L{IReactorUNIX.listenUNIX} contains the name of the new-style factory
        class being used and the filename on which the port is listening or
        indicates that the port is not listening.
        """
        class NewStyleFactory(object):
            def doStart(self):
                pass

            def doStop(self):
                pass

        # Sanity check
        self.assertIsInstance(NewStyleFactory, type)

        return self._reprTest(
            NewStyleFactory(), "twisted.test.test_unix.NewStyleFactory")



class ClientProto(protocol.ConnectedDatagramProtocol):
    started = stopped = False
    gotback = None

    def __init__(self):
        self.deferredStarted = defer.Deferred()
        self.deferredGotBack = defer.Deferred()

    def stopProtocol(self):
        self.stopped = True

    def startProtocol(self):
        self.started = True
        self.deferredStarted.callback(None)

    def datagramReceived(self, data):
        self.gotback = data
        self.deferredGotBack.callback(None)



class ServerProto(protocol.DatagramProtocol):
    started = stopped = False
    gotwhat = gotfrom = None

    def __init__(self):
        self.deferredStarted = defer.Deferred()
        self.deferredGotWhat = defer.Deferred()

    def stopProtocol(self):
        self.stopped = True

    def startProtocol(self):
        self.started = True
        self.deferredStarted.callback(None)

    def datagramReceived(self, data, addr):
        self.gotfrom = addr
        self.transport.write(b"hi back", addr)
        self.gotwhat = data
        self.deferredGotWhat.callback(None)



class DatagramUnixSocketTests(unittest.TestCase):
    """
    Test datagram UNIX sockets.
    """
    def test_exchange(self):
        """
        Test that a datagram can be sent to and received by a server and vice
        versa.
        """
        clientaddr = self.mktemp()
        serveraddr = self.mktemp()
        sp = ServerProto()
        cp = ClientProto()
        s = reactor.listenUNIXDatagram(serveraddr, sp)
        self.addCleanup(s.stopListening)
        c = reactor.connectUNIXDatagram(serveraddr, cp, bindAddress=clientaddr)
        self.addCleanup(c.stopListening)

        d = defer.gatherResults([sp.deferredStarted, cp.deferredStarted])
        def write(ignored):
            cp.transport.write(b"hi")
            return defer.gatherResults([sp.deferredGotWhat,
                                        cp.deferredGotBack])

        def _cbTestExchange(ignored):
            self.assertEqual(b"hi", sp.gotwhat)
            self.assertEqual(clientaddr, sp.gotfrom)
            self.assertEqual(b"hi back", cp.gotback)

        d.addCallback(write)
        d.addCallback(_cbTestExchange)
        return d


    def test_cannotListen(self):
        """
        L{IReactorUNIXDatagram.listenUNIXDatagram} raises
        L{error.CannotListenError} if the unix socket specified is already in
        use.
        """
        addr = self.mktemp()
        p = ServerProto()
        s = reactor.listenUNIXDatagram(addr, p)
        self.assertRaises(error.CannotListenError,
                          reactor.listenUNIXDatagram, addr, p)
        s.stopListening()
        os.unlink(addr)

    # test connecting to bound and connected (somewhere else) address

    def _reprTest(self, serverProto, protocolName):
        """
        Test the C{__str__} and C{__repr__} implementations of a UNIX datagram
        port when used with the given protocol.
        """
        filename = self.mktemp()
        unixPort = reactor.listenUNIXDatagram(filename, serverProto)

        connectedString = "<%s on %r>" % (protocolName, filename)
        self.assertEqual(repr(unixPort), connectedString)
        self.assertEqual(str(unixPort), connectedString)

        stopDeferred = defer.maybeDeferred(unixPort.stopListening)
        def stoppedListening(ign):
            unconnectedString = "<%s (not listening)>" % (protocolName,)
            self.assertEqual(repr(unixPort), unconnectedString)
            self.assertEqual(str(unixPort), unconnectedString)
        stopDeferred.addCallback(stoppedListening)
        return stopDeferred


    def test_reprWithClassicProtocol(self):
        """
        The two string representations of the L{IListeningPort} returned by
        L{IReactorUNIXDatagram.listenUNIXDatagram} contains the name of the
        classic protocol class being used and the filename on which the port is
        listening or indicates that the port is not listening.
        """
        class ClassicProtocol:
            def makeConnection(self, transport):
                pass

            def doStop(self):
                pass

        # Sanity check
        self.assertIsInstance(ClassicProtocol, types.ClassType)

        return self._reprTest(
            ClassicProtocol(), "twisted.test.test_unix.ClassicProtocol")

    if _PY3:
        test_reprWithClassicProtocol.skip = (
            "Classic classes do not exist on Python 3.")


    def test_reprWithNewStyleProtocol(self):
        """
        The two string representations of the L{IListeningPort} returned by
        L{IReactorUNIXDatagram.listenUNIXDatagram} contains the name of the
        new-style protocol class being used and the filename on which the port
        is listening or indicates that the port is not listening.
        """
        class NewStyleProtocol(object):
            def makeConnection(self, transport):
                pass

            def doStop(self):
                pass

        # Sanity check
        self.assertIsInstance(NewStyleProtocol, type)

        return self._reprTest(
            NewStyleProtocol(), "twisted.test.test_unix.NewStyleProtocol")



if not interfaces.IReactorUNIX(reactor, None):
    UnixSocketTests.skip = "This reactor does not support UNIX domain sockets"
if not interfaces.IReactorUNIXDatagram(reactor, None):
    DatagramUnixSocketTests.skip = "This reactor does not support UNIX datagram sockets"
