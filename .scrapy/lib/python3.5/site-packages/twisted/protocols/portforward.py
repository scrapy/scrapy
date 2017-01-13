
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A simple port forwarder.
"""

# Twisted imports
from twisted.internet import protocol
from twisted.python import log

class Proxy(protocol.Protocol):
    noisy = True

    peer = None

    def setPeer(self, peer):
        self.peer = peer


    def connectionLost(self, reason):
        if self.peer is not None:
            self.peer.transport.loseConnection()
            self.peer = None
        elif self.noisy:
            log.msg("Unable to connect to peer: %s" % (reason,))


    def dataReceived(self, data):
        self.peer.transport.write(data)



class ProxyClient(Proxy):
    def connectionMade(self):
        self.peer.setPeer(self)

        # Wire this and the peer transport together to enable
        # flow control (this stops connections from filling
        # this proxy memory when one side produces data at a
        # higher rate than the other can consume).
        self.transport.registerProducer(self.peer.transport, True)
        self.peer.transport.registerProducer(self.transport, True)

        # We're connected, everybody can read to their hearts content.
        self.peer.transport.resumeProducing()



class ProxyClientFactory(protocol.ClientFactory):

    protocol = ProxyClient

    def setServer(self, server):
        self.server = server


    def buildProtocol(self, *args, **kw):
        prot = protocol.ClientFactory.buildProtocol(self, *args, **kw)
        prot.setPeer(self.server)
        return prot


    def clientConnectionFailed(self, connector, reason):
        self.server.transport.loseConnection()



class ProxyServer(Proxy):

    clientProtocolFactory = ProxyClientFactory
    reactor = None

    def connectionMade(self):
        # Don't read anything from the connecting client until we have
        # somewhere to send it to.
        self.transport.pauseProducing()

        client = self.clientProtocolFactory()
        client.setServer(self)

        if self.reactor is None:
            from twisted.internet import reactor
            self.reactor = reactor
        self.reactor.connectTCP(self.factory.host, self.factory.port, client)



class ProxyFactory(protocol.Factory):
    """
    Factory for port forwarder.
    """

    protocol = ProxyServer

    def __init__(self, host, port):
        self.host = host
        self.port = port
