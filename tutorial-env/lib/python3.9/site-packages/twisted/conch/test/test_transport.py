# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for ssh/transport.py and the classes therein.
"""


import binascii
import re
import string
import struct
import types
from hashlib import md5, sha1, sha256, sha384, sha512
from typing import Optional, Type

from twisted import __version__ as twisted_version
from twisted.conch.error import ConchError
from twisted.conch.ssh import _kex, address, service
from twisted.internet import defer
from twisted.protocols import loopback
from twisted.python import randbytes
from twisted.python.compat import iterbytes
from twisted.python.randbytes import insecureRandom
from twisted.python.reflect import requireModule
from twisted.test import proto_helpers
from twisted.trial.unittest import TestCase

pyasn1 = requireModule("pyasn1")
cryptography = requireModule("cryptography")

dependencySkip: Optional[str]
if pyasn1 and cryptography:
    dependencySkip = None
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import dh, ec

    from twisted.conch.ssh import common, factory, keys, transport
    from twisted.conch.test import keydata

    X25519_SUPPORTED = default_backend().x25519_supported()
else:
    if not pyasn1:
        dependencySkip = "Cannot run without PyASN1"
    elif not cryptography:
        dependencySkip = "can't run without cryptography"
    X25519_SUPPORTED = False

    # fictional modules to make classes work
    class transport:  # type: ignore[no-redef]
        class SSHTransportBase:
            pass

        class SSHServerTransport:
            pass

        class SSHClientTransport:
            pass

    class factory:  # type: ignore[no-redef]
        class SSHFactory:
            pass

    class common:  # type: ignore[no-redef]
        @classmethod
        def NS(self, arg):
            return b""


def skipWithoutX25519(f):
    if not X25519_SUPPORTED:
        f.skip = "x25519 not supported on this system"
    return f


def _MPpow(x, y, z):
    """
    Return the MP version of C{(x ** y) % z}.
    """
    return common.MP(pow(x, y, z))


class MockTransportBase(transport.SSHTransportBase):
    """
    A base class for the client and server protocols.  Stores the messages
    it receives instead of ignoring them.

    @ivar errors: a list of tuples: (reasonCode, description)
    @ivar unimplementeds: a list of integers: sequence number
    @ivar debugs: a list of tuples: (alwaysDisplay, message, lang)
    @ivar ignoreds: a list of strings: ignored data
    """

    def connectionMade(self):
        """
        Set up instance variables.
        """
        transport.SSHTransportBase.connectionMade(self)
        self.errors = []
        self.unimplementeds = []
        self.debugs = []
        self.ignoreds = []
        self.gotUnsupportedVersion = None

    def _unsupportedVersionReceived(self, remoteVersion):
        """
        Intercept unsupported version call.

        @type remoteVersion: L{str}
        """
        self.gotUnsupportedVersion = remoteVersion
        return transport.SSHTransportBase._unsupportedVersionReceived(
            self, remoteVersion
        )

    def receiveError(self, reasonCode, description):
        """
        Store any errors received.

        @type reasonCode: L{int}
        @type description: L{str}
        """
        self.errors.append((reasonCode, description))

    def receiveUnimplemented(self, seqnum):
        """
        Store any unimplemented packet messages.

        @type seqnum: L{int}
        """
        self.unimplementeds.append(seqnum)

    def receiveDebug(self, alwaysDisplay, message, lang):
        """
        Store any debug messages.

        @type alwaysDisplay: L{bool}
        @type message: L{str}
        @type lang: L{str}
        """
        self.debugs.append((alwaysDisplay, message, lang))

    def ssh_IGNORE(self, packet):
        """
        Store any ignored data.

        @type packet: L{str}
        """
        self.ignoreds.append(packet)


class MockCipher:
    """
    A mocked-up version of twisted.conch.ssh.transport.SSHCiphers.
    """

    outCipType = b"test"
    encBlockSize = 6
    inCipType = b"test"
    decBlockSize = 6
    inMACType = b"test"
    outMACType = b"test"
    verifyDigestSize = 1
    usedEncrypt = False
    usedDecrypt = False
    outMAC = (None, b"", b"", 1)
    inMAC = (None, b"", b"", 1)
    keys = ()

    def encrypt(self, x):
        """
        Called to encrypt the packet.  Simply record that encryption was used
        and return the data unchanged.
        """
        self.usedEncrypt = True
        if (len(x) % self.encBlockSize) != 0:
            raise RuntimeError(
                "length %i modulo blocksize %i is not 0: %i"
                % (len(x), self.encBlockSize, len(x) % self.encBlockSize)
            )
        return x

    def decrypt(self, x):
        """
        Called to decrypt the packet.  Simply record that decryption was used
        and return the data unchanged.
        """
        self.usedDecrypt = True
        if (len(x) % self.encBlockSize) != 0:
            raise RuntimeError(
                "length %i modulo blocksize %i is not 0: %i"
                % (len(x), self.decBlockSize, len(x) % self.decBlockSize)
            )
        return x

    def makeMAC(self, outgoingPacketSequence, payload):
        """
        Make a Message Authentication Code by sending the character value of
        the outgoing packet.
        """
        return bytes((outgoingPacketSequence,))

    def verify(self, incomingPacketSequence, packet, macData):
        """
        Verify the Message Authentication Code by checking that the packet
        sequence number is the same.
        """
        return bytes((incomingPacketSequence,)) == macData

    def setKeys(self, ivOut, keyOut, ivIn, keyIn, macIn, macOut):
        """
        Record the keys.
        """
        self.keys = (ivOut, keyOut, ivIn, keyIn, macIn, macOut)


class MockCompression:
    """
    A mocked-up compression, based on the zlib interface.  Instead of
    compressing, it reverses the data and adds a 0x66 byte to the end.
    """

    def compress(self, payload):
        return payload[::-1]  # reversed

    def decompress(self, payload):
        return payload[:-1][::-1]

    def flush(self, kind):
        return b"\x66"


class MockService(service.SSHService):
    """
    A mocked-up service, based on twisted.conch.ssh.service.SSHService.

    @ivar started: True if this service has been started.
    @ivar stopped: True if this service has been stopped.
    """

    name = b"MockService"
    started = False
    stopped = False
    protocolMessages = {0xFF: "MSG_TEST", 71: "MSG_fiction"}

    def logPrefix(self):
        return "MockService"

    def serviceStarted(self):
        """
        Record that the service was started.
        """
        self.started = True

    def serviceStopped(self):
        """
        Record that the service was stopped.
        """
        self.stopped = True

    def ssh_TEST(self, packet):
        """
        A message that this service responds to.
        """
        self.transport.sendPacket(0xFF, packet)


class MockFactory(factory.SSHFactory):
    """
    A mocked-up factory based on twisted.conch.ssh.factory.SSHFactory.
    """

    services = {b"ssh-userauth": MockService}

    def getPublicKeys(self):
        """
        Return the public keys that authenticate this server.
        """
        return {
            b"ssh-rsa": keys.Key.fromString(keydata.publicRSA_openssh),
            b"ssh-dsa": keys.Key.fromString(keydata.publicDSA_openssh),
        }

    def getPrivateKeys(self):
        """
        Return the private keys that authenticate this server.
        """
        return {
            b"ssh-rsa": keys.Key.fromString(keydata.privateRSA_openssh),
            b"ssh-dsa": keys.Key.fromString(keydata.privateDSA_openssh),
        }

    def getPrimes(self):
        """
        Diffie-Hellman primes that can be used for key exchange algorithms
        that use group exchange to establish a prime / generator group.

        @return: The primes and generators.
        @rtype: L{dict} mapping the key size to a C{list} of
            C{(generator, prime)} tuple.
        """
        # In these tests, we hardwire the prime values to those
        # defined by the diffie-hellman-group14-sha1 key exchange
        # algorithm, to avoid requiring a moduli file when running
        # tests.
        # See OpenSSHFactory.getPrimes.
        group14 = _kex.getDHGeneratorAndPrime(b"diffie-hellman-group14-sha1")
        return {2048: (group14,), 4096: ((5, 7),)}


class MockOldFactoryPublicKeys(MockFactory):
    """
    The old SSHFactory returned mappings from key names to strings from
    getPublicKeys().  We return those here for testing.
    """

    def getPublicKeys(self):
        """
        We used to map key types to public key blobs as strings.
        """
        keys = MockFactory.getPublicKeys(self)
        for name, key in keys.items()[:]:
            keys[name] = key.blob()
        return keys


class MockOldFactoryPrivateKeys(MockFactory):
    """
    The old SSHFactory returned mappings from key names to cryptography key
    objects from getPrivateKeys().  We return those here for testing.
    """

    def getPrivateKeys(self):
        """
        We used to map key types to cryptography key objects.
        """
        keys = MockFactory.getPrivateKeys(self)
        for name, key in keys.items()[:]:
            keys[name] = key.keyObject
        return keys


def generatePredictableKey(transport):
    p = transport.p
    g = transport.g
    bits = p.bit_length()
    x = sum(0x9 << x for x in range(0, bits - 3, 4))
    # The cryptography module doesn't let us create a secret key directly from
    # an "x" value; we need to compute the public value ourselves.
    y = pow(g, x, p)
    try:
        transport.dhSecretKey = dh.DHPrivateNumbers(
            x, dh.DHPublicNumbers(y, dh.DHParameterNumbers(p, g))
        ).private_key(default_backend())
    except ValueError:
        print(f"\np={p}\ng={g}\nx={x}\n")
        raise
    transport.dhSecretKeyPublicMP = common.MP(
        transport.dhSecretKey.public_key().public_numbers().y
    )


class TransportTestCase(TestCase):
    """
    Base class for transport test cases.
    """

    klass: Optional[Type[transport.SSHTransportBase]] = None

    if dependencySkip:
        skip = dependencySkip

    def setUp(self):
        self.transport = proto_helpers.StringTransport()
        self.proto = self.klass()
        self.packets = []

        def secureRandom(len):
            """
            Return a consistent entropy value
            """
            return b"\x99" * len

        self.patch(randbytes, "secureRandom", secureRandom)
        self.proto._startEphemeralDH = types.MethodType(
            generatePredictableKey, self.proto
        )

        def stubSendPacket(messageType, payload):
            self.packets.append((messageType, payload))

        self.proto.makeConnection(self.transport)
        # we just let the kex packet go into the transport
        self.proto.sendPacket = stubSendPacket

    def finishKeyExchange(self, proto):
        """
        Deliver enough additional messages to C{proto} so that the key exchange
        which is started in L{SSHTransportBase.connectionMade} completes and
        non-key exchange messages can be sent and received.
        """
        proto.dataReceived(b"SSH-2.0-BogoClient-1.2i\r\n")
        proto.dispatchMessage(transport.MSG_KEXINIT, self._A_KEXINIT_MESSAGE)
        proto._keySetup(b"foo", b"bar")
        # SSHTransportBase can't handle MSG_NEWKEYS, or it would be the right
        # thing to deliver next.  _newKeys won't work either, because
        # sendKexInit (probably) hasn't been called.  sendKexInit is
        # responsible for setting up certain state _newKeys relies on.  So,
        # just change the key exchange state to what it would be when key
        # exchange is finished.
        proto._keyExchangeState = proto._KEY_EXCHANGE_NONE

    def simulateKeyExchange(self, sharedSecret, exchangeHash):
        """
        Finish a key exchange by calling C{_keySetup} with the given arguments.
        Also do extra whitebox stuff to satisfy that method's assumption that
        some kind of key exchange has actually taken place.
        """
        self.proto._keyExchangeState = self.proto._KEY_EXCHANGE_REQUESTED
        self.proto._blockedByKeyExchange = []
        self.proto._keySetup(sharedSecret, exchangeHash)


class DHGroupExchangeSHA1Mixin:
    """
    Mixin for diffie-hellman-group-exchange-sha1 tests.
    """

    kexAlgorithm = b"diffie-hellman-group-exchange-sha1"
    hashProcessor = sha1


class DHGroupExchangeSHA256Mixin:
    """
    Mixin for diffie-hellman-group-exchange-sha256 tests.
    """

    kexAlgorithm = b"diffie-hellman-group-exchange-sha256"
    hashProcessor = sha256


class ECDHMixin:
    """
    Mixin for elliptic curve diffie-hellman tests.
    """

    kexAlgorithm = b"ecdh-sha2-nistp256"
    hashProcessor = sha256


class Curve25519SHA256Mixin:
    """
    Mixin for curve25519-sha256 tests.
    """

    kexAlgorithm = b"curve25519-sha256"
    hashProcessor = sha256


class BaseSSHTransportBaseCase:
    """
    Base case for TransportBase tests.
    """

    klass: Optional[Type[transport.SSHTransportBase]] = MockTransportBase


class BaseSSHTransportTests(BaseSSHTransportBaseCase, TransportTestCase):
    """
    Test TransportBase. It implements the non-server/client specific
    parts of the SSH transport protocol.
    """

    if dependencySkip:
        skip = dependencySkip

    _A_KEXINIT_MESSAGE = (
        b"\xAA" * 16
        + common.NS(b"diffie-hellman-group14-sha1")
        + common.NS(b"ssh-rsa")
        + common.NS(b"aes256-ctr")
        + common.NS(b"aes256-ctr")
        + common.NS(b"hmac-sha1")
        + common.NS(b"hmac-sha1")
        + common.NS(b"none")
        + common.NS(b"none")
        + common.NS(b"")
        + common.NS(b"")
        + b"\x00"
        + b"\x00\x00\x00\x00"
    )

    def test_sendVersion(self):
        """
        Test that the first thing sent over the connection is the version
        string.  The 'softwareversion' part must consist of printable
        US-ASCII characters, with the exception of whitespace characters and
        the minus sign.

        RFC 4253, section 4.2.
        """
        # the other setup was done in the setup method
        version = self.transport.value().split(b"\r\n", 1)[0]
        self.assertEqual(version, b"SSH-2.0-Twisted_" + twisted_version.encode("ascii"))
        softwareVersion = version.decode("ascii")[len("SSH-2.0-") :]
        # This is an inefficient regex, but it's simple to build.
        softwareVersionRegex = (
            r"^("
            + "|".join(
                re.escape(c) for c in string.printable if c != "-" and not c.isspace()
            )
            + r")*$"
        )
        self.assertRegex(softwareVersion, softwareVersionRegex)

    def test_dataReceiveVersionNotSentMemoryDOS(self):
        """
        When the peer is not sending its SSH version but keeps sending data,
        the connection is disconnected after 4KB to prevent buffering too
        much and running our of memory.
        """
        sut = MockTransportBase()
        sut.makeConnection(self.transport)

        # Data can be received over multiple chunks.
        sut.dataReceived(b"SSH-2-Server-Identifier")
        sut.dataReceived(b"1234567890" * 406)
        sut.dataReceived(b"1235678")
        self.assertFalse(self.transport.disconnecting)

        # Here we are going over the limit.
        sut.dataReceived(b"1234567")
        # Once a lot of data is received without an SSH version string,
        # the transport is disconnected.
        self.assertTrue(self.transport.disconnecting)
        self.assertIn(b"Preventing a denial of service attack", self.transport.value())

    def test_sendPacketPlain(self):
        """
        Test that plain (unencrypted, uncompressed) packets are sent
        correctly.  The format is::
            uint32 length (including type and padding length)
            byte padding length
            byte type
            bytes[length-padding length-2] data
            bytes[padding length] padding
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        self.transport.clear()
        message = ord("A")
        payload = b"BCDEFG"
        proto.sendPacket(message, payload)
        value = self.transport.value()
        self.assertEqual(value, b"\x00\x00\x00\x0c\x04ABCDEFG\x99\x99\x99\x99")

    def test_sendPacketEncrypted(self):
        """
        Test that packets sent while encryption is enabled are sent
        correctly.  The whole packet should be encrypted.
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        proto.currentEncryptions = testCipher = MockCipher()
        message = ord("A")
        payload = b"BC"
        self.transport.clear()
        proto.sendPacket(message, payload)
        self.assertTrue(testCipher.usedEncrypt)
        value = self.transport.value()
        self.assertEqual(
            value,
            # Four byte length prefix
            b"\x00\x00\x00\x08"
            # One byte padding length
            b"\x04"
            # The actual application data
            b"ABC"
            # "Random" padding - see the secureRandom monkeypatch in setUp
            b"\x99\x99\x99\x99"
            # The MAC
            b"\x02",
        )

    def test_sendPacketCompressed(self):
        """
        Test that packets sent while compression is enabled are sent
        correctly.  The packet type and data should be encrypted.
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        proto.outgoingCompression = MockCompression()
        self.transport.clear()
        proto.sendPacket(ord("A"), b"B")
        value = self.transport.value()
        self.assertEqual(
            value, b"\x00\x00\x00\x0c\x08BA\x66\x99\x99\x99\x99\x99\x99\x99\x99"
        )

    def test_sendPacketBoth(self):
        """
        Test that packets sent while compression and encryption are
        enabled are sent correctly.  The packet type and data should be
        compressed and then the whole packet should be encrypted.
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        proto.currentEncryptions = testCipher = MockCipher()
        proto.outgoingCompression = MockCompression()
        message = ord("A")
        payload = b"BC"
        self.transport.clear()
        proto.sendPacket(message, payload)
        self.assertTrue(testCipher.usedEncrypt)
        value = self.transport.value()
        self.assertEqual(
            value,
            # Four byte length prefix
            b"\x00\x00\x00\x0e"
            # One byte padding length
            b"\x09"
            # Compressed application data
            b"CBA\x66"
            # "Random" padding - see the secureRandom monkeypatch in setUp
            b"\x99\x99\x99\x99\x99\x99\x99\x99\x99"
            # The MAC
            b"\x02",
        )

    def test_getPacketPlain(self):
        """
        Test that packets are retrieved correctly out of the buffer when
        no encryption is enabled.
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        self.transport.clear()
        proto.sendPacket(ord("A"), b"BC")
        proto.buf = self.transport.value() + b"extra"
        self.assertEqual(proto.getPacket(), b"ABC")
        self.assertEqual(proto.buf, b"extra")

    def test_getPacketEncrypted(self):
        """
        Test that encrypted packets are retrieved correctly.
        See test_sendPacketEncrypted.
        """
        proto = MockTransportBase()
        proto.sendKexInit = lambda: None  # don't send packets
        proto.makeConnection(self.transport)
        self.transport.clear()
        proto.currentEncryptions = testCipher = MockCipher()
        proto.sendPacket(ord("A"), b"BCD")
        value = self.transport.value()
        proto.buf = value[: MockCipher.decBlockSize]
        self.assertIsNone(proto.getPacket())
        self.assertTrue(testCipher.usedDecrypt)
        self.assertEqual(proto.first, b"\x00\x00\x00\x0e\x09A")
        proto.buf += value[MockCipher.decBlockSize :]
        self.assertEqual(proto.getPacket(), b"ABCD")
        self.assertEqual(proto.buf, b"")

    def test_getPacketCompressed(self):
        """
        Test that compressed packets are retrieved correctly.  See
        test_sendPacketCompressed.
        """
        proto = MockTransportBase()
        proto.makeConnection(self.transport)
        self.finishKeyExchange(proto)
        self.transport.clear()
        proto.outgoingCompression = MockCompression()
        proto.incomingCompression = proto.outgoingCompression
        proto.sendPacket(ord("A"), b"BCD")
        proto.buf = self.transport.value()
        self.assertEqual(proto.getPacket(), b"ABCD")

    def test_getPacketBoth(self):
        """
        Test that compressed and encrypted packets are retrieved correctly.
        See test_sendPacketBoth.
        """
        proto = MockTransportBase()
        proto.sendKexInit = lambda: None
        proto.makeConnection(self.transport)
        self.transport.clear()
        proto.currentEncryptions = MockCipher()
        proto.outgoingCompression = MockCompression()
        proto.incomingCompression = proto.outgoingCompression
        proto.sendPacket(ord("A"), b"BCDEFG")
        proto.buf = self.transport.value()
        self.assertEqual(proto.getPacket(), b"ABCDEFG")

    def test_ciphersAreValid(self):
        """
        Test that all the supportedCiphers are valid.
        """
        ciphers = transport.SSHCiphers(b"A", b"B", b"C", b"D")
        iv = key = b"\x00" * 16
        for cipName in self.proto.supportedCiphers:
            self.assertTrue(ciphers._getCipher(cipName, iv, key))

    def test_sendKexInit(self):
        """
        Test that the KEXINIT (key exchange initiation) message is sent
        correctly.  Payload::
            bytes[16] cookie
            string key exchange algorithms
            string public key algorithms
            string outgoing ciphers
            string incoming ciphers
            string outgoing MACs
            string incoming MACs
            string outgoing compressions
            string incoming compressions
            bool first packet follows
            uint32 0
        """
        value = self.transport.value().split(b"\r\n", 1)[1]
        self.proto.buf = value
        packet = self.proto.getPacket()
        self.assertEqual(packet[0:1], bytes((transport.MSG_KEXINIT,)))
        self.assertEqual(packet[1:17], b"\x99" * 16)
        (
            keyExchanges,
            pubkeys,
            ciphers1,
            ciphers2,
            macs1,
            macs2,
            compressions1,
            compressions2,
            languages1,
            languages2,
            buf,
        ) = common.getNS(packet[17:], 10)

        self.assertEqual(
            keyExchanges, b",".join(self.proto.supportedKeyExchanges + [b"ext-info-s"])
        )
        self.assertEqual(pubkeys, b",".join(self.proto.supportedPublicKeys))
        self.assertEqual(ciphers1, b",".join(self.proto.supportedCiphers))
        self.assertEqual(ciphers2, b",".join(self.proto.supportedCiphers))
        self.assertEqual(macs1, b",".join(self.proto.supportedMACs))
        self.assertEqual(macs2, b",".join(self.proto.supportedMACs))
        self.assertEqual(compressions1, b",".join(self.proto.supportedCompressions))
        self.assertEqual(compressions2, b",".join(self.proto.supportedCompressions))
        self.assertEqual(languages1, b",".join(self.proto.supportedLanguages))
        self.assertEqual(languages2, b",".join(self.proto.supportedLanguages))
        self.assertEqual(buf, b"\x00" * 5)

    def test_receiveKEXINITReply(self):
        """
        Immediately after connecting, the transport expects a KEXINIT message
        and does not reply to it.
        """
        self.transport.clear()
        self.proto.dispatchMessage(transport.MSG_KEXINIT, self._A_KEXINIT_MESSAGE)
        self.assertEqual(self.packets, [])

    def test_sendKEXINITReply(self):
        """
        When a KEXINIT message is received which is not a reply to an earlier
        KEXINIT message which was sent, a KEXINIT reply is sent.
        """
        self.finishKeyExchange(self.proto)
        del self.packets[:]

        self.proto.dispatchMessage(transport.MSG_KEXINIT, self._A_KEXINIT_MESSAGE)
        self.assertEqual(len(self.packets), 1)
        self.assertEqual(self.packets[0][0], transport.MSG_KEXINIT)

    def test_sendKexInitTwiceFails(self):
        """
        A new key exchange cannot be started while a key exchange is already in
        progress.  If an attempt is made to send a I{KEXINIT} message using
        L{SSHTransportBase.sendKexInit} while a key exchange is in progress
        causes that method to raise a L{RuntimeError}.
        """
        self.assertRaises(RuntimeError, self.proto.sendKexInit)

    def test_sendKexInitBlocksOthers(self):
        """
        After L{SSHTransportBase.sendKexInit} has been called, messages types
        other than the following are queued and not sent until after I{NEWKEYS}
        is sent by L{SSHTransportBase._keySetup}.

        RFC 4253, section 7.1.
        """
        # sendKexInit is called by connectionMade, which is called in setUp.
        # So we're in the state already.
        disallowedMessageTypes = [
            transport.MSG_SERVICE_REQUEST,
            transport.MSG_KEXINIT,
        ]

        # Drop all the bytes sent by setUp, they're not relevant to this test.
        self.transport.clear()

        # Get rid of the sendPacket monkey patch, we are testing the behavior
        # of sendPacket.
        del self.proto.sendPacket

        for messageType in disallowedMessageTypes:
            self.proto.sendPacket(messageType, b"foo")
            self.assertEqual(self.transport.value(), b"")

        self.finishKeyExchange(self.proto)
        # Make the bytes written to the transport cleartext so it's easier to
        # make an assertion about them.
        self.proto.nextEncryptions = MockCipher()

        # Pseudo-deliver the peer's NEWKEYS message, which should flush the
        # messages which were queued above.
        self.proto._newKeys()
        self.assertEqual(self.transport.value().count(b"foo"), 2)

    def test_sendExtInfo(self):
        """
        Test that EXT_INFO messages are sent correctly.  See RFC 8308,
        section 2.3.
        """
        self.proto._peerSupportsExtensions = True
        self.proto.sendExtInfo(
            [
                (b"server-sig-algs", b"ssh-rsa,rsa-sha2-256"),
                (b"elevation", b"d"),
            ]
        )
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_EXT_INFO,
                    b"\x00\x00\x00\x02"
                    + common.NS(b"server-sig-algs")
                    + common.NS(b"ssh-rsa,rsa-sha2-256")
                    + common.NS(b"elevation")
                    + common.NS(b"d"),
                )
            ],
        )

    def test_sendExtInfoUnsupported(self):
        """
        If the peer has not advertised support for extension negotiation, no
        EXT_INFO message is sent, since RFC 8308 only guarantees that the
        peer will be prepared to accept it if it has advertised support.
        """
        self.proto.sendExtInfo([(b"server-sig-algs", b"ssh-rsa,rsa-sha2-256")])
        self.assertEqual(self.packets, [])

    def test_EXT_INFO(self):
        """
        When an EXT_INFO message is received, the transport stores a mapping
        of the peer's advertised extensions.  See RFC 8308, section 2.3.
        """
        self.proto.dispatchMessage(
            transport.MSG_EXT_INFO,
            b"\x00\x00\x00\x02"
            + common.NS(b"server-sig-algs")
            + common.NS(b"ssh-rsa,rsa-sha2-256,rsa-sha2-512")
            + common.NS(b"no-flow-control")
            + common.NS(b"s"),
        )
        self.assertEqual(
            self.proto.peerExtensions,
            {
                b"server-sig-algs": b"ssh-rsa,rsa-sha2-256,rsa-sha2-512",
                b"no-flow-control": b"s",
            },
        )

    def test_sendDebug(self):
        """
        Test that debug messages are sent correctly.  Payload::
            bool always display
            string debug message
            string language
        """
        self.proto.sendDebug(b"test", True, b"en")
        self.assertEqual(
            self.packets,
            [(transport.MSG_DEBUG, b"\x01\x00\x00\x00\x04test\x00\x00\x00\x02en")],
        )

    def test_receiveDebug(self):
        """
        Test that debug messages are received correctly.  See test_sendDebug.
        """
        self.proto.dispatchMessage(
            transport.MSG_DEBUG, b"\x01\x00\x00\x00\x04test\x00\x00\x00\x02en"
        )
        self.proto.dispatchMessage(
            transport.MSG_DEBUG, b"\x00\x00\x00\x00\x06silent\x00\x00\x00\x02en"
        )
        self.assertEqual(
            self.proto.debugs, [(True, b"test", b"en"), (False, b"silent", b"en")]
        )

    def test_sendIgnore(self):
        """
        Test that ignored messages are sent correctly.  Payload::
            string ignored data
        """
        self.proto.sendIgnore(b"test")
        self.assertEqual(
            self.packets, [(transport.MSG_IGNORE, b"\x00\x00\x00\x04test")]
        )

    def test_receiveIgnore(self):
        """
        Test that ignored messages are received correctly.  See
        test_sendIgnore.
        """
        self.proto.dispatchMessage(transport.MSG_IGNORE, b"test")
        self.assertEqual(self.proto.ignoreds, [b"test"])

    def test_sendUnimplemented(self):
        """
        Test that unimplemented messages are sent correctly.  Payload::
            uint32 sequence number
        """
        self.proto.sendUnimplemented()
        self.assertEqual(
            self.packets, [(transport.MSG_UNIMPLEMENTED, b"\x00\x00\x00\x00")]
        )

    def test_receiveUnimplemented(self):
        """
        Test that unimplemented messages are received correctly.  See
        test_sendUnimplemented.
        """
        self.proto.dispatchMessage(transport.MSG_UNIMPLEMENTED, b"\x00\x00\x00\xff")
        self.assertEqual(self.proto.unimplementeds, [255])

    def test_sendDisconnect(self):
        """
        Test that disconnection messages are sent correctly.  Payload::
            uint32 reason code
            string reason description
            string language
        """
        disconnected = [False]

        def stubLoseConnection():
            disconnected[0] = True

        self.transport.loseConnection = stubLoseConnection
        self.proto.sendDisconnect(0xFF, b"test")
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_DISCONNECT,
                    b"\x00\x00\x00\xff\x00\x00\x00\x04test\x00\x00\x00\x00",
                )
            ],
        )
        self.assertTrue(disconnected[0])

    def test_receiveDisconnect(self):
        """
        Test that disconnection messages are received correctly.  See
        test_sendDisconnect.
        """
        disconnected = [False]

        def stubLoseConnection():
            disconnected[0] = True

        self.transport.loseConnection = stubLoseConnection
        self.proto.dispatchMessage(
            transport.MSG_DISCONNECT, b"\x00\x00\x00\xff\x00\x00\x00\x04test"
        )
        self.assertEqual(self.proto.errors, [(255, b"test")])
        self.assertTrue(disconnected[0])

    def test_dataReceived(self):
        """
        Test that dataReceived parses packets and dispatches them to
        ssh_* methods.
        """
        kexInit = [False]

        def stubKEXINIT(packet):
            kexInit[0] = True

        self.proto.ssh_KEXINIT = stubKEXINIT
        self.proto.dataReceived(self.transport.value())
        self.assertTrue(self.proto.gotVersion)
        self.assertEqual(self.proto.ourVersionString, self.proto.otherVersionString)
        self.assertTrue(kexInit[0])

    def test_service(self):
        """
        Test that the transport can set the running service and dispatches
        packets to the service's packetReceived method.
        """
        service = MockService()
        self.proto.setService(service)
        self.assertEqual(self.proto.service, service)
        self.assertTrue(service.started)
        self.proto.dispatchMessage(0xFF, b"test")
        self.assertEqual(self.packets, [(0xFF, b"test")])

        service2 = MockService()
        self.proto.setService(service2)
        self.assertTrue(service2.started)
        self.assertTrue(service.stopped)

        self.proto.connectionLost(None)
        self.assertTrue(service2.stopped)

    def test_avatar(self):
        """
        Test that the transport notifies the avatar of disconnections.
        """
        disconnected = [False]

        def logout():
            disconnected[0] = True

        self.proto.logoutFunction = logout
        self.proto.avatar = True

        self.proto.connectionLost(None)
        self.assertTrue(disconnected[0])

    def test_isEncrypted(self):
        """
        Test that the transport accurately reflects its encrypted status.
        """
        self.assertFalse(self.proto.isEncrypted("in"))
        self.assertFalse(self.proto.isEncrypted("out"))
        self.assertFalse(self.proto.isEncrypted("both"))
        self.proto.currentEncryptions = MockCipher()
        self.assertTrue(self.proto.isEncrypted("in"))
        self.assertTrue(self.proto.isEncrypted("out"))
        self.assertTrue(self.proto.isEncrypted("both"))
        self.proto.currentEncryptions = transport.SSHCiphers(
            b"none", b"none", b"none", b"none"
        )
        self.assertFalse(self.proto.isEncrypted("in"))
        self.assertFalse(self.proto.isEncrypted("out"))
        self.assertFalse(self.proto.isEncrypted("both"))

        self.assertRaises(TypeError, self.proto.isEncrypted, "bad")

    def test_isVerified(self):
        """
        Test that the transport accurately reflects its verified status.
        """
        self.assertFalse(self.proto.isVerified("in"))
        self.assertFalse(self.proto.isVerified("out"))
        self.assertFalse(self.proto.isVerified("both"))
        self.proto.currentEncryptions = MockCipher()
        self.assertTrue(self.proto.isVerified("in"))
        self.assertTrue(self.proto.isVerified("out"))
        self.assertTrue(self.proto.isVerified("both"))
        self.proto.currentEncryptions = transport.SSHCiphers(
            b"none", b"none", b"none", b"none"
        )
        self.assertFalse(self.proto.isVerified("in"))
        self.assertFalse(self.proto.isVerified("out"))
        self.assertFalse(self.proto.isVerified("both"))

        self.assertRaises(TypeError, self.proto.isVerified, "bad")

    def test_loseConnection(self):
        """
        Test that loseConnection sends a disconnect message and closes the
        connection.
        """
        disconnected = [False]

        def stubLoseConnection():
            disconnected[0] = True

        self.transport.loseConnection = stubLoseConnection
        self.proto.loseConnection()
        self.assertEqual(self.packets[0][0], transport.MSG_DISCONNECT)
        self.assertEqual(
            self.packets[0][1][3:4], bytes((transport.DISCONNECT_CONNECTION_LOST,))
        )

    def test_badVersion(self):
        """
        Test that the transport disconnects when it receives a bad version.
        """

        def testBad(version):
            self.packets = []
            self.proto.gotVersion = False
            disconnected = [False]

            def stubLoseConnection():
                disconnected[0] = True

            self.transport.loseConnection = stubLoseConnection
            for c in iterbytes(version + b"\r\n"):
                self.proto.dataReceived(c)
            self.assertTrue(disconnected[0])
            self.assertEqual(self.packets[0][0], transport.MSG_DISCONNECT)
            self.assertEqual(
                self.packets[0][1][3:4],
                bytes((transport.DISCONNECT_PROTOCOL_VERSION_NOT_SUPPORTED,)),
            )

        testBad(b"SSH-1.5-OpenSSH")
        testBad(b"SSH-3.0-Twisted")
        testBad(b"GET / HTTP/1.1")

    def test_dataBeforeVersion(self):
        """
        Test that the transport ignores data sent before the version string.
        """
        proto = MockTransportBase()
        proto.makeConnection(proto_helpers.StringTransport())
        data = (
            b"""here's some stuff beforehand
here's some other stuff
"""
            + proto.ourVersionString
            + b"\r\n"
        )
        [proto.dataReceived(c) for c in iterbytes(data)]
        self.assertTrue(proto.gotVersion)
        self.assertEqual(proto.otherVersionString, proto.ourVersionString)

    def test_compatabilityVersion(self):
        """
        Test that the transport treats the compatibility version (1.99)
        as equivalent to version 2.0.
        """
        proto = MockTransportBase()
        proto.makeConnection(proto_helpers.StringTransport())
        proto.dataReceived(b"SSH-1.99-OpenSSH\n")
        self.assertTrue(proto.gotVersion)
        self.assertEqual(proto.otherVersionString, b"SSH-1.99-OpenSSH")

    def test_dataReceivedSSHVersionUnixNewline(self):
        """
        It can parse the SSH version string even when it ends only in
        Unix newlines (CR) and does not follows the RFC 4253 to use
        network newlines (CR LF).
        """
        sut = MockTransportBase()
        sut.makeConnection(proto_helpers.StringTransport())

        sut.dataReceived(b"SSH-2.0-PoorSSHD Some-comment here\n" b"more-data")

        self.assertTrue(sut.gotVersion)
        self.assertEqual(sut.otherVersionString, b"SSH-2.0-PoorSSHD Some-comment here")

    def test_dataReceivedSSHVersionTrailingSpaces(self):
        """
        The trailing spaces from SSH version comment are not removed.

        The SSH version string needs to be kept as received
        (without CR LF end of line) as they are used in the host
        authentication process.

        This can happen with a Bitvise SSH server which hides its version.
        """
        sut = MockTransportBase()
        sut.makeConnection(proto_helpers.StringTransport())

        sut.dataReceived(
            b"SSH-2.0-9.99 FlowSsh: Bitvise SSH Server (WinSSHD) \r\n" b"more-data"
        )

        self.assertTrue(sut.gotVersion)
        self.assertEqual(
            sut.otherVersionString,
            b"SSH-2.0-9.99 FlowSsh: Bitvise SSH Server (WinSSHD) ",
        )

    def test_supportedVersionsAreAllowed(self):
        """
        If an unusual SSH version is received and is included in
        C{supportedVersions}, an unsupported version error is not emitted.
        """
        proto = MockTransportBase()
        proto.supportedVersions = (b"9.99",)
        proto.makeConnection(proto_helpers.StringTransport())
        proto.dataReceived(b"SSH-9.99-OpenSSH\n")
        self.assertFalse(proto.gotUnsupportedVersion)

    def test_unsupportedVersionsCallUnsupportedVersionReceived(self):
        """
        If an unusual SSH version is received and is not included in
        C{supportedVersions}, an unsupported version error is emitted.
        """
        proto = MockTransportBase()
        proto.supportedVersions = (b"2.0",)
        proto.makeConnection(proto_helpers.StringTransport())
        proto.dataReceived(b"SSH-9.99-OpenSSH\n")
        self.assertEqual(b"9.99", proto.gotUnsupportedVersion)

    def test_badPackets(self):
        """
        Test that the transport disconnects with an error when it receives
        bad packets.
        """

        def testBad(packet, error=transport.DISCONNECT_PROTOCOL_ERROR):
            self.packets = []
            self.proto.buf = packet
            self.assertIsNone(self.proto.getPacket())
            self.assertEqual(len(self.packets), 1)
            self.assertEqual(self.packets[0][0], transport.MSG_DISCONNECT)
            self.assertEqual(self.packets[0][1][3:4], bytes((error,)))

        testBad(b"\xff" * 8)  # big packet
        testBad(b"\x00\x00\x00\x05\x00BCDE")  # length not modulo blocksize
        oldEncryptions = self.proto.currentEncryptions
        self.proto.currentEncryptions = MockCipher()
        testBad(
            b"\x00\x00\x00\x08\x06AB123456", transport.DISCONNECT_MAC_ERROR  # bad MAC
        )
        self.proto.currentEncryptions.decrypt = lambda x: x[:-1]
        testBad(b"\x00\x00\x00\x08\x06BCDEFGHIJK")  # bad decryption
        self.proto.currentEncryptions = oldEncryptions
        self.proto.incomingCompression = MockCompression()

        def stubDecompress(payload):
            raise Exception("bad compression")

        self.proto.incomingCompression.decompress = stubDecompress
        testBad(
            b"\x00\x00\x00\x04\x00BCDE",  # bad decompression
            transport.DISCONNECT_COMPRESSION_ERROR,
        )
        self.flushLoggedErrors()

    def test_unimplementedPackets(self):
        """
        Test that unimplemented packet types cause MSG_UNIMPLEMENTED packets
        to be sent.
        """
        seqnum = self.proto.incomingPacketSequence

        def checkUnimplemented(seqnum=seqnum):
            self.assertEqual(self.packets[0][0], transport.MSG_UNIMPLEMENTED)
            self.assertEqual(self.packets[0][1][3:4], bytes((seqnum,)))
            self.proto.packets = []
            seqnum += 1

        self.proto.dispatchMessage(40, b"")
        checkUnimplemented()
        transport.messages[41] = b"MSG_fiction"
        self.proto.dispatchMessage(41, b"")
        checkUnimplemented()
        self.proto.dispatchMessage(60, b"")
        checkUnimplemented()
        self.proto.setService(MockService())
        self.proto.dispatchMessage(70, b"")
        checkUnimplemented()
        self.proto.dispatchMessage(71, b"")
        checkUnimplemented()

    def test_multipleClasses(self):
        """
        Test that multiple instances have distinct states.
        """
        proto = self.proto
        proto.dataReceived(self.transport.value())
        proto.currentEncryptions = MockCipher()
        proto.outgoingCompression = MockCompression()
        proto.incomingCompression = MockCompression()
        proto.setService(MockService())
        proto2 = MockTransportBase()
        proto2.makeConnection(proto_helpers.StringTransport())
        proto2.sendIgnore(b"")
        self.assertNotEqual(proto.gotVersion, proto2.gotVersion)
        self.assertNotEqual(proto.transport, proto2.transport)
        self.assertNotEqual(proto.outgoingPacketSequence, proto2.outgoingPacketSequence)
        self.assertNotEqual(proto.incomingPacketSequence, proto2.incomingPacketSequence)
        self.assertNotEqual(proto.currentEncryptions, proto2.currentEncryptions)
        self.assertNotEqual(proto.service, proto2.service)


