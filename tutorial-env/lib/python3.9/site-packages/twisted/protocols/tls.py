# -*- test-case-name: twisted.protocols.test.test_tls,twisted.internet.test.test_tls,twisted.test.test_sslverify -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of a TLS transport (L{ISSLTransport}) as an
L{IProtocol<twisted.internet.interfaces.IProtocol>} layered on top of any
L{ITransport<twisted.internet.interfaces.ITransport>} implementation, based on
U{OpenSSL<http://www.openssl.org>}'s memory BIO features.

L{TLSMemoryBIOFactory} is a L{WrappingFactory} which wraps protocols created by
the factory it wraps with L{TLSMemoryBIOProtocol}.  L{TLSMemoryBIOProtocol}
intercedes between the underlying transport and the wrapped protocol to
implement SSL and TLS.  Typical usage of this module looks like this::

    from twisted.protocols.tls import TLSMemoryBIOFactory
    from twisted.internet.protocol import ServerFactory
    from twisted.internet.ssl import PrivateCertificate
    from twisted.internet import reactor

    from someapplication import ApplicationProtocol

    serverFactory = ServerFactory()
    serverFactory.protocol = ApplicationProtocol
    certificate = PrivateCertificate.loadPEM(certPEMData)
    contextFactory = certificate.options()
    tlsFactory = TLSMemoryBIOFactory(contextFactory, False, serverFactory)
    reactor.listenTCP(12345, tlsFactory)
    reactor.run()

This API offers somewhat more flexibility than
L{twisted.internet.interfaces.IReactorSSL}; for example, a
L{TLSMemoryBIOProtocol} instance can use another instance of
L{TLSMemoryBIOProtocol} as its transport, yielding TLS over TLS - useful to
implement onion routing.  It can also be used to run TLS over unusual
transports, such as UNIX sockets and stdio.
"""


from zope.interface import directlyProvides, implementer, providedBy

from OpenSSL.SSL import Connection, Error, SysCallError, WantReadError, ZeroReturnError

from twisted.internet._producer_helpers import _PullToPush
from twisted.internet._sslverify import _setAcceptableProtocols
from twisted.internet.interfaces import (
    IHandshakeListener,
    ILoggingContext,
    INegotiated,
    IOpenSSLClientConnectionCreator,
    IOpenSSLServerConnectionCreator,
    IProtocolNegotiationFactory,
    IPushProducer,
    ISystemHandle,
)
from twisted.internet.main import CONNECTION_LOST
from twisted.internet.protocol import Protocol
from twisted.protocols.policies import ProtocolWrapper, WrappingFactory
from twisted.python.failure import Failure


@implementer(IPushProducer)
class _ProducerMembrane:
    """
    Stand-in for producer registered with a L{TLSMemoryBIOProtocol} transport.

    Ensures that producer pause/resume events from the undelying transport are
    coordinated with pause/resume events from the TLS layer.

    @ivar _producer: The application-layer producer.
    """

    _producerPaused = False

    def __init__(self, producer):
        self._producer = producer

    def pauseProducing(self):
        """
        C{pauseProducing} the underlying producer, if it's not paused.
        """
        if self._producerPaused:
            return
        self._producerPaused = True
        self._producer.pauseProducing()

    def resumeProducing(self):
        """
        C{resumeProducing} the underlying producer, if it's paused.
        """
        if not self._producerPaused:
            return
        self._producerPaused = False
        self._producer.resumeProducing()

    def stopProducing(self):
        """
        C{stopProducing} the underlying producer.

        There is only a single source for this event, so it's simply passed
        on.
        """
        self._producer.stopProducing()


def _representsEOF(exceptionObject: Error) -> bool:
    """
    Does the given OpenSSL.SSL.Error represent an end-of-file?
    """
    reasonString: str
    if isinstance(exceptionObject, SysCallError):
        _, reasonString = exceptionObject.args
    else:
        errorQueue = exceptionObject.args[0]
        _, _, reasonString = errorQueue[-1]
    return reasonString.casefold().startswith("unexpected eof")


@implementer(ISystemHandle, INegotiated)
class TLSMemoryBIOProtocol(ProtocolWrapper):
    """
    L{TLSMemoryBIOProtocol} is a protocol wrapper which uses OpenSSL via a
    memory BIO to encrypt bytes written to it before sending them on to the
    underlying transport and decrypts bytes received from the underlying
    transport before delivering them to the wrapped protocol.

    In addition to producer events from the underlying transport, the need to
    wait for reads before a write can proceed means the L{TLSMemoryBIOProtocol}
    may also want to pause a producer.  Pause/resume events are therefore
    merged using the L{_ProducerMembrane} wrapper.  Non-streaming (pull)
    producers are supported by wrapping them with L{_PullToPush}.

    @ivar _tlsConnection: The L{OpenSSL.SSL.Connection} instance which is
        encrypted and decrypting this connection.

    @ivar _lostTLSConnection: A flag indicating whether connection loss has
        already been dealt with (C{True}) or not (C{False}).  TLS disconnection
        is distinct from the underlying connection being lost.

    @ivar _appSendBuffer: application-level (cleartext) data that is waiting to
        be transferred to the TLS buffer, but can't be because the TLS
        connection is handshaking.
    @type _appSendBuffer: L{list} of L{bytes}

    @ivar _connectWrapped: A flag indicating whether or not to call
        C{makeConnection} on the wrapped protocol.  This is for the reactor's
        L{twisted.internet.interfaces.ITLSTransport.startTLS} implementation,
        since it has a protocol which it has already called C{makeConnection}
        on, and which has no interest in a new transport.  See #3821.

    @ivar _handshakeDone: A flag indicating whether or not the handshake is
        known to have completed successfully (C{True}) or not (C{False}).  This
        is used to control error reporting behavior.  If the handshake has not
        completed, the underlying L{OpenSSL.SSL.Error} will be passed to the
        application's C{connectionLost} method.  If it has completed, any
        unexpected L{OpenSSL.SSL.Error} will be turned into a
        L{ConnectionLost}.  This is weird; however, it is simply an attempt at
        a faithful re-implementation of the behavior provided by
        L{twisted.internet.ssl}.

    @ivar _reason: If an unexpected L{OpenSSL.SSL.Error} occurs which causes
        the connection to be lost, it is saved here.  If appropriate, this may
        be used as the reason passed to the application protocol's
        C{connectionLost} method.

    @ivar _producer: The current producer registered via C{registerProducer},
        or L{None} if no producer has been registered or a previous one was
        unregistered.

    @ivar _aborted: C{abortConnection} has been called.  No further data will
        be received to the wrapped protocol's C{dataReceived}.
    @type _aborted: L{bool}
    """

    _reason = None
    _handshakeDone = False
    _lostTLSConnection = False
    _producer = None
    _aborted = False

    def __init__(self, factory, wrappedProtocol, _connectWrapped=True):
        ProtocolWrapper.__init__(self, factory, wrappedProtocol)
        self._connectWrapped = _connectWrapped

    def getHandle(self):
        """
        Return the L{OpenSSL.SSL.Connection} object being used to encrypt and
        decrypt this connection.

        This is done for the benefit of L{twisted.internet.ssl.Certificate}'s
        C{peerFromTransport} and C{hostFromTransport} methods only.  A
        different system handle may be returned by future versions of this
        method.
        """
        return self._tlsConnection

    def makeConnection(self, transport):
        """
        Connect this wrapper to the given transport and initialize the
        necessary L{OpenSSL.SSL.Connection} with a memory BIO.
        """
        self._tlsConnection = self.factory._createConnection(self)
        self._appSendBuffer = []

        # Add interfaces provided by the transport we are wrapping:
        for interface in providedBy(transport):
            directlyProvides(self, interface)

        # Intentionally skip ProtocolWrapper.makeConnection - it might call
        # wrappedProtocol.makeConnection, which we want to make conditional.
        Protocol.makeConnection(self, transport)
        self.factory.registerProtocol(self)
        if self._connectWrapped:
            # Now that the TLS layer is initialized, notify the application of
            # the connection.
            ProtocolWrapper.makeConnection(self, transport)

        # Now that we ourselves have a transport (initialized by the
        # ProtocolWrapper.makeConnection call above), kick off the TLS
        # handshake.
        self._checkHandshakeStatus()

    def _checkHandshakeStatus(self):
        """
        Ask OpenSSL to proceed with a handshake in progress.

        Initially, this just sends the ClientHello; after some bytes have been
        stuffed in to the C{Connection} object by C{dataReceived}, it will then
        respond to any C{Certificate} or C{KeyExchange} messages.
        """
        # The connection might already be aborted (eg. by a callback during
        # connection setup), so don't even bother trying to handshake in that
        # case.
        if self._aborted:
            return
        try:
            self._tlsConnection.do_handshake()
        except WantReadError:
            self._flushSendBIO()
        except Error:
            self._tlsShutdownFinished(Failure())
        else:
            self._handshakeDone = True
            if IHandshakeListener.providedBy(self.wrappedProtocol):
                self.wrappedProtocol.handshakeCompleted()

    def _flushSendBIO(self):
        """
        Read any bytes out of the send BIO and write them to the underlying
        transport.
        """
        try:
            bytes = self._tlsConnection.bio_read(2 ** 15)
        except WantReadError:
            # There may be nothing in the send BIO right now.
            pass
        else:
            self.transport.write(bytes)

    def _flushReceiveBIO(self):
        """
        Try to receive any application-level bytes which are now available
        because of a previous write into the receive BIO.  This will take
        care of delivering any application-level bytes which are received to
        the protocol, as well as handling of the various exceptions which
        can come from trying to get such bytes.
        """
        # Keep trying this until an error indicates we should stop or we
        # close the connection.  Looping is necessary to make sure we
        # process all of the data which was put into the receive BIO, as
        # there is no guarantee that a single recv call will do it all.
        while not self._lostTLSConnection:
            try:
                bytes = self._tlsConnection.recv(2 ** 15)
            except WantReadError:
                # The newly received bytes might not have been enough to produce
                # any application data.
                break
            except ZeroReturnError:
                # TLS has shut down and no more TLS data will be received over
                # this connection.
                self._shutdownTLS()
                # Passing in None means the user protocol's connnectionLost
                # will get called with reason from underlying transport:
                self._tlsShutdownFinished(None)
            except Error:
                # Something went pretty wrong.  For example, this might be a
                # handshake failure during renegotiation (because there were no
                # shared ciphers, because a certificate failed to verify, etc).
                # TLS can no longer proceed.
                failure = Failure()
                self._tlsShutdownFinished(failure)
            else:
                if not self._aborted:
                    ProtocolWrapper.dataReceived(self, bytes)

        # The received bytes might have generated a response which needs to be
        # sent now.  For example, the handshake involves several round-trip
        # exchanges without ever producing application-bytes.
        self._flushSendBIO()

    def dataReceived(self, bytes):
        """
        Deliver any received bytes to the receive BIO and then read and deliver
        to the application any application-level data which becomes available
        as a result of this.
        """
        # Let OpenSSL know some bytes were just received.
        self._tlsConnection.bio_write(bytes)

        # If we are still waiting for the handshake to complete, try to
        # complete the handshake with the bytes we just received.
        if not self._handshakeDone:
            self._checkHandshakeStatus()

            # If the handshake still isn't finished, then we've nothing left to
            # do.
            if not self._handshakeDone:
                return

        # If we've any pending writes, this read may have un-blocked them, so
        # attempt to unbuffer them into the OpenSSL layer.
        if self._appSendBuffer:
            self._unbufferPendingWrites()

        # Since the handshake is complete, the wire-level bytes we just
        # processed might turn into some application-level bytes; try to pull
        # those out.
        self._flushReceiveBIO()

    def _shutdownTLS(self):
        """
        Initiate, or reply to, the shutdown handshake of the TLS layer.
        """
        try:
            shutdownSuccess = self._tlsConnection.shutdown()
        except Error:
            # Mid-handshake, a call to shutdown() can result in a
            # WantWantReadError, or rather an SSL_ERR_WANT_READ; but pyOpenSSL
            # doesn't allow us to get at the error.  See:
            # https://github.com/pyca/pyopenssl/issues/91
            shutdownSuccess = False
        self._flushSendBIO()
        if shutdownSuccess:
            # Both sides have shutdown, so we can start closing lower-level
            # transport. This will also happen if we haven't started
            # negotiation at all yet, in which case shutdown succeeds
            # immediately.
            self.transport.loseConnection()

    def _tlsShutdownFinished(self, reason):
        """
        Called when TLS connection has gone away; tell underlying transport to
        disconnect.

        @param reason: a L{Failure} whose value is an L{Exception} if we want to
            report that failure through to the wrapped protocol's
            C{connectionLost}, or L{None} if the C{reason} that
            C{connectionLost} should receive should be coming from the
            underlying transport.
        @type reason: L{Failure} or L{None}
        """
        if reason is not None:
            # Squash an EOF in violation of the TLS protocol into
            # ConnectionLost, so that applications which might run over
            # multiple protocols can recognize its type.
            if _representsEOF(reason.value):
                reason = Failure(CONNECTION_LOST)
        if self._reason is None:
            self._reason = reason
        self._lostTLSConnection = True
        # We may need to send a TLS alert regarding the nature of the shutdown
        # here (for example, why a handshake failed), so always flush our send
        # buffer before telling our lower-level transport to go away.
        self._flushSendBIO()
        # Using loseConnection causes the application protocol's
        # connectionLost method to be invoked non-reentrantly, which is always
        # a nice feature. However, for error cases (reason != None) we might
        # want to use abortConnection when it becomes available. The
        # loseConnection call is basically tested by test_handshakeFailure.
        # At least one side will need to do it or the test never finishes.
        self.transport.loseConnection()

    def connectionLost(self, reason):
        """
        Handle the possible repetition of calls to this method (due to either
        the underlying transport going away or due to an error at the TLS
        layer) and make sure the base implementation only gets invoked once.
        """
        if not self._lostTLSConnection:
            # Tell the TLS connection that it's not going to get any more data
            # and give it a chance to finish reading.
            self._tlsConnection.bio_shutdown()
            self._flushReceiveBIO()
            self._lostTLSConnection = True
        reason = self._reason or reason
        self._reason = None
        self.connected = False
        ProtocolWrapper.connectionLost(self, reason)

        # Breaking reference cycle between self._tlsConnection and self.
        self._tlsConnection = None

    def loseConnection(self):
        """
        Send a TLS close alert and close the underlying connection.
        """
        if self.disconnecting or not self.connected:
            return
        # If connection setup has not finished, OpenSSL 1.0.2f+ will not shut
        # down the connection until we write some data to the connection which
        # allows the handshake to complete. However, since no data should be
        # written after loseConnection, this means we'll be stuck forever
        # waiting for shutdown to complete. Instead, we simply abort the
        # connection without trying to shut down cleanly:
        if not self._handshakeDone and not self._appSendBuffer:
            self.abortConnection()
        self.disconnecting = True
        if not self._appSendBuffer and self._producer is None:
            self._shutdownTLS()

    def abortConnection(self):
        """
        Tear down TLS state so that if the connection is aborted mid-handshake
        we don't deliver any further data from the application.
        """
        self._aborted = True
        self.disconnecting = True
        self._shutdownTLS()
        self.transport.abortConnection()

    def failVerification(self, reason):
        """
        Abort the connection during connection setup, giving a reason that
        certificate verification failed.

        @param reason: The reason that the verification failed; reported to the
            application protocol's C{connectionLost} method.
        @type reason: L{Failure}
        """
        self._reason = reason
        self.abortConnection()

    def write(self, bytes):
        """
        Process the given application bytes and send any resulting TLS traffic
        which arrives in the send BIO.

        If C{loseConnection} was called, subsequent calls to C{write} will
        drop the bytes on the floor.
        """
        if isinstance(bytes, str):
            raise TypeError("Must write bytes to a TLS transport, not str.")
        # Writes after loseConnection are not supported, unless a producer has
        # been registered, in which case writes can happen until the producer
        # is unregistered:
        if self.disconnecting and self._producer is None:
            return
        self._write(bytes)

    def _bufferedWrite(self, octets):
        """
        Put the given octets into L{TLSMemoryBIOProtocol._appSendBuffer}, and
        tell any listening producer that it should pause because we are now
        buffering.
        """
        self._appSendBuffer.append(octets)
        if self._producer is not None:
            self._producer.pauseProducing()

    def _unbufferPendingWrites(self):
        """
        Un-buffer all waiting writes in L{TLSMemoryBIOProtocol._appSendBuffer}.
        """
        pendingWrites, self._appSendBuffer = self._appSendBuffer, []
        for eachWrite in pendingWrites:
            self._write(eachWrite)

        if self._appSendBuffer:
            # If OpenSSL ran out of buffer space in the Connection on our way
            # through the loop earlier and re-buffered any of our outgoing
            # writes, then we're done; don't consider any future work.
            return

        if self._producer is not None:
            # If we have a registered producer, let it know that we have some
            # more buffer space.
            self._producer.resumeProducing()
            return

        if self.disconnecting:
            # Finally, if we have no further buffered data, no producer wants
            # to send us more data in the future, and the application told us
            # to end the stream, initiate a TLS shutdown.
            self._shutdownTLS()

    def _write(self, bytes):
        """
        Process the given application bytes and send any resulting TLS traffic
        which arrives in the send BIO.

        This may be called by C{dataReceived} with bytes that were buffered
        before C{loseConnection} was called, which is why this function
        doesn't check for disconnection but accepts the bytes regardless.
        """
        if self._lostTLSConnection:
            return

        # A TLS payload is 16kB max
        bufferSize = 2 ** 14

        # How far into the input we've gotten so far
        alreadySent = 0

        while alreadySent < len(bytes):
            toSend = bytes[alreadySent : alreadySent + bufferSize]
            try:
                sent = self._tlsConnection.send(toSend)
            except WantReadError:
                self._bufferedWrite(bytes[alreadySent:])
                break
            except Error:
                # Pretend TLS connection disconnected, which will trigger
                # disconnect of underlying transport. The error will be passed
                # to the application protocol's connectionLost method.  The
                # other SSL implementation doesn't, but losing helpful
                # debugging information is a bad idea.
                self._tlsShutdownFinished(Failure())
                break
            else:
                # We've successfully handed off the bytes to the OpenSSL
                # Connection object.
                alreadySent += sent
                # See if OpenSSL wants to hand any bytes off to the underlying
                # transport as a result.
                self._flushSendBIO()

    def writeSequence(self, iovec):
        """
        Write a sequence of application bytes by joining them into one string
        and passing them to L{write}.
        """
        self.write(b"".join(iovec))

    def getPeerCertificate(self):
        return self._tlsConnection.get_peer_certificate()

    @property
    def negotiatedProtocol(self):
        """
        @see: L{INegotiated.negotiatedProtocol}
        """
        protocolName = None

        try:
            # If ALPN is not implemented that's ok, NPN might be.
            protocolName = self._tlsConnection.get_alpn_proto_negotiated()
        except (NotImplementedError, AttributeError):
            pass

        if protocolName not in (b"", None):
            # A protocol was selected using ALPN.
            return protocolName

        try:
            protocolName = self._tlsConnection.get_next_proto_negotiated()
        except (NotImplementedError, AttributeError):
            pass

        if protocolName != b"":
            return protocolName

        return None

    def registerProducer(self, producer, streaming):
        # If we've already disconnected, nothing to do here:
        if self._lostTLSConnection:
            producer.stopProducing()
            return

        # If we received a non-streaming producer, wrap it so it becomes a
        # streaming producer:
        if not streaming:
            producer = streamingProducer = _PullToPush(producer, self)
        producer = _ProducerMembrane(producer)
        # This will raise an exception if a producer is already registered:
        self.transport.registerProducer(producer, True)
        self._producer = producer
        # If we received a non-streaming producer, we need to start the
        # streaming wrapper:
        if not streaming:
            streamingProducer.startStreaming()

    def unregisterProducer(self):
        # If we have no producer, we don't need to do anything here.
        if self._producer is None:
            return

        # If we received a non-streaming producer, we need to stop the
        # streaming wrapper:
        if isinstance(self._producer._producer, _PullToPush):
            self._producer._producer.stopStreaming()
        self._producer = None
        self._producerPaused = False
        self.transport.unregisterProducer()
        if self.disconnecting and not self._appSendBuffer:
            self._shutdownTLS()


@implementer(IOpenSSLClientConnectionCreator, IOpenSSLServerConnectionCreator)
class _ContextFactoryToConnectionFactory:
    """
    Adapter wrapping a L{twisted.internet.interfaces.IOpenSSLContextFactory}
    into a L{IOpenSSLClientConnectionCreator} or
    L{IOpenSSLServerConnectionCreator}.

    See U{https://twistedmatrix.com/trac/ticket/7215} for work that should make
    this unnecessary.
    """

    def __init__(self, oldStyleContextFactory):
        """
        Construct a L{_ContextFactoryToConnectionFactory} with a
        L{twisted.internet.interfaces.IOpenSSLContextFactory}.

        Immediately call C{getContext} on C{oldStyleContextFactory} in order to
        force advance parameter checking, since old-style context factories
        don't actually check that their arguments to L{OpenSSL} are correct.

        @param oldStyleContextFactory: A factory that can produce contexts.
        @type oldStyleContextFactory:
            L{twisted.internet.interfaces.IOpenSSLContextFactory}
        """
        oldStyleContextFactory.getContext()
        self._oldStyleContextFactory = oldStyleContextFactory

    def _connectionForTLS(self, protocol):
        """
        Create an L{OpenSSL.SSL.Connection} object.

        @param protocol: The protocol initiating a TLS connection.
        @type protocol: L{TLSMemoryBIOProtocol}

        @return: a connection
        @rtype: L{OpenSSL.SSL.Connection}
        """
        context = self._oldStyleContextFactory.getContext()
        return Connection(context, None)

    def serverConnectionForTLS(self, protocol):
        """
        Construct an OpenSSL server connection from the wrapped old-style
        context factory.

        @note: Since old-style context factories don't distinguish between
            clients and servers, this is exactly the same as
            L{_ContextFactoryToConnectionFactory.clientConnectionForTLS}.

        @param protocol: The protocol initiating a TLS connection.
        @type protocol: L{TLSMemoryBIOProtocol}

        @return: a connection
        @rtype: L{OpenSSL.SSL.Connection}
        """
        return self._connectionForTLS(protocol)

    def clientConnectionForTLS(self, protocol):
        """
        Construct an OpenSSL server connection from the wrapped old-style
        context factory.

        @note: Since old-style context factories don't distinguish between
            clients and servers, this is exactly the same as
            L{_ContextFactoryToConnectionFactory.serverConnectionForTLS}.

        @param protocol: The protocol initiating a TLS connection.
        @type protocol: L{TLSMemoryBIOProtocol}

        @return: a connection
        @rtype: L{OpenSSL.SSL.Connection}
        """
        return self._connectionForTLS(protocol)


class TLSMemoryBIOFactory(WrappingFactory):
    """
    L{TLSMemoryBIOFactory} adds TLS to connections.

    @ivar _creatorInterface: the interface which L{_connectionCreator} is
        expected to implement.
    @type _creatorInterface: L{zope.interface.interfaces.IInterface}

    @ivar _connectionCreator: a callable which creates an OpenSSL Connection
        object.
    @type _connectionCreator: 1-argument callable taking
        L{TLSMemoryBIOProtocol} and returning L{OpenSSL.SSL.Connection}.
    """

    protocol = TLSMemoryBIOProtocol

    noisy = False  # disable unnecessary logging.

    def __init__(self, contextFactory, isClient, wrappedFactory):
        """
        Create a L{TLSMemoryBIOFactory}.

        @param contextFactory: Configuration parameters used to create an
            OpenSSL connection.  In order of preference, what you should pass
            here should be:

                1. L{twisted.internet.ssl.CertificateOptions} (if you're
                   writing a server) or the result of
                   L{twisted.internet.ssl.optionsForClientTLS} (if you're
                   writing a client).  If you want security you should really
                   use one of these.

                2. If you really want to implement something yourself, supply a
                   provider of L{IOpenSSLClientConnectionCreator} or
                   L{IOpenSSLServerConnectionCreator}.

                3. If you really have to, supply a
                   L{twisted.internet.ssl.ContextFactory}.  This will likely be
                   deprecated at some point so please upgrade to the new
                   interfaces.

        @type contextFactory: L{IOpenSSLClientConnectionCreator} or
            L{IOpenSSLServerConnectionCreator}, or, for compatibility with
            older code, anything implementing
            L{twisted.internet.interfaces.IOpenSSLContextFactory}.  See
            U{https://twistedmatrix.com/trac/ticket/7215} for information on
            the upcoming deprecation of passing a
            L{twisted.internet.ssl.ContextFactory} here.

        @param isClient: Is this a factory for TLS client connections; in other
            words, those that will send a C{ClientHello} greeting?  L{True} if
            so, L{False} otherwise.  This flag determines what interface is
            expected of C{contextFactory}.  If L{True}, C{contextFactory}
            should provide L{IOpenSSLClientConnectionCreator}; otherwise it
            should provide L{IOpenSSLServerConnectionCreator}.
        @type isClient: L{bool}

        @param wrappedFactory: A factory which will create the
            application-level protocol.
        @type wrappedFactory: L{twisted.internet.interfaces.IProtocolFactory}
        """
        WrappingFactory.__init__(self, wrappedFactory)
        if isClient:
            creatorInterface = IOpenSSLClientConnectionCreator
        else:
            creatorInterface = IOpenSSLServerConnectionCreator
        self._creatorInterface = creatorInterface
        if not creatorInterface.providedBy(contextFactory):
            contextFactory = _ContextFactoryToConnectionFactory(contextFactory)
        self._connectionCreator = contextFactory

    def logPrefix(self):
        """
        Annotate the wrapped factory's log prefix with some text indicating TLS
        is in use.

        @rtype: C{str}
        """
        if ILoggingContext.providedBy(self.wrappedFactory):
            logPrefix = self.wrappedFactory.logPrefix()
        else:
            logPrefix = self.wrappedFactory.__class__.__name__
        return f"{logPrefix} (TLS)"

    def _applyProtocolNegotiation(self, connection):
        """
        Applies ALPN/NPN protocol neogitation to the connection, if the factory
        supports it.

        @param connection: The OpenSSL connection object to have ALPN/NPN added
            to it.
        @type connection: L{OpenSSL.SSL.Connection}

        @return: Nothing
        @rtype: L{None}
        """
        if IProtocolNegotiationFactory.providedBy(self.wrappedFactory):
            protocols = self.wrappedFactory.acceptableProtocols()
            context = connection.get_context()
            _setAcceptableProtocols(context, protocols)

        return

    def _createConnection(self, tlsProtocol):
        """
        Create an OpenSSL connection and set it up good.

        @param tlsProtocol: The protocol which is establishing the connection.
        @type tlsProtocol: L{TLSMemoryBIOProtocol}

        @return: an OpenSSL connection object for C{tlsProtocol} to use
        @rtype: L{OpenSSL.SSL.Connection}
        """
        connectionCreator = self._connectionCreator
        if self._creatorInterface is IOpenSSLClientConnectionCreator:
            connection = connectionCreator.clientConnectionForTLS(tlsProtocol)
            self._applyProtocolNegotiation(connection)
            connection.set_connect_state()
        else:
            connection = connectionCreator.serverConnectionForTLS(tlsProtocol)
            self._applyProtocolNegotiation(connection)
            connection.set_accept_state()
        return connection
