# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A Factory for SSH servers.

See also L{twisted.conch.openssh_compat.factory} for OpenSSH compatibility.

Maintainer: Paul Swartz
"""


import random
from itertools import chain

from twisted.conch import error
from twisted.conch.ssh import _kex, connection, transport, userauth
from twisted.internet import protocol
from twisted.logger import Logger


class SSHFactory(protocol.Factory):
    """
    A Factory for SSH servers.
    """

    _log = Logger()
    protocol = transport.SSHServerTransport

    services = {
        b"ssh-userauth": userauth.SSHUserAuthServer,
        b"ssh-connection": connection.SSHConnection,
    }

    def startFactory(self):
        """
        Check for public and private keys.
        """
        if not hasattr(self, "publicKeys"):
            self.publicKeys = self.getPublicKeys()
        if not hasattr(self, "privateKeys"):
            self.privateKeys = self.getPrivateKeys()
        if not self.publicKeys or not self.privateKeys:
            raise error.ConchError("no host keys, failing")
        if not hasattr(self, "primes"):
            self.primes = self.getPrimes()

    def buildProtocol(self, addr):
        """
        Create an instance of the server side of the SSH protocol.

        @type addr: L{twisted.internet.interfaces.IAddress} provider
        @param addr: The address at which the server will listen.

        @rtype: L{twisted.conch.ssh.transport.SSHServerTransport}
        @return: The built transport.
        """
        t = protocol.Factory.buildProtocol(self, addr)
        t.supportedPublicKeys = list(
            chain.from_iterable(
                key.supportedSignatureAlgorithms() for key in self.privateKeys.values()
            )
        )
        if not self.primes:
            self._log.info(
                "disabling non-fixed-group key exchange algorithms "
                "because we cannot find moduli file"
            )
            t.supportedKeyExchanges = [
                kexAlgorithm
                for kexAlgorithm in t.supportedKeyExchanges
                if _kex.isFixedGroup(kexAlgorithm) or _kex.isEllipticCurve(kexAlgorithm)
            ]
        return t

    def getPublicKeys(self):
        """
        Called when the factory is started to get the public portions of the
        servers host keys.  Returns a dictionary mapping SSH key types to
        public key strings.

        @rtype: L{dict}
        """
        raise NotImplementedError("getPublicKeys unimplemented")

    def getPrivateKeys(self):
        """
        Called when the factory is started to get the  private portions of the
        servers host keys.  Returns a dictionary mapping SSH key types to
        L{twisted.conch.ssh.keys.Key} objects.

        @rtype: L{dict}
        """
        raise NotImplementedError("getPrivateKeys unimplemented")

    def getPrimes(self):
        """
        Called when the factory is started to get Diffie-Hellman generators and
        primes to use.  Returns a dictionary mapping number of bits to lists
        of tuple of (generator, prime).

        @rtype: L{dict}
        """

    def getDHPrime(self, bits):
        """
        Return a tuple of (g, p) for a Diffe-Hellman process, with p being as
        close to bits bits as possible.

        @type bits: L{int}
        @rtype:     L{tuple}
        """
        primesKeys = sorted(self.primes.keys(), key=lambda i: abs(i - bits))
        realBits = primesKeys[0]
        return random.choice(self.primes[realBits])

    def getService(self, transport, service):
        """
        Return a class to use as a service for the given transport.

        @type transport:    L{transport.SSHServerTransport}
        @type service:      L{bytes}
        @rtype:             subclass of L{service.SSHService}
        """
        if service == b"ssh-userauth" or hasattr(transport, "avatar"):
            return self.services[service]