class BaseSSHTransportDHGroupExchangeBaseCase(BaseSSHTransportBaseCase):
    """
    Diffie-Hellman group exchange tests for TransportBase.
    """

    def test_getKey(self):
        """
        Test that _getKey generates the correct keys.
        """
        self.proto.kexAlg = self.kexAlgorithm
        self.proto.sessionID = b"EF"

        k1 = self.hashProcessor(b"AB" + b"CD" + b"K" + self.proto.sessionID).digest()
        k2 = self.hashProcessor(b"ABCD" + k1).digest()
        k3 = self.hashProcessor(b"ABCD" + k1 + k2).digest()
        k4 = self.hashProcessor(b"ABCD" + k1 + k2 + k3).digest()
        self.assertEqual(self.proto._getKey(b"K", b"AB", b"CD"), k1 + k2 + k3 + k4)


class BaseSSHTransportDHGroupExchangeSHA1Tests(
    BaseSSHTransportDHGroupExchangeBaseCase, DHGroupExchangeSHA1Mixin, TransportTestCase
):
    """
    diffie-hellman-group-exchange-sha1 tests for TransportBase.
    """


class BaseSSHTransportDHGroupExchangeSHA256Tests(
    BaseSSHTransportDHGroupExchangeBaseCase,
    DHGroupExchangeSHA256Mixin,
    TransportTestCase,
):
    """
    diffie-hellman-group-exchange-sha256 tests for TransportBase.
    """


