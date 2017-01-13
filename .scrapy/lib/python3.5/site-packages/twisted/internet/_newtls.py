# -*- test-case-name: twisted.test.test_ssl -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module implements memory BIO based TLS support.  It is the preferred
implementation and will be used whenever pyOpenSSL 0.10 or newer is installed
(whenever L{twisted.protocols.tls} is importable).

@since: 11.1
"""

from __future__ import division, absolute_import

from zope.interface import implementer
from zope.interface import directlyProvides

from twisted.internet.interfaces import ITLSTransport, ISSLTransport
from twisted.internet.abstract import FileDescriptor

from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol


class _BypassTLS(object):
    """
    L{_BypassTLS} is used as the transport object for the TLS protocol object
    used to implement C{startTLS}.  Its methods skip any TLS logic which
    C{startTLS} enables.

    @ivar _base: A transport class L{_BypassTLS} has been mixed in with to which
        methods will be forwarded.  This class is only responsible for sending
        bytes over the connection, not doing TLS.

    @ivar _connection: A L{Connection} which TLS has been started on which will
        be proxied to by this object.  Any method which has its behavior
        altered after C{startTLS} will be skipped in favor of the base class's
        implementation.  This allows the TLS protocol object to have direct
        access to the transport, necessary to actually implement TLS.
    """
    def __init__(self, base, connection):
        self._base = base
        self._connection = connection


    def __getattr__(self, name):
        """
        Forward any extra attribute access to the original transport object.
        For example, this exposes C{getHost}, the behavior of which does not
        change after TLS is enabled.
        """
        return getattr(self._connection, name)


    def write(self, data):
        """
        Write some bytes directly to the connection.
        """
        return self._base.write(self._connection, data)


    def writeSequence(self, iovec):
        """
        Write a some bytes directly to the connection.
        """
        return self._base.writeSequence(self._connection, iovec)


    def loseConnection(self, *args, **kwargs):
        """
        Close the underlying connection.
        """
        return self._base.loseConnection(self._connection, *args, **kwargs)


    def registerProducer(self, producer, streaming):
        """
        Register a producer with the underlying connection.
        """
        return self._base.registerProducer(self._connection, producer, streaming)


    def unregisterProducer(self):
        """
        Unregister a producer with the underlying connection.
        """
        return self._base.unregisterProducer(self._connection)



def startTLS(transport, contextFactory, normal, bypass):
    """
    Add a layer of SSL to a transport.

    @param transport: The transport which will be modified.  This can either by
        a L{FileDescriptor<twisted.internet.abstract.FileDescriptor>} or a
        L{FileHandle<twisted.internet.iocpreactor.abstract.FileHandle>}.  The
        actual requirements of this instance are that it have:

          - a C{_tlsClientDefault} attribute indicating whether the transport is
            a client (C{True}) or a server (C{False})
          - a settable C{TLS} attribute which can be used to mark the fact
            that SSL has been started
          - settable C{getHandle} and C{getPeerCertificate} attributes so
            these L{ISSLTransport} methods can be added to it
          - a C{protocol} attribute referring to the L{IProtocol} currently
            connected to the transport, which can also be set to a new
            L{IProtocol} for the transport to deliver data to

    @param contextFactory: An SSL context factory defining SSL parameters for
        the new SSL layer.
    @type contextFactory: L{twisted.internet.interfaces.IOpenSSLContextFactory}

    @param normal: A flag indicating whether SSL will go in the same direction
        as the underlying transport goes.  That is, if the SSL client will be
        the underlying client and the SSL server will be the underlying server.
        C{True} means it is the same, C{False} means they are switched.
    @type param: L{bool}

    @param bypass: A transport base class to call methods on to bypass the new
        SSL layer (so that the SSL layer itself can send its bytes).
    @type bypass: L{type}
    """
    # Figure out which direction the SSL goes in.  If normal is True,
    # we'll go in the direction indicated by the subclass.  Otherwise,
    # we'll go the other way (client = not normal ^ _tlsClientDefault,
    # in other words).
    if normal:
        client = transport._tlsClientDefault
    else:
        client = not transport._tlsClientDefault

    # If we have a producer, unregister it, and then re-register it below once
    # we've switched to TLS mode, so it gets hooked up correctly:
    producer, streaming = None, None
    if transport.producer is not None:
        producer, streaming = transport.producer, transport.streamingProducer
        transport.unregisterProducer()

    tlsFactory = TLSMemoryBIOFactory(contextFactory, client, None)
    tlsProtocol = TLSMemoryBIOProtocol(tlsFactory, transport.protocol, False)
    transport.protocol = tlsProtocol

    transport.getHandle = tlsProtocol.getHandle
    transport.getPeerCertificate = tlsProtocol.getPeerCertificate

    # Mark the transport as secure.
    directlyProvides(transport, ISSLTransport)

    # Remember we did this so that write and writeSequence can send the
    # data to the right place.
    transport.TLS = True

    # Hook it up
    transport.protocol.makeConnection(_BypassTLS(bypass, transport))

    # Restore producer if necessary:
    if producer:
        transport.registerProducer(producer, streaming)



@implementer(ITLSTransport)
class ConnectionMixin(object):
    """
    A mixin for L{twisted.internet.abstract.FileDescriptor} which adds an
    L{ITLSTransport} implementation.

    @ivar TLS: A flag indicating whether TLS is currently in use on this
        transport.  This is not a good way for applications to check for TLS,
        instead use L{twisted.internet.interfaces.ISSLTransport}.
    """

    TLS = False

    def startTLS(self, ctx, normal=True):
        """
        @see: L{ITLSTransport.startTLS}
        """
        startTLS(self, ctx, normal, FileDescriptor)


    def write(self, bytes):
        """
        Write some bytes to this connection, passing them through a TLS layer if
        necessary, or discarding them if the connection has already been lost.
        """
        if self.TLS:
            if self.connected:
                self.protocol.write(bytes)
        else:
            FileDescriptor.write(self, bytes)


    def writeSequence(self, iovec):
        """
        Write some bytes to this connection, scatter/gather-style, passing them
        through a TLS layer if necessary, or discarding them if the connection
        has already been lost.
        """
        if self.TLS:
            if self.connected:
                self.protocol.writeSequence(iovec)
        else:
            FileDescriptor.writeSequence(self, iovec)


    def loseConnection(self):
        """
        Close this connection after writing all pending data.

        If TLS has been negotiated, perform a TLS shutdown.
        """
        if self.TLS:
            if self.connected and not self.disconnecting:
                self.protocol.loseConnection()
        else:
            FileDescriptor.loseConnection(self)


    def registerProducer(self, producer, streaming):
        """
        Register a producer.

        If TLS is enabled, the TLS connection handles this.
        """
        if self.TLS:
            # Registering a producer before we're connected shouldn't be a
            # problem. If we end up with a write(), that's already handled in
            # the write() code above, and there are no other potential
            # side-effects.
            self.protocol.registerProducer(producer, streaming)
        else:
            FileDescriptor.registerProducer(self, producer, streaming)


    def unregisterProducer(self):
        """
        Unregister a producer.

        If TLS is enabled, the TLS connection handles this.
        """
        if self.TLS:
            self.protocol.unregisterProducer()
        else:
            FileDescriptor.unregisterProducer(self)



class ClientMixin(object):
    """
    A mixin for L{twisted.internet.tcp.Client} which just marks it as a client
    for the purposes of the default TLS handshake.

    @ivar _tlsClientDefault: Always C{True}, indicating that this is a client
        connection, and by default when TLS is negotiated this class will act as
        a TLS client.
    """
    _tlsClientDefault = True



class ServerMixin(object):
    """
    A mixin for L{twisted.internet.tcp.Server} which just marks it as a server
    for the purposes of the default TLS handshake.

    @ivar _tlsClientDefault: Always C{False}, indicating that this is a server
        connection, and by default when TLS is negotiated this class will act as
        a TLS server.
    """
    _tlsClientDefault = False
