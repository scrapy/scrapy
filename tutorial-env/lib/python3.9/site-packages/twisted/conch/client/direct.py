# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.conch import error
from twisted.conch.ssh import transport
from twisted.internet import defer, protocol, reactor


class SSHClientFactory(protocol.ClientFactory):
    def __init__(self, d, options, verifyHostKey, userAuthObject):
        self.d = d
        self.options = options
        self.verifyHostKey = verifyHostKey
        self.userAuthObject = userAuthObject

    def clientConnectionLost(self, connector, reason):
        if self.options["reconnect"]:
            connector.connect()

    def clientConnectionFailed(self, connector, reason):
        if self.d is None:
            return
        d, self.d = self.d, None
        d.errback(reason)

    def buildProtocol(self, addr):
        trans = SSHClientTransport(self)
        if self.options["ciphers"]:
            trans.supportedCiphers = self.options["ciphers"]
        if self.options["macs"]:
            trans.supportedMACs = self.options["macs"]
        if self.options["compress"]:
            trans.supportedCompressions[0:1] = ["zlib"]
        if self.options["host-key-algorithms"]:
            trans.supportedPublicKeys = self.options["host-key-algorithms"]
        return trans


class SSHClientTransport(transport.SSHClientTransport):
    def __init__(self, factory):
        self.factory = factory
        self.unixServer = None

    def connectionLost(self, reason):
        if self.unixServer:
            d = self.unixServer.stopListening()
            self.unixServer = None
        else:
            d = defer.succeed(None)
        d.addCallback(
            lambda x: transport.SSHClientTransport.connectionLost(self, reason)
        )

    def receiveError(self, code, desc):
        if self.factory.d is None:
            return
        d, self.factory.d = self.factory.d, None
        d.errback(error.ConchError(desc, code))

    def sendDisconnect(self, code, reason):
        if self.factory.d is None:
            return
        d, self.factory.d = self.factory.d, None
        transport.SSHClientTransport.sendDisconnect(self, code, reason)
        d.errback(error.ConchError(reason, code))

    def receiveDebug(self, alwaysDisplay, message, lang):
        self._log.debug(
            "Received Debug Message: {message}",
            message=message,
            alwaysDisplay=alwaysDisplay,
            lang=lang,
        )
        if alwaysDisplay:  # XXX what should happen here?
            print(message)

    def verifyHostKey(self, pubKey, fingerprint):
        return self.factory.verifyHostKey(
            self, self.transport.getPeer().host, pubKey, fingerprint
        )

    def setService(self, service):
        self._log.info("setting client server to {service}", service=service)
        transport.SSHClientTransport.setService(self, service)
        if service.name != "ssh-userauth" and self.factory.d is not None:
            d, self.factory.d = self.factory.d, None
            d.callback(None)

    def connectionSecure(self):
        self.requestService(self.factory.userAuthObject)


def connect(host, port, options, verifyHostKey, userAuthObject):
    d = defer.Deferred()
    factory = SSHClientFactory(d, options, verifyHostKey, userAuthObject)
    reactor.connectTCP(host, port, factory)
    return d