class BaseSSHTransportEllipticCurveTests(
    BaseSSHTransportDHGroupExchangeBaseCase, ECDHMixin, TransportTestCase
):
    """
    ecdh-sha2-nistp256 tests for TransportBase
    """


@skipWithoutX25519
class BaseSSHTransportCurve25519SHA256Tests(
    BaseSSHTransportDHGroupExchangeBaseCase, Curve25519SHA256Mixin, TransportTestCase
):
    """
    curve25519-sha256 tests for TransportBase
    """


class ServerAndClientSSHTransportBaseCase:
    """
    Tests that need to be run on both the server and the client.
    """

    def checkDisconnected(self, kind=None):
        """
        Helper function to check if the transport disconnected.
        """
        if kind is None:
            kind = transport.DISCONNECT_PROTOCOL_ERROR
        self.assertEqual(self.packets[-1][0], transport.MSG_DISCONNECT)
        self.assertEqual(self.packets[-1][1][3:4], bytes((kind,)))

    def connectModifiedProtocol(self, protoModification, kind=None):
        """
        Helper function to connect a modified protocol to the test protocol
        and test for disconnection.
        """
        if kind is None:
            kind = transport.DISCONNECT_KEY_EXCHANGE_FAILED
        proto2 = self.klass()
        protoModification(proto2)
        proto2.makeConnection(proto_helpers.StringTransport())
        self.proto.dataReceived(proto2.transport.value())
        if kind:
            self.checkDisconnected(kind)
        return proto2

    def test_disconnectIfCantMatchKex(self):
        """
        Test that the transport disconnects if it can't match the key
        exchange
        """

        def blankKeyExchanges(proto2):
            proto2.supportedKeyExchanges = []

        self.connectModifiedProtocol(blankKeyExchanges)

    def test_disconnectIfCantMatchKeyAlg(self):
        """
        Like test_disconnectIfCantMatchKex, but for the key algorithm.
        """

        def blankPublicKeys(proto2):
            proto2.supportedPublicKeys = []

        self.connectModifiedProtocol(blankPublicKeys)

    def test_disconnectIfCantMatchCompression(self):
        """
        Like test_disconnectIfCantMatchKex, but for the compression.
        """

        def blankCompressions(proto2):
            proto2.supportedCompressions = []

        self.connectModifiedProtocol(blankCompressions)

    def test_disconnectIfCantMatchCipher(self):
        """
        Like test_disconnectIfCantMatchKex, but for the encryption.
        """

        def blankCiphers(proto2):
            proto2.supportedCiphers = []

        self.connectModifiedProtocol(blankCiphers)

    def test_disconnectIfCantMatchMAC(self):
        """
        Like test_disconnectIfCantMatchKex, but for the MAC.
        """

        def blankMACs(proto2):
            proto2.supportedMACs = []

        self.connectModifiedProtocol(blankMACs)

    def test_getPeer(self):
        """
        Test that the transport's L{getPeer} method returns an
        L{SSHTransportAddress} with the L{IAddress} of the peer.
        """
        self.assertEqual(
            self.proto.getPeer(),
            address.SSHTransportAddress(self.proto.transport.getPeer()),
        )

    def test_getHost(self):
        """
        Test that the transport's L{getHost} method returns an
        L{SSHTransportAddress} with the L{IAddress} of the host.
        """
        self.assertEqual(
            self.proto.getHost(),
            address.SSHTransportAddress(self.proto.transport.getHost()),
        )


class ServerSSHTransportBaseCase(ServerAndClientSSHTransportBaseCase):
    """
    Base case for SSHServerTransport tests.
    """

    klass: Optional[Type[transport.SSHTransportBase]] = transport.SSHServerTransport

    def setUp(self):
        TransportTestCase.setUp(self)
        self.proto.factory = MockFactory()
        self.proto.factory.startFactory()

    def tearDown(self):
        TransportTestCase.tearDown(self)
        self.proto.factory.stopFactory()
        del self.proto.factory


class ServerSSHTransportTests(ServerSSHTransportBaseCase, TransportTestCase):
    """
    Tests for SSHServerTransport.
    """

    def test__getHostKeys(self):
        """
        L{transport.SSHServerTransport._getHostKeys} returns host keys from
        the factory, looked up by public key signature algorithm.
        """
        self.proto.factory.publicKeys = {
            b"ssh-rsa": keys.Key.fromString(keydata.publicRSA_openssh),
            b"ssh-dss": keys.Key.fromString(keydata.publicDSA_openssh),
            b"ecdsa-sha2-nistp256": keys.Key.fromString(keydata.publicECDSA_openssh),
            b"ssh-ed25519": keys.Key.fromString(keydata.publicEd25519_openssh),
        }
        self.proto.factory.privateKeys = {
            b"ssh-rsa": keys.Key.fromString(keydata.privateRSA_openssh),
            b"ssh-dss": keys.Key.fromString(keydata.privateDSA_openssh),
            b"ecdsa-sha2-nistp256": keys.Key.fromString(keydata.privateECDSA_openssh),
            b"ssh-ed25519": keys.Key.fromString(keydata.privateEd25519_openssh_new),
        }
        self.assertEqual(
            self.proto._getHostKeys(b"ssh-rsa"),
            (
                self.proto.factory.publicKeys[b"ssh-rsa"],
                self.proto.factory.privateKeys[b"ssh-rsa"],
            ),
        )
        self.assertEqual(
            self.proto._getHostKeys(b"rsa-sha2-256"),
            (
                self.proto.factory.publicKeys[b"ssh-rsa"],
                self.proto.factory.privateKeys[b"ssh-rsa"],
            ),
        )
        self.assertEqual(
            self.proto._getHostKeys(b"rsa-sha2-512"),
            (
                self.proto.factory.publicKeys[b"ssh-rsa"],
                self.proto.factory.privateKeys[b"ssh-rsa"],
            ),
        )
        self.assertEqual(
            self.proto._getHostKeys(b"ssh-dss"),
            (
                self.proto.factory.publicKeys[b"ssh-dss"],
                self.proto.factory.privateKeys[b"ssh-dss"],
            ),
        )
        self.assertEqual(
            self.proto._getHostKeys(b"ecdsa-sha2-nistp256"),
            (
                self.proto.factory.publicKeys[b"ecdsa-sha2-nistp256"],
                self.proto.factory.privateKeys[b"ecdsa-sha2-nistp256"],
            ),
        )
        self.assertEqual(
            self.proto._getHostKeys(b"ssh-ed25519"),
            (
                self.proto.factory.publicKeys[b"ssh-ed25519"],
                self.proto.factory.privateKeys[b"ssh-ed25519"],
            ),
        )
        self.assertRaises(KeyError, self.proto._getHostKeys, b"ecdsa-sha2-nistp384")

    def test_KEXINITMultipleAlgorithms(self):
        """
        Receiving a KEXINIT packet listing multiple supported algorithms will
        set up the first common algorithm found in the client's preference
        list.
        """
        self.proto.dataReceived(
            b"SSH-2.0-Twisted\r\n\x00\x00\x01\xf4\x04\x14"
            b"\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99"
            b"\x99\x00\x00\x00bdiffie-hellman-group1-sha1,diffie-hellman-g"
            b"roup-exchange-sha1,diffie-hellman-group-exchange-sha256\x00"
            b"\x00\x00\x0fssh-dss,ssh-rsa\x00\x00\x00\x85aes128-ctr,aes128-"
            b"cbc,aes192-ctr,aes192-cbc,aes256-ctr,aes256-cbc,cast128-ctr,c"
            b"ast128-cbc,blowfish-ctr,blowfish-cbc,3des-ctr,3des-cbc\x00"
            b"\x00\x00\x85aes128-ctr,aes128-cbc,aes192-ctr,aes192-cbc,aes25"
            b"6-ctr,aes256-cbc,cast128-ctr,cast128-cbc,blowfish-ctr,blowfis"
            b"h-cbc,3des-ctr,3des-cbc\x00\x00\x00\x12hmac-md5,hmac-sha1\x00"
            b"\x00\x00\x12hmac-md5,hmac-sha1\x00\x00\x00\tnone,zlib\x00\x00"
            b"\x00\tnone,zlib\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x99\x99\x99\x99"
        )

        # Even if as server we prefer diffie-hellman-group-exchange-sha256 the
        # client preference is used, after skipping diffie-hellman-group1-sha1
        self.assertEqual(self.proto.kexAlg, b"diffie-hellman-group-exchange-sha1")
        self.assertEqual(self.proto.keyAlg, b"ssh-dss")
        self.assertEqual(self.proto.outgoingCompressionType, b"none")
        self.assertEqual(self.proto.incomingCompressionType, b"none")
        self.assertFalse(self.proto._peerSupportsExtensions)
        ne = self.proto.nextEncryptions
        self.assertEqual(ne.outCipType, b"aes128-ctr")
        self.assertEqual(ne.inCipType, b"aes128-ctr")
        self.assertEqual(ne.outMACType, b"hmac-md5")
        self.assertEqual(ne.inMACType, b"hmac-md5")

    def test_KEXINITExtensionNegotiation(self):
        """
        If the client sends "ext-info-c" in its key exchange algorithms,
        then the server notes that the client supports extension
        negotiation.  See RFC 8308, section 2.1.
        """
        kexInitPacket = (
            b"\x00" * 16
            + common.NS(b"diffie-hellman-group-exchange-sha256,ext-info-c")
            + common.NS(b"ssh-rsa")
            + common.NS(b"aes256-ctr")
            + common.NS(b"aes256-ctr")
            + common.NS(b"hmac-sha1")
            + common.NS(b"hmac-sha1")
            + common.NS(b"none")
            + common.NS(b"none")
            + common.NS(b"")
            + common.NS(b"")
            + b"\x00"
            + b"\x00\x00\x00\x00"
        )
        self.proto.ssh_KEXINIT(kexInitPacket)
        self.assertEqual(self.proto.kexAlg, b"diffie-hellman-group-exchange-sha256")
        self.assertTrue(self.proto._peerSupportsExtensions)

    def test_ignoreGuessPacketKex(self):
        """
        The client is allowed to send a guessed key exchange packet
        after it sends the KEXINIT packet.  However, if the key exchanges
        do not match, that guess packet must be ignored.  This tests that
        the packet is ignored in the case of the key exchange method not
        matching.
        """
        kexInitPacket = (
            b"\x00" * 16
            + (
                b"".join(
                    [
                        common.NS(x)
                        for x in [
                            b",".join(y)
                            for y in [
                                self.proto.supportedKeyExchanges[::-1],
                                self.proto.supportedPublicKeys,
                                self.proto.supportedCiphers,
                                self.proto.supportedCiphers,
                                self.proto.supportedMACs,
                                self.proto.supportedMACs,
                                self.proto.supportedCompressions,
                                self.proto.supportedCompressions,
                                self.proto.supportedLanguages,
                                self.proto.supportedLanguages,
                            ]
                        ]
                    ]
                )
            )
            + (b"\xff\x00\x00\x00\x00")
        )
        self.proto.ssh_KEXINIT(kexInitPacket)
        self.assertTrue(self.proto.ignoreNextPacket)
        self.proto.ssh_DEBUG(b"\x01\x00\x00\x00\x04test\x00\x00\x00\x00")
        self.assertTrue(self.proto.ignoreNextPacket)

        self.proto.ssh_KEX_DH_GEX_REQUEST_OLD(b"\x00\x00\x08\x00")
        self.assertFalse(self.proto.ignoreNextPacket)
        self.assertEqual(self.packets, [])
        self.proto.ignoreNextPacket = True

        self.proto.ssh_KEX_DH_GEX_REQUEST(b"\x00\x00\x08\x00" * 3)
        self.assertFalse(self.proto.ignoreNextPacket)
        self.assertEqual(self.packets, [])

    def test_ignoreGuessPacketKey(self):
        """
        Like test_ignoreGuessPacketKex, but for an incorrectly guessed
        public key format.
        """
        kexInitPacket = (
            b"\x00" * 16
            + (
                b"".join(
                    [
                        common.NS(x)
                        for x in [
                            b",".join(y)
                            for y in [
                                self.proto.supportedKeyExchanges,
                                self.proto.supportedPublicKeys[::-1],
                                self.proto.supportedCiphers,
                                self.proto.supportedCiphers,
                                self.proto.supportedMACs,
                                self.proto.supportedMACs,
                                self.proto.supportedCompressions,
                                self.proto.supportedCompressions,
                                self.proto.supportedLanguages,
                                self.proto.supportedLanguages,
                            ]
                        ]
                    ]
                )
            )
            + (b"\xff\x00\x00\x00\x00")
        )
        self.proto.ssh_KEXINIT(kexInitPacket)
        self.assertTrue(self.proto.ignoreNextPacket)
        self.proto.ssh_DEBUG(b"\x01\x00\x00\x00\x04test\x00\x00\x00\x00")
        self.assertTrue(self.proto.ignoreNextPacket)

        self.proto.ssh_KEX_DH_GEX_REQUEST_OLD(b"\x00\x00\x08\x00")
        self.assertFalse(self.proto.ignoreNextPacket)
        self.assertEqual(self.packets, [])
        self.proto.ignoreNextPacket = True

        self.proto.ssh_KEX_DH_GEX_REQUEST(b"\x00\x00\x08\x00" * 3)
        self.assertFalse(self.proto.ignoreNextPacket)
        self.assertEqual(self.packets, [])

    def assertKexDHInitResponse(self, kexAlgorithm, keyAlgorithm, bits):
        """
        Test that the KEXDH_INIT packet causes the server to send a
        KEXDH_REPLY with the server's public key and a signature.

        @param kexAlgorithm: The key exchange algorithm to use.
        @type kexAlgorithm: L{bytes}

        @param keyAlgorithm: The public key signature algorithm to use.
        @type keyAlgorithm: L{bytes}

        @param bits: The bit length of the DH modulus.
        @type bits: L{int}
        """
        self.proto.supportedKeyExchanges = [kexAlgorithm]
        self.proto.supportedPublicKeys = [keyAlgorithm]
        self.proto.dataReceived(self.transport.value())

        pubHostKey, privHostKey = self.proto._getHostKeys(keyAlgorithm)
        g, p = _kex.getDHGeneratorAndPrime(kexAlgorithm)
        e = pow(g, 5000, p)

        self.proto.ssh_KEX_DH_GEX_REQUEST_OLD(common.MP(e))
        y = common.getMP(common.NS(b"\x99" * (bits // 8)))[0]
        f = _MPpow(self.proto.g, y, self.proto.p)
        self.assertEqual(self.proto.dhSecretKeyPublicMP, f)
        sharedSecret = _MPpow(e, y, self.proto.p)

        h = sha1()
        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(pubHostKey.blob()))
        h.update(common.MP(e))
        h.update(f)
        h.update(sharedSecret)
        exchangeHash = h.digest()

        signature = privHostKey.sign(exchangeHash, signatureType=keyAlgorithm)

        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEXDH_REPLY,
                    common.NS(pubHostKey.blob()) + f + common.NS(signature),
                ),
                (transport.MSG_NEWKEYS, b""),
            ],
        )

    def test_checkBad_KEX_ECDH_INIT_CurveName(self):
        """
        Test that if the server receives a KEX_DH_GEX_REQUEST_OLD message
        and the key exchange algorithm is not set, we raise a ConchError.
        """
        self.proto.kexAlg = b"bad-curve"
        self.proto.keyAlg = b"ssh-rsa"
        self.assertRaises(
            UnsupportedAlgorithm,
            self.proto._ssh_KEX_ECDH_INIT,
            common.NS(b"unused-key"),
        )

    def test_checkBad_KEX_INIT_CurveName(self):
        """
        Test that if the server received a bad name for a curve
        we raise an UnsupportedAlgorithm error.
        """
        kexmsg = (
            b"\xAA" * 16
            + common.NS(b"ecdh-sha2-nistp256")
            + common.NS(b"ssh-rsa")
            + common.NS(b"aes256-ctr")
            + common.NS(b"aes256-ctr")
            + common.NS(b"hmac-sha1")
            + common.NS(b"hmac-sha1")
            + common.NS(b"none")
            + common.NS(b"none")
            + common.NS(b"")
            + common.NS(b"")
            + b"\x00"
            + b"\x00\x00\x00\x00"
        )

        self.proto.ssh_KEXINIT(kexmsg)
        self.assertRaises(AttributeError)
        self.assertRaises(UnsupportedAlgorithm)

    def test_KEXDH_INIT_GROUP14(self):
        """
        KEXDH_INIT messages are processed when the
        diffie-hellman-group14-sha1 key exchange algorithm and the ssh-rsa
        public key signature algorithm are requested.
        """
        self.assertKexDHInitResponse(b"diffie-hellman-group14-sha1", b"ssh-rsa", 2048)

    def test_KEXDH_INIT_GROUP14_rsa_sha2_256(self):
        """
        KEXDH_INIT messages are processed when the
        diffie-hellman-group14-sha1 key exchange algorithm and the
        rsa-sha2-256 public key signature algorithm are requested.
        """
        self.assertKexDHInitResponse(
            b"diffie-hellman-group14-sha1", b"rsa-sha2-256", 2048
        )

    def test_KEXDH_INIT_GROUP14_rsa_sha2_512(self):
        """
        KEXDH_INIT messages are processed when the
        diffie-hellman-group14-sha1 key exchange algorithm and the
        rsa-sha2-256 public key signature algorithm are requested.
        """
        self.assertKexDHInitResponse(
            b"diffie-hellman-group14-sha1", b"rsa-sha2-512", 2048
        )

    def test_keySetup(self):
        """
        Test that _keySetup sets up the next encryption keys.
        """
        self.proto.kexAlg = b"diffie-hellman-group14-sha1"
        self.proto.nextEncryptions = MockCipher()
        self.simulateKeyExchange(b"AB", b"CD")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.simulateKeyExchange(b"AB", b"EF")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.assertEqual(self.packets[-1], (transport.MSG_NEWKEYS, b""))
        newKeys = [self.proto._getKey(c, b"AB", b"EF") for c in iterbytes(b"ABCDEF")]
        self.assertEqual(
            self.proto.nextEncryptions.keys,
            (newKeys[1], newKeys[3], newKeys[0], newKeys[2], newKeys[5], newKeys[4]),
        )

    def test_keySetupWithExtInfo(self):
        """
        If the client advertised support for extension negotiation, then
        _keySetup sends SSH_MSG_EXT_INFO with the "server-sig-algs"
        extension as the next packet following the server's first
        SSH_MSG_NEWKEYS.  See RFC 8308, sections 2.4 and 3.1.
        """
        self.proto.supportedPublicKeys = [b"ssh-rsa", b"rsa-sha2-256", b"rsa-sha2-512"]
        self.proto.kexAlg = b"diffie-hellman-group14-sha1"
        self.proto.nextEncryptions = MockCipher()
        self.proto._peerSupportsExtensions = True
        self.simulateKeyExchange(b"AB", b"CD")
        self.assertEqual(self.packets[-2], (transport.MSG_NEWKEYS, b""))
        self.assertEqual(
            self.packets[-1],
            (
                transport.MSG_EXT_INFO,
                b"\x00\x00\x00\x01"
                + common.NS(b"server-sig-algs")
                + common.NS(b"ssh-rsa,rsa-sha2-256,rsa-sha2-512"),
            ),
        )
        self.simulateKeyExchange(b"AB", b"EF")
        self.assertEqual(self.packets[-1], (transport.MSG_NEWKEYS, b""))

    def test_ECDH_keySetup(self):
        """
        Test that _keySetup sets up the next encryption keys.
        """
        self.proto.kexAlg = b"ecdh-sha2-nistp256"
        self.proto.nextEncryptions = MockCipher()
        self.simulateKeyExchange(b"AB", b"CD")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.simulateKeyExchange(b"AB", b"EF")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.assertEqual(self.packets[-1], (transport.MSG_NEWKEYS, b""))
        newKeys = [self.proto._getKey(c, b"AB", b"EF") for c in iterbytes(b"ABCDEF")]
        self.assertEqual(
            self.proto.nextEncryptions.keys,
            (newKeys[1], newKeys[3], newKeys[0], newKeys[2], newKeys[5], newKeys[4]),
        )

    def test_NEWKEYS(self):
        """
        Test that NEWKEYS transitions the keys in nextEncryptions to
        currentEncryptions.
        """
        self.test_KEXINITMultipleAlgorithms()

        self.proto.nextEncryptions = transport.SSHCiphers(
            b"none", b"none", b"none", b"none"
        )
        self.proto.ssh_NEWKEYS(b"")
        self.assertIs(self.proto.currentEncryptions, self.proto.nextEncryptions)
        self.assertIsNone(self.proto.outgoingCompression)
        self.assertIsNone(self.proto.incomingCompression)
        self.proto.outgoingCompressionType = b"zlib"
        self.simulateKeyExchange(b"AB", b"CD")
        self.proto.ssh_NEWKEYS(b"")
        self.assertIsNotNone(self.proto.outgoingCompression)
        self.proto.incomingCompressionType = b"zlib"
        self.simulateKeyExchange(b"AB", b"EF")
        self.proto.ssh_NEWKEYS(b"")
        self.assertIsNotNone(self.proto.incomingCompression)

    def test_SERVICE_REQUEST(self):
        """
        Test that the SERVICE_REQUEST message requests and starts a
        service.
        """
        self.proto.ssh_SERVICE_REQUEST(common.NS(b"ssh-userauth"))
        self.assertEqual(
            self.packets, [(transport.MSG_SERVICE_ACCEPT, common.NS(b"ssh-userauth"))]
        )
        self.assertEqual(self.proto.service.name, b"MockService")

    def test_disconnectNEWKEYSData(self):
        """
        Test that NEWKEYS disconnects if it receives data.
        """
        self.proto.ssh_NEWKEYS(b"bad packet")
        self.checkDisconnected()

    def test_disconnectSERVICE_REQUESTBadService(self):
        """
        Test that SERVICE_REQUESTS disconnects if an unknown service is
        requested.
        """
        self.proto.ssh_SERVICE_REQUEST(common.NS(b"no service"))
        self.checkDisconnected(transport.DISCONNECT_SERVICE_NOT_AVAILABLE)


class ServerSSHTransportDHGroupExchangeBaseCase(ServerSSHTransportBaseCase):
    """
    Diffie-Hellman group exchange tests for SSHServerTransport.
    """

    def test_KEX_DH_GEX_REQUEST_OLD(self):
        """
        Test that the KEX_DH_GEX_REQUEST_OLD message causes the server
        to reply with a KEX_DH_GEX_GROUP message with the correct
        Diffie-Hellman group.
        """
        self.proto.supportedKeyExchanges = [self.kexAlgorithm]
        self.proto.supportedPublicKeys = [b"ssh-rsa"]
        self.proto.dataReceived(self.transport.value())
        self.proto.ssh_KEX_DH_GEX_REQUEST_OLD(b"\x00\x00\x04\x00")
        dhGenerator, dhPrime = self.proto.factory.getPrimes().get(2048)[0]
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEX_DH_GEX_GROUP,
                    common.MP(dhPrime) + b"\x00\x00\x00\x01\x02",
                )
            ],
        )
        self.assertEqual(self.proto.g, 2)
        self.assertEqual(self.proto.p, dhPrime)

    def test_KEX_DH_GEX_REQUEST_OLD_badKexAlg(self):
        """
        Test that if the server receives a KEX_DH_GEX_REQUEST_OLD message
        and the key exchange algorithm is not set, we raise a ConchError.
        """
        self.proto.kexAlg = None
        self.assertRaises(ConchError, self.proto.ssh_KEX_DH_GEX_REQUEST_OLD, None)

    def test_KEX_DH_GEX_REQUEST(self, keyAlgorithm=b"ssh-rsa"):
        """
        Test that the KEX_DH_GEX_REQUEST message causes the server to reply
        with a KEX_DH_GEX_GROUP message with the correct Diffie-Hellman
        group.
        """
        self.proto.supportedKeyExchanges = [self.kexAlgorithm]
        self.proto.supportedPublicKeys = [keyAlgorithm]
        self.proto.dataReceived(self.transport.value())
        self.proto.ssh_KEX_DH_GEX_REQUEST(
            b"\x00\x00\x04\x00\x00\x00\x08\x00" + b"\x00\x00\x0c\x00"
        )
        dhGenerator, dhPrime = self.proto.factory.getPrimes().get(2048)[0]
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEX_DH_GEX_GROUP,
                    common.MP(dhPrime) + b"\x00\x00\x00\x01\x02",
                )
            ],
        )
        self.assertEqual(self.proto.g, 2)
        self.assertEqual(self.proto.p, dhPrime)

    def test_KEX_DH_GEX_INIT_after_REQUEST_OLD(self):
        """
        Test that the KEX_DH_GEX_INIT message after the client sends
        KEX_DH_GEX_REQUEST_OLD causes the server to send a KEX_DH_GEX_INIT
        message with a public key and signature.
        """
        self.test_KEX_DH_GEX_REQUEST_OLD()
        pubHostKey, privHostKey = self.proto._getHostKeys(b"ssh-rsa")
        e = pow(self.proto.g, 3, self.proto.p)
        y = common.getMP(b"\x00\x00\x01\x00" + b"\x99" * 512)[0]
        self.assertEqual(self.proto.dhSecretKey.private_numbers().x, y)
        f = _MPpow(self.proto.g, y, self.proto.p)
        self.assertEqual(self.proto.dhSecretKeyPublicMP, f)
        sharedSecret = _MPpow(e, y, self.proto.p)
        h = self.hashProcessor()
        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(pubHostKey.blob()))
        h.update(b"\x00\x00\x04\x00")
        h.update(common.MP(self.proto.p))
        h.update(common.MP(self.proto.g))
        h.update(common.MP(e))
        h.update(f)
        h.update(sharedSecret)
        exchangeHash = h.digest()
        self.proto.ssh_KEX_DH_GEX_INIT(common.MP(e))
        self.assertEqual(
            self.packets[1:],
            [
                (
                    transport.MSG_KEX_DH_GEX_REPLY,
                    common.NS(pubHostKey.blob())
                    + f
                    + common.NS(privHostKey.sign(exchangeHash)),
                ),
                (transport.MSG_NEWKEYS, b""),
            ],
        )

    def test_KEX_DH_GEX_INIT_after_REQUEST(self):
        """
        Test that the KEX_DH_GEX_INIT message after the client sends
        KEX_DH_GEX_REQUEST causes the server to send a KEX_DH_GEX_INIT message
        with a public key and signature.
        """
        self.test_KEX_DH_GEX_REQUEST()
        pubHostKey, privHostKey = self.proto._getHostKeys(b"ssh-rsa")
        e = pow(self.proto.g, 3, self.proto.p)
        y = common.getMP(b"\x00\x00\x01\x00" + b"\x99" * 256)[0]
        f = _MPpow(self.proto.g, y, self.proto.p)
        sharedSecret = _MPpow(e, y, self.proto.p)

        h = self.hashProcessor()

        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(pubHostKey.blob()))
        h.update(b"\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x0c\x00")
        h.update(common.MP(self.proto.p))
        h.update(common.MP(self.proto.g))
        h.update(common.MP(e))
        h.update(f)
        h.update(sharedSecret)
        exchangeHash = h.digest()
        self.proto.ssh_KEX_DH_GEX_INIT(common.MP(e))
        self.assertEqual(
            self.packets[1],
            (
                transport.MSG_KEX_DH_GEX_REPLY,
                common.NS(pubHostKey.blob())
                + f
                + common.NS(privHostKey.sign(exchangeHash)),
            ),
        )

    def test_KEX_DH_GEX_INIT_after_REQUEST_rsa_sha2_512(self):
        """
        Test that the KEX_DH_GEX_INIT message after the client sends
        KEX_DH_GEX_REQUEST using a public key signature algorithm other than
        the default for the public key format causes the server to send a
        KEX_DH_GEX_INIT message with a public key and signature.
        """
        self.test_KEX_DH_GEX_REQUEST(keyAlgorithm=b"rsa-sha2-512")
        pubHostKey, privHostKey = self.proto._getHostKeys(b"rsa-sha2-512")
        e = pow(self.proto.g, 3, self.proto.p)
        y = common.getMP(b"\x00\x00\x01\x00" + b"\x99" * 256)[0]
        f = _MPpow(self.proto.g, y, self.proto.p)
        sharedSecret = _MPpow(e, y, self.proto.p)

        h = self.hashProcessor()

        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(pubHostKey.blob()))
        h.update(b"\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x0c\x00")
        h.update(common.MP(self.proto.p))
        h.update(common.MP(self.proto.g))
        h.update(common.MP(e))
        h.update(f)
        h.update(sharedSecret)
        exchangeHash = h.digest()
        self.proto.ssh_KEX_DH_GEX_INIT(common.MP(e))
        self.assertEqual(
            self.packets[1],
            (
                transport.MSG_KEX_DH_GEX_REPLY,
                common.NS(pubHostKey.blob())
                + f
                + common.NS(
                    privHostKey.sign(exchangeHash, signatureType=b"rsa-sha2-512")
                ),
            ),
        )


class ServerSSHTransportDHGroupExchangeSHA1Tests(
    ServerSSHTransportDHGroupExchangeBaseCase,
    DHGroupExchangeSHA1Mixin,
    TransportTestCase,
):
    """
    diffie-hellman-group-exchange-sha1 tests for SSHServerTransport.
    """


class ServerSSHTransportDHGroupExchangeSHA256Tests(
    ServerSSHTransportDHGroupExchangeBaseCase,
    DHGroupExchangeSHA256Mixin,
    TransportTestCase,
):
    """
    diffie-hellman-group-exchange-sha256 tests for SSHServerTransport.
    """


class ServerSSHTransportECDHBaseCase(ServerSSHTransportBaseCase):
    """
    Elliptic Curve Diffie-Hellman tests for SSHServerTransport.
    """

    def test_KEX_ECDH_INIT(self):
        """
        Test that the KEXDH_INIT message causes the server to send a
        KEXDH_REPLY with the server's public key and a signature.
        """
        self.proto.supportedKeyExchanges = [self.kexAlgorithm]
        self.proto.supportedPublicKeys = [b"ssh-rsa"]
        self.proto.dataReceived(self.transport.value())

        pubHostKey, privHostKey = self.proto._getHostKeys(b"ssh-rsa")
        ecPriv = self.proto._generateECPrivateKey()
        ecPub = ecPriv.public_key()
        encPub = self.proto._encodeECPublicKey(ecPub)

        self.proto.ssh_KEX_DH_GEX_REQUEST_OLD(common.NS(encPub))

        sharedSecret = self.proto._generateECSharedSecret(
            ecPriv, self.proto._encodeECPublicKey(self.proto.ecPub)
        )

        h = self.hashProcessor()
        h.update(common.NS(self.proto.otherVersionString))
        h.update(common.NS(self.proto.ourVersionString))
        h.update(common.NS(self.proto.otherKexInitPayload))
        h.update(common.NS(self.proto.ourKexInitPayload))
        h.update(common.NS(pubHostKey.blob()))
        h.update(common.NS(encPub))
        h.update(common.NS(self.proto._encodeECPublicKey(self.proto.ecPub)))
        h.update(sharedSecret)
        exchangeHash = h.digest()

        signature = privHostKey.sign(exchangeHash)

        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEXDH_REPLY,
                    common.NS(pubHostKey.blob())
                    + common.NS(self.proto._encodeECPublicKey(self.proto.ecPub))
                    + common.NS(signature),
                ),
                (transport.MSG_NEWKEYS, b""),
            ],
        )


class ServerSSHTransportECDHTests(
    ServerSSHTransportECDHBaseCase, ECDHMixin, TransportTestCase
):
    """
    ecdh-sha2-nistp256 tests for SSHServerTransport.
    """


@skipWithoutX25519
class ServerSSHTransportCurve25519SHA256Tests(
    ServerSSHTransportECDHBaseCase, Curve25519SHA256Mixin, TransportTestCase
):
    """
    curve25519-sha256 tests for SSHServerTransport.
    """


class ClientSSHTransportBaseCase(ServerAndClientSSHTransportBaseCase):
    """
    Base case for SSHClientTransport tests.
    """

    klass: Optional[Type[transport.SSHTransportBase]] = transport.SSHClientTransport

    def verifyHostKey(self, pubKey, fingerprint):
        """
        Mock version of SSHClientTransport.verifyHostKey.
        """
        self.calledVerifyHostKey = True
        self.assertEqual(pubKey, self.blob)
        self.assertEqual(
            fingerprint.replace(b":", b""), binascii.hexlify(md5(pubKey).digest())
        )
        return defer.succeed(True)

    def setUp(self):
        TransportTestCase.setUp(self)
        self.blob = keys.Key.fromString(keydata.publicRSA_openssh).blob()
        self.privObj = keys.Key.fromString(keydata.privateRSA_openssh)
        self.calledVerifyHostKey = False
        self.proto.verifyHostKey = self.verifyHostKey


class ClientSSHTransportTests(ClientSSHTransportBaseCase, TransportTestCase):
    """
    Tests for SSHClientTransport.
    """

    def test_KEXINITMultipleAlgorithms(self):
        """
        Receiving a KEXINIT packet listing multiple supported
        algorithms will set up the first common algorithm, ordered after our
        preference.
        """
        self.proto.dataReceived(
            b"SSH-2.0-Twisted\r\n\x00\x00\x01\xf4\x04\x14"
            b"\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99"
            b"\x99\x00\x00\x00bdiffie-hellman-group1-sha1,diffie-hellman-g"
            b"roup-exchange-sha1,diffie-hellman-group-exchange-sha256\x00"
            b"\x00\x00\x0fssh-dss,ssh-rsa\x00\x00\x00\x85aes128-ctr,aes128-"
            b"cbc,aes192-ctr,aes192-cbc,aes256-ctr,aes256-cbc,cast128-ctr,c"
            b"ast128-cbc,blowfish-ctr,blowfish-cbc,3des-ctr,3des-cbc\x00"
            b"\x00\x00\x85aes128-ctr,aes128-cbc,aes192-ctr,aes192-cbc,aes25"
            b"6-ctr,aes256-cbc,cast128-ctr,cast128-cbc,blowfish-ctr,blowfis"
            b"h-cbc,3des-ctr,3des-cbc\x00\x00\x00\x12hmac-md5,hmac-sha1\x00"
            b"\x00\x00\x12hmac-md5,hmac-sha1\x00\x00\x00\tzlib,none\x00\x00"
            b"\x00\tzlib,none\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x99\x99\x99\x99"
        )
        # Even if client prefer diffie-hellman-group1-sha1, we will go for
        # diffie-hellman-group-exchange-sha256 as this what we prefer and is
        # also supported by the server.
        self.assertEqual(self.proto.kexAlg, b"diffie-hellman-group-exchange-sha256")
        self.assertEqual(self.proto.keyAlg, b"ssh-rsa")
        self.assertEqual(self.proto.outgoingCompressionType, b"none")
        self.assertEqual(self.proto.incomingCompressionType, b"none")
        ne = self.proto.nextEncryptions
        self.assertEqual(ne.outCipType, b"aes256-ctr")
        self.assertEqual(ne.inCipType, b"aes256-ctr")
        self.assertEqual(ne.outMACType, b"hmac-sha1")
        self.assertEqual(ne.inMACType, b"hmac-sha1")

    def test_notImplementedClientMethods(self):
        """
        verifyHostKey() should return a Deferred which fails with a
        NotImplementedError exception.  connectionSecure() should raise
        NotImplementedError().
        """
        self.assertRaises(NotImplementedError, self.klass().connectionSecure)

        def _checkRaises(f):
            f.trap(NotImplementedError)

        d = self.klass().verifyHostKey(None, None)
        return d.addCallback(self.fail).addErrback(_checkRaises)

    def assertKexInitResponseForDH(self, kexAlgorithm, bits):
        """
        Test that a KEXINIT packet with a group1 or group14 key exchange
        results in a correct KEXDH_INIT response.

        @param kexAlgorithm: The key exchange algorithm to use
        @type kexAlgorithm: L{str}
        """
        self.proto.supportedKeyExchanges = [kexAlgorithm]

        # Imitate reception of server key exchange request contained
        # in data returned by self.transport.value()
        self.proto.dataReceived(self.transport.value())

        x = self.proto.dhSecretKey.private_numbers().x
        self.assertEqual(common.MP(x)[5:], b"\x99" * (bits // 8))

        # Data sent to server should be a transport.MSG_KEXDH_INIT
        # message containing our public key.
        self.assertEqual(
            self.packets, [(transport.MSG_KEXDH_INIT, self.proto.dhSecretKeyPublicMP)]
        )

    def test_KEXINIT_group14(self):
        """
        KEXINIT messages requesting diffie-hellman-group14-sha1 result in
        KEXDH_INIT responses.
        """
        self.assertKexInitResponseForDH(b"diffie-hellman-group14-sha1", 2048)

    def test_KEXINIT_badKexAlg(self):
        """
        Test that the client raises a ConchError if it receives a
        KEXINIT message but doesn't have a key exchange algorithm that we
        understand.
        """
        self.proto.supportedKeyExchanges = [b"diffie-hellman-group24-sha1"]
        data = self.transport.value().replace(b"group14", b"group24")
        self.assertRaises(ConchError, self.proto.dataReceived, data)

    def test_KEXINITExtensionNegotiation(self):
        """
        If the server sends "ext-info-s" in its key exchange algorithms,
        then the client notes that the server supports extension
        negotiation.  See RFC 8308, section 2.1.
        """
        kexInitPacket = (
            b"\x00" * 16
            + common.NS(b"diffie-hellman-group-exchange-sha256,ext-info-s")
            + common.NS(b"ssh-rsa")
            + common.NS(b"aes256-ctr")
            + common.NS(b"aes256-ctr")
            + common.NS(b"hmac-sha1")
            + common.NS(b"hmac-sha1")
            + common.NS(b"none")
            + common.NS(b"none")
            + common.NS(b"")
            + common.NS(b"")
            + b"\x00"
            + b"\x00\x00\x00\x00"
        )
        self.proto.ssh_KEXINIT(kexInitPacket)
        self.assertTrue(self.proto._peerSupportsExtensions)

    def begin_KEXDH_REPLY(self):
        """
        Utility for test_KEXDH_REPLY and
        test_disconnectKEXDH_REPLYBadSignature.

        Begins a Diffie-Hellman key exchange in the named group
        Group-14 and computes information needed to return either a
        correct or incorrect signature.

        """
        self.test_KEXINIT_group14()

        f = 2
        fMP = common.MP(f)
        x = self.proto.dhSecretKey.private_numbers().x
        p = self.proto.p
        sharedSecret = _MPpow(f, x, p)
        h = sha1()
        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(self.blob))
        h.update(self.proto.dhSecretKeyPublicMP)
        h.update(fMP)
        h.update(sharedSecret)
        exchangeHash = h.digest()

        signature = self.privObj.sign(exchangeHash)

        return (exchangeHash, signature, common.NS(self.blob) + fMP)

    def test_KEXDH_REPLY(self):
        """
        Test that the KEXDH_REPLY message verifies the server.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEXDH_REPLY()

        def _cbTestKEXDH_REPLY(value):
            self.assertIsNone(value)
            self.assertTrue(self.calledVerifyHostKey)
            self.assertEqual(self.proto.sessionID, exchangeHash)

        d = self.proto.ssh_KEX_DH_GEX_GROUP(packetStart + common.NS(signature))
        d.addCallback(_cbTestKEXDH_REPLY)

        return d

    def test_keySetup(self):
        """
        Test that _keySetup sets up the next encryption keys.
        """
        self.proto.kexAlg = b"diffie-hellman-group14-sha1"
        self.proto.nextEncryptions = MockCipher()
        self.simulateKeyExchange(b"AB", b"CD")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.simulateKeyExchange(b"AB", b"EF")
        self.assertEqual(self.proto.sessionID, b"CD")
        self.assertEqual(self.packets[-1], (transport.MSG_NEWKEYS, b""))
        newKeys = [self.proto._getKey(c, b"AB", b"EF") for c in iterbytes(b"ABCDEF")]
        self.assertEqual(
            self.proto.nextEncryptions.keys,
            (newKeys[0], newKeys[2], newKeys[1], newKeys[3], newKeys[4], newKeys[5]),
        )

    def test_NEWKEYS(self):
        """
        Test that NEWKEYS transitions the keys from nextEncryptions to
        currentEncryptions.
        """
        self.test_KEXINITMultipleAlgorithms()
        secure = [False]

        def stubConnectionSecure():
            secure[0] = True

        self.proto.connectionSecure = stubConnectionSecure

        self.proto.nextEncryptions = transport.SSHCiphers(
            b"none", b"none", b"none", b"none"
        )
        self.simulateKeyExchange(b"AB", b"CD")
        self.assertIsNot(self.proto.currentEncryptions, self.proto.nextEncryptions)

        self.proto.nextEncryptions = MockCipher()
        self.proto.ssh_NEWKEYS(b"")
        self.assertIsNone(self.proto.outgoingCompression)
        self.assertIsNone(self.proto.incomingCompression)
        self.assertIs(self.proto.currentEncryptions, self.proto.nextEncryptions)
        self.assertTrue(secure[0])
        self.proto.outgoingCompressionType = b"zlib"
        self.simulateKeyExchange(b"AB", b"GH")
        self.proto.ssh_NEWKEYS(b"")
        self.assertIsNotNone(self.proto.outgoingCompression)
        self.proto.incomingCompressionType = b"zlib"
        self.simulateKeyExchange(b"AB", b"IJ")
        self.proto.ssh_NEWKEYS(b"")
        self.assertIsNotNone(self.proto.incomingCompression)

    def test_SERVICE_ACCEPT(self):
        """
        Test that the SERVICE_ACCEPT packet starts the requested service.
        """
        self.proto.instance = MockService()
        self.proto.ssh_SERVICE_ACCEPT(b"\x00\x00\x00\x0bMockService")
        self.assertTrue(self.proto.instance.started)

    def test_requestService(self):
        """
        Test that requesting a service sends a SERVICE_REQUEST packet.
        """
        self.proto.requestService(MockService())
        self.assertEqual(
            self.packets,
            [(transport.MSG_SERVICE_REQUEST, b"\x00\x00\x00\x0bMockService")],
        )

    def test_disconnectKEXDH_REPLYBadSignature(self):
        """
        Test that KEXDH_REPLY disconnects if the signature is bad.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEXDH_REPLY()

        d = self.proto.ssh_KEX_DH_GEX_GROUP(packetStart + common.NS(b"bad signature"))
        return d.addCallback(
            lambda _: self.checkDisconnected(transport.DISCONNECT_KEY_EXCHANGE_FAILED)
        )

    def test_disconnectKEX_ECDH_REPLYBadSignature(self):
        """
        Test that KEX_ECDH_REPLY disconnects if the signature is bad.
        """
        kexmsg = (
            b"\xAA" * 16
            + common.NS(b"ecdh-sha2-nistp256")
            + common.NS(b"ssh-rsa")
            + common.NS(b"aes256-ctr")
            + common.NS(b"aes256-ctr")
            + common.NS(b"hmac-sha1")
            + common.NS(b"hmac-sha1")
            + common.NS(b"none")
            + common.NS(b"none")
            + common.NS(b"")
            + common.NS(b"")
            + b"\x00"
            + b"\x00\x00\x00\x00"
        )

        self.proto.ssh_KEXINIT(kexmsg)

        self.proto.dataReceived(b"SSH-2.0-OpenSSH\r\n")

        self.proto.ecPriv = ec.generate_private_key(ec.SECP256R1(), default_backend())
        self.proto.ecPub = self.proto.ecPriv.public_key()

        # Generate the private key
        thisPriv = ec.generate_private_key(ec.SECP256R1(), default_backend())
        # Get the public key
        thisPub = thisPriv.public_key()
        encPub = thisPub.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.proto.curve = ec.SECP256R1()

        self.proto.kexAlg = b"ecdh-sha2-nistp256"

        self.proto._ssh_KEX_ECDH_REPLY(
            common.NS(MockFactory().getPublicKeys()[b"ssh-rsa"].blob())
            + common.NS(encPub)
            + common.NS(b"bad-signature")
        )

        self.checkDisconnected(transport.DISCONNECT_KEY_EXCHANGE_FAILED)

    def test_disconnectNEWKEYSData(self):
        """
        Test that NEWKEYS disconnects if it receives data.
        """
        self.proto.ssh_NEWKEYS(b"bad packet")
        self.checkDisconnected()

    def test_disconnectSERVICE_ACCEPT(self):
        """
        Test that SERVICE_ACCEPT disconnects if the accepted protocol is
        differet from the asked-for protocol.
        """
        self.proto.instance = MockService()
        self.proto.ssh_SERVICE_ACCEPT(b"\x00\x00\x00\x03bad")
        self.checkDisconnected()

    def test_noPayloadSERVICE_ACCEPT(self):
        """
        Some commercial SSH servers don't send a payload with the
        SERVICE_ACCEPT message.  Conch pretends that it got the correct
        name of the service.
        """
        self.proto.instance = MockService()
        self.proto.ssh_SERVICE_ACCEPT(b"")  # no payload
        self.assertTrue(self.proto.instance.started)
        self.assertEqual(len(self.packets), 0)  # not disconnected


class ClientSSHTransportDHGroupExchangeBaseCase(ClientSSHTransportBaseCase):
    """
    Diffie-Hellman group exchange tests for SSHClientTransport.
    """

    """
    1536-bit modulus from RFC 3526
    """
    P1536 = int(
        "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
        "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
        "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
        "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
        "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
        "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
        "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
        "670C354E4ABC9804F1746C08CA237327FFFFFFFFFFFFFFFF",
        16,
    )

    def test_KEXINIT_groupexchange(self):
        """
        KEXINIT packet with a group-exchange key exchange results
        in a KEX_DH_GEX_REQUEST message.
        """
        self.proto.supportedKeyExchanges = [self.kexAlgorithm]
        self.proto.dataReceived(self.transport.value())
        # The response will include our advertised group sizes.
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEX_DH_GEX_REQUEST,
                    b"\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x20\x00",
                )
            ],
        )

    def test_KEX_DH_GEX_GROUP(self):
        """
        Test that the KEX_DH_GEX_GROUP message results in a
        KEX_DH_GEX_INIT message with the client's Diffie-Hellman public key.
        """
        self.test_KEXINIT_groupexchange()
        self.proto.ssh_KEX_DH_GEX_GROUP(common.MP(self.P1536) + common.MP(2))
        self.assertEqual(self.proto.p, self.P1536)
        self.assertEqual(self.proto.g, 2)
        x = self.proto.dhSecretKey.private_numbers().x
        self.assertEqual(common.MP(x)[5:], b"\x99" * 192)
        self.assertEqual(
            self.proto.dhSecretKeyPublicMP, common.MP(pow(2, x, self.P1536))
        )
        self.assertEqual(
            self.packets[1:],
            [(transport.MSG_KEX_DH_GEX_INIT, self.proto.dhSecretKeyPublicMP)],
        )

    def begin_KEX_DH_GEX_REPLY(self):
        """
        Utility for test_KEX_DH_GEX_REPLY and
        test_disconnectGEX_REPLYBadSignature.

        Begins a Diffie-Hellman key exchange in an unnamed
        (server-specified) group and computes information needed to
        return either a correct or incorrect signature.
        """
        self.test_KEX_DH_GEX_GROUP()
        p = self.proto.p
        f = 3
        fMP = common.MP(f)
        sharedSecret = _MPpow(f, self.proto.dhSecretKey.private_numbers().x, p)
        h = self.hashProcessor()
        h.update(common.NS(self.proto.ourVersionString) * 2)
        h.update(common.NS(self.proto.ourKexInitPayload) * 2)
        h.update(common.NS(self.blob))
        # Here is the wire format for advertised min, pref and max DH sizes.
        h.update(b"\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00\x20\x00")
        # And the selected group parameters.
        h.update(common.MP(self.P1536) + common.MP(2))
        h.update(self.proto.dhSecretKeyPublicMP)
        h.update(fMP)
        h.update(sharedSecret)
        exchangeHash = h.digest()

        signature = self.privObj.sign(exchangeHash)

        return (exchangeHash, signature, common.NS(self.blob) + fMP)

    def test_KEX_DH_GEX_REPLY(self):
        """
        Test that the KEX_DH_GEX_REPLY message results in a verified
        server.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEX_DH_GEX_REPLY()

        def _cbTestKEX_DH_GEX_REPLY(value):
            self.assertIsNone(value)
            self.assertTrue(self.calledVerifyHostKey)
            self.assertEqual(self.proto.sessionID, exchangeHash)

        d = self.proto.ssh_KEX_DH_GEX_REPLY(packetStart + common.NS(signature))
        d.addCallback(_cbTestKEX_DH_GEX_REPLY)
        return d

    def test_disconnectGEX_REPLYBadSignature(self):
        """
        Test that KEX_DH_GEX_REPLY disconnects if the signature is bad.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEX_DH_GEX_REPLY()

        d = self.proto.ssh_KEX_DH_GEX_REPLY(packetStart + common.NS(b"bad signature"))
        return d.addCallback(
            lambda _: self.checkDisconnected(transport.DISCONNECT_KEY_EXCHANGE_FAILED)
        )

    def test_disconnectKEX_ECDH_REPLYBadSignature(self):
        """
        Test that KEX_ECDH_REPLY disconnects if the signature is bad.
        """
        kexmsg = (
            b"\xAA" * 16
            + common.NS(b"ecdh-sha2-nistp256")
            + common.NS(b"ssh-rsa")
            + common.NS(b"aes256-ctr")
            + common.NS(b"aes256-ctr")
            + common.NS(b"hmac-sha1")
            + common.NS(b"hmac-sha1")
            + common.NS(b"none")
            + common.NS(b"none")
            + common.NS(b"")
            + common.NS(b"")
            + b"\x00"
            + b"\x00\x00\x00\x00"
        )

        self.proto.ssh_KEXINIT(kexmsg)

        self.proto.dataReceived(b"SSH-2.0-OpenSSH\r\n")

        self.proto.ecPriv = ec.generate_private_key(ec.SECP256R1(), default_backend())
        self.proto.ecPub = self.proto.ecPriv.public_key()

        # Generate the private key
        thisPriv = ec.generate_private_key(ec.SECP256R1(), default_backend())
        # Get the public key
        thisPub = thisPriv.public_key()
        encPub = thisPub.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.proto.curve = ec.SECP256R1()

        self.proto.kexAlg = b"ecdh-sha2-nistp256"

        self.proto._ssh_KEX_ECDH_REPLY(
            common.NS(MockFactory().getPublicKeys()[b"ssh-rsa"].blob())
            + common.NS(encPub)
            + common.NS(b"bad-signature")
        )

        self.checkDisconnected(transport.DISCONNECT_KEY_EXCHANGE_FAILED)


class ClientSSHTransportDHGroupExchangeSHA1Tests(
    ClientSSHTransportDHGroupExchangeBaseCase,
    DHGroupExchangeSHA1Mixin,
    TransportTestCase,
):
    """
    diffie-hellman-group-exchange-sha1 tests for SSHClientTransport.
    """


class ClientSSHTransportDHGroupExchangeSHA256Tests(
    ClientSSHTransportDHGroupExchangeBaseCase,
    DHGroupExchangeSHA256Mixin,
    TransportTestCase,
):
    """
    diffie-hellman-group-exchange-sha256 tests for SSHClientTransport.
    """


class ClientSSHTransportECDHBaseCase(ClientSSHTransportBaseCase):
    """
    Elliptic Curve Diffie-Hellman tests for SSHClientTransport.
    """

    def test_KEXINIT(self):
        """
        KEXINIT packet with an elliptic curve key exchange results
        in a KEXDH_INIT message.
        """
        self.proto.supportedKeyExchanges = [self.kexAlgorithm]
        self.proto.dataReceived(self.transport.value())
        # The response will include the client's ephemeral public key.
        self.assertEqual(
            self.packets,
            [
                (
                    transport.MSG_KEXDH_INIT,
                    common.NS(self.proto._encodeECPublicKey(self.proto.ecPub)),
                )
            ],
        )

    def begin_KEXDH_REPLY(self):
        """
        Utility for test_KEXDH_REPLY and
        test_disconnectKEXDH_REPLYBadSignature.

        Begins an Elliptic Curve Diffie-Hellman key exchange and computes
        information needed to return either a correct or incorrect
        signature.
        """
        self.test_KEXINIT()

        privKey = MockFactory().getPrivateKeys()[b"ssh-rsa"]
        pubKey = MockFactory().getPublicKeys()[b"ssh-rsa"]
        ecPriv = self.proto._generateECPrivateKey()
        ecPub = ecPriv.public_key()
        encPub = self.proto._encodeECPublicKey(ecPub)

        sharedSecret = self.proto._generateECSharedSecret(
            ecPriv, self.proto._encodeECPublicKey(self.proto.ecPub)
        )

        h = self.hashProcessor()
        h.update(common.NS(self.proto.ourVersionString))
        h.update(common.NS(self.proto.otherVersionString))
        h.update(common.NS(self.proto.ourKexInitPayload))
        h.update(common.NS(self.proto.otherKexInitPayload))
        h.update(common.NS(pubKey.blob()))
        h.update(common.NS(self.proto._encodeECPublicKey(self.proto.ecPub)))
        h.update(common.NS(encPub))
        h.update(sharedSecret)
        exchangeHash = h.digest()

        signature = privKey.sign(exchangeHash)

        return (exchangeHash, signature, common.NS(pubKey.blob()) + common.NS(encPub))

    def test_KEXDH_REPLY(self):
        """
        Test that the KEXDH_REPLY message completes the key exchange.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEXDH_REPLY()

        def _cbTestKEXDH_REPLY(value):
            self.assertIsNone(value)
            self.assertTrue(self.calledVerifyHostKey)
            self.assertEqual(self.proto.sessionID, exchangeHash)

        d = self.proto.ssh_KEX_DH_GEX_GROUP(packetStart + common.NS(signature))
        d.addCallback(_cbTestKEXDH_REPLY)
        return d

    def test_disconnectKEXDH_REPLYBadSignature(self):
        """
        Test that KEX_ECDH_REPLY disconnects if the signature is bad.
        """
        (exchangeHash, signature, packetStart) = self.begin_KEXDH_REPLY()

        d = self.proto.ssh_KEX_DH_GEX_GROUP(packetStart + common.NS(b"bad signature"))
        return d.addCallback(
            lambda _: self.checkDisconnected(transport.DISCONNECT_KEY_EXCHANGE_FAILED)
        )


class ClientSSHTransportECDHTests(
    ClientSSHTransportECDHBaseCase, ECDHMixin, TransportTestCase
):
    """
    ecdh-sha2-nistp256 tests for SSHClientTransport.
    """


@skipWithoutX25519
class ClientSSHTransportCurve25519SHA256Tests(
    ClientSSHTransportECDHBaseCase, Curve25519SHA256Mixin, TransportTestCase
):
    """
    curve25519-sha256 tests for SSHClientTransport.
    """


class GetMACTests(TestCase):
    """
    Tests for L{SSHCiphers._getMAC}.
    """

    if dependencySkip:
        skip = dependencySkip

    def setUp(self):
        self.ciphers = transport.SSHCiphers(b"A", b"B", b"C", b"D")

    def getSharedSecret(self):
        """
        Generate a new shared secret to be used with the tests.

        @return: A new secret.
        @rtype: L{bytes}
        """
        return insecureRandom(64)

    def assertGetMAC(self, hmacName, hashProcessor, digestSize, blockPadSize):
        """
        Check that when L{SSHCiphers._getMAC} is called with a supportd HMAC
        algorithm name it returns a tuple of
        (digest object, inner pad, outer pad, digest size) with a C{key}
        attribute set to the value of the key supplied.

        @param hmacName: Identifier of HMAC algorithm.
        @type hmacName: L{bytes}

        @param hashProcessor: Callable for the hash algorithm.
        @type hashProcessor: C{callable}

        @param digestSize: Size of the digest for algorithm.
        @type digestSize: L{int}

        @param blockPadSize: Size of padding applied to the shared secret to
            match the block size.
        @type blockPadSize: L{int}
        """
        secret = self.getSharedSecret()

        params = self.ciphers._getMAC(hmacName, secret)

        key = secret[:digestSize] + b"\x00" * blockPadSize
        innerPad = bytes(ord(b) ^ 0x36 for b in iterbytes(key))
        outerPad = bytes(ord(b) ^ 0x5C for b in iterbytes(key))
        self.assertEqual((hashProcessor, innerPad, outerPad, digestSize), params)
        self.assertEqual(key, params.key)

    def test_hmacsha2512(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"hmac-sha2-512"} MAC
        algorithm name it returns a tuple of (sha512 digest object, inner pad,
        outer pad, sha512 digest size) with a C{key} attribute set to the
        value of the key supplied.
        """
        self.assertGetMAC(b"hmac-sha2-512", sha512, digestSize=64, blockPadSize=64)

    def test_hmacsha2384(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"hmac-sha2-384"} MAC
        algorithm name it returns a tuple of (sha384 digest object, inner pad,
        outer pad, sha384 digest size) with a C{key} attribute set to the
        value of the key supplied.
        """
        self.assertGetMAC(b"hmac-sha2-384", sha384, digestSize=48, blockPadSize=80)

    def test_hmacsha2256(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"hmac-sha2-256"} MAC
        algorithm name it returns a tuple of (sha256 digest object, inner pad,
        outer pad, sha256 digest size) with a C{key} attribute set to the
        value of the key supplied.
        """
        self.assertGetMAC(b"hmac-sha2-256", sha256, digestSize=32, blockPadSize=32)

    def test_hmacsha1(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"hmac-sha1"} MAC
        algorithm name it returns a tuple of (sha1 digest object, inner pad,
        outer pad, sha1 digest size) with a C{key} attribute set to the value
        of the key supplied.
        """
        self.assertGetMAC(b"hmac-sha1", sha1, digestSize=20, blockPadSize=44)

    def test_hmacmd5(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"hmac-md5"} MAC
        algorithm name it returns a tuple of (md5 digest object, inner pad,
        outer pad, md5 digest size) with a C{key} attribute set to the value of
        the key supplied.
        """
        self.assertGetMAC(b"hmac-md5", md5, digestSize=16, blockPadSize=48)

    def test_none(self):
        """
        When L{SSHCiphers._getMAC} is called with the C{b"none"} MAC algorithm
        name it returns a tuple of (None, "", "", 0).
        """
        key = self.getSharedSecret()

        params = self.ciphers._getMAC(b"none", key)

        self.assertEqual((None, b"", b"", 0), params)


class SSHCiphersTests(TestCase):
    """
    Tests for the SSHCiphers helper class.
    """

    if dependencySkip:
        skip = dependencySkip

    def test_init(self):
        """
        Test that the initializer sets up the SSHCiphers object.
        """
        ciphers = transport.SSHCiphers(b"A", b"B", b"C", b"D")
        self.assertEqual(ciphers.outCipType, b"A")
        self.assertEqual(ciphers.inCipType, b"B")
        self.assertEqual(ciphers.outMACType, b"C")
        self.assertEqual(ciphers.inMACType, b"D")

    def test_getCipher(self):
        """
        Test that the _getCipher method returns the correct cipher.
        """
        ciphers = transport.SSHCiphers(b"A", b"B", b"C", b"D")
        iv = key = b"\x00" * 16
        for cipName, (algClass, keySize, counter) in ciphers.cipherMap.items():
            cip = ciphers._getCipher(cipName, iv, key)
            if cipName == b"none":
                self.assertIsInstance(cip, transport._DummyCipher)
            else:
                self.assertIsInstance(cip.algorithm, algClass)

    def test_setKeysCiphers(self):
        """
        Test that setKeys sets up the ciphers.
        """
        key = b"\x00" * 64
        for cipName in transport.SSHTransportBase.supportedCiphers:
            modName, keySize, counter = transport.SSHCiphers.cipherMap[cipName]
            encCipher = transport.SSHCiphers(cipName, b"none", b"none", b"none")
            decCipher = transport.SSHCiphers(b"none", cipName, b"none", b"none")
            cip = encCipher._getCipher(cipName, key, key)
            bs = cip.algorithm.block_size // 8
            encCipher.setKeys(key, key, b"", b"", b"", b"")
            decCipher.setKeys(b"", b"", key, key, b"", b"")
            self.assertEqual(encCipher.encBlockSize, bs)
            self.assertEqual(decCipher.decBlockSize, bs)
            encryptor = cip.encryptor()
            enc = encryptor.update(key[:bs])
            enc2 = encryptor.update(key[:bs])
            self.assertEqual(encCipher.encrypt(key[:bs]), enc)
            self.assertEqual(encCipher.encrypt(key[:bs]), enc2)
            self.assertEqual(decCipher.decrypt(enc), key[:bs])
            self.assertEqual(decCipher.decrypt(enc2), key[:bs])

    def test_setKeysMACs(self):
        """
        Test that setKeys sets up the MACs.
        """
        key = b"\x00" * 64
        for macName, mod in transport.SSHCiphers.macMap.items():
            outMac = transport.SSHCiphers(b"none", b"none", macName, b"none")
            inMac = transport.SSHCiphers(b"none", b"none", b"none", macName)
            outMac.setKeys(b"", b"", b"", b"", key, b"")
            inMac.setKeys(b"", b"", b"", b"", b"", key)
            if mod:
                ds = mod().digest_size
            else:
                ds = 0
            self.assertEqual(inMac.verifyDigestSize, ds)
            if mod:
                mod, i, o, ds = outMac._getMAC(macName, key)
            seqid = 0
            data = key
            packet = b"\x00" * 4 + key
            if mod:
                mac = mod(o + mod(i + packet).digest()).digest()
            else:
                mac = b""
            self.assertEqual(outMac.makeMAC(seqid, data), mac)
            self.assertTrue(inMac.verify(seqid, data, mac))

    def test_makeMAC(self):
        """
        L{SSHCiphers.makeMAC} computes the HMAC of an outgoing SSH message with
        a particular sequence id and content data.
        """
        # Use the test vectors given in the appendix of RFC 2104.
        vectors = [
            (b"\x0b" * 16, b"Hi There", b"9294727a3638bb1c13f48ef8158bfc9d"),
            (
                b"Jefe",
                b"what do ya want for nothing?",
                b"750c783e6ab0b503eaa86e310a5db738",
            ),
            (b"\xAA" * 16, b"\xDD" * 50, b"56be34521d144c88dbb8c733f0e8b3f6"),
        ]

        for key, data, mac in vectors:
            outMAC = transport.SSHCiphers(b"none", b"none", b"hmac-md5", b"none")
            outMAC.outMAC = outMAC._getMAC(b"hmac-md5", key)
            (seqid,) = struct.unpack(">L", data[:4])
            shortened = data[4:]
            self.assertEqual(
                mac,
                binascii.hexlify(outMAC.makeMAC(seqid, shortened)),
                f"Failed HMAC test vector; key={key!r} data={data!r}",
            )


class TransportLoopbackTests(TestCase):
    """
    Test the server transport and client transport against each other,
    """

    if dependencySkip:
        skip = dependencySkip

    def _runClientServer(self, mod):
        """
        Run an async client and server, modifying each using the mod function
        provided.  Returns a Deferred called back when both Protocols have
        disconnected.

        @type mod: C{func}
        @rtype: C{defer.Deferred}
        """
        factory = MockFactory()
        server = transport.SSHServerTransport()
        server.factory = factory
        factory.startFactory()
        server.errors = []
        server.receiveError = lambda code, desc: server.errors.append((code, desc))
        client = transport.SSHClientTransport()
        client.verifyHostKey = lambda x, y: defer.succeed(None)
        client.errors = []
        client.receiveError = lambda code, desc: client.errors.append((code, desc))
        client.connectionSecure = lambda: client.loseConnection()
        server.supportedPublicKeys = list(server.factory.getPublicKeys().keys())
        server = mod(server)
        client = mod(client)

        def check(ignored, server, client):
            name = repr(
                [
                    server.supportedCiphers[0],
                    server.supportedMACs[0],
                    server.supportedKeyExchanges[0],
                    server.supportedCompressions[0],
                ]
            )
            self.assertEqual(client.errors, [])
            self.assertEqual(
                server.errors,
                [(transport.DISCONNECT_CONNECTION_LOST, b"user closed connection")],
            )
            if server.supportedCiphers[0] == b"none":
                self.assertFalse(server.isEncrypted(), name)
                self.assertFalse(client.isEncrypted(), name)
            else:
                self.assertTrue(server.isEncrypted(), name)
                self.assertTrue(client.isEncrypted(), name)
            if server.supportedMACs[0] == b"none":
                self.assertFalse(server.isVerified(), name)
                self.assertFalse(client.isVerified(), name)
            else:
                self.assertTrue(server.isVerified(), name)
                self.assertTrue(client.isVerified(), name)

        d = loopback.loopbackAsync(server, client)
        d.addCallback(check, server, client)
        return d

    def test_ciphers(self):
        """
        Test that the client and server play nicely together, in all
        the various combinations of ciphers.
        """
        deferreds = []
        for cipher in transport.SSHTransportBase.supportedCiphers + [b"none"]:

            def setCipher(proto):
                proto.supportedCiphers = [cipher]
                return proto

            deferreds.append(self._runClientServer(setCipher))
        return defer.DeferredList(deferreds, fireOnOneErrback=True)

    def test_macs(self):
        """
        Like test_ciphers, but for the various MACs.
        """
        deferreds = []
        for mac in transport.SSHTransportBase.supportedMACs + [b"none"]:

            def setMAC(proto):
                proto.supportedMACs = [mac]
                return proto

            deferreds.append(self._runClientServer(setMAC))
        return defer.DeferredList(deferreds, fireOnOneErrback=True)

    def test_keyexchanges(self):
        """
        Like test_ciphers, but for the various key exchanges.
        """
        deferreds = []
        for kexAlgorithm in transport.SSHTransportBase.supportedKeyExchanges:

            def setKeyExchange(proto):
                proto.supportedKeyExchanges = [kexAlgorithm]
                return proto

            deferreds.append(self._runClientServer(setKeyExchange))
        return defer.DeferredList(deferreds, fireOnOneErrback=True)

    def test_compressions(self):
        """
        Like test_ciphers, but for the various compressions.
        """
        deferreds = []
        for compression in transport.SSHTransportBase.supportedCompressions:

            def setCompression(proto):
                proto.supportedCompressions = [compression]
                return proto

            deferreds.append(self._runClientServer(setCompression))
        return defer.DeferredList(deferreds, fireOnOneErrback=True)
