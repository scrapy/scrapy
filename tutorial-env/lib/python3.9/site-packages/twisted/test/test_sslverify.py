# Copyright 2005 Divmod, Inc.  See LICENSE file for details
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet._sslverify}.
"""


import datetime
import itertools
import sys
from unittest import skipIf

from zope.interface import implementer

from incremental import Version

from twisted.internet import defer, interfaces, protocol, reactor
from twisted.internet._idna import _idnaText
from twisted.internet.error import CertificateError, ConnectionClosed, ConnectionLost
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath
from twisted.python.modules import getModule
from twisted.python.reflect import requireModule
from twisted.test.iosim import connectedServerAndClient
from twisted.test.test_twisted import SetAsideModule
from twisted.trial import util
from twisted.trial.unittest import SkipTest, SynchronousTestCase, TestCase

skipSSL = ""
skipSNI = ""
skipNPN = ""
skipALPN = ""

if requireModule("OpenSSL"):
    import ipaddress

    from OpenSSL import SSL
    from OpenSSL.crypto import FILETYPE_PEM, TYPE_RSA, X509, PKey, get_elliptic_curves

    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )
    from cryptography.x509.oid import NameOID

    from twisted.internet import ssl

    try:
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.set_npn_advertise_callback(lambda c: None)
    except (NotImplementedError, AttributeError):
        skipNPN = (
            "NPN is deprecated (and OpenSSL 1.0.1 or greater required for NPN"
            " support)"
        )

    try:
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.set_alpn_select_callback(lambda c: None)  # type: ignore[misc,arg-type]
    except NotImplementedError:
        skipALPN = "OpenSSL 1.0.2 or greater required for ALPN support"
else:
    skipSSL = "OpenSSL is required for SSL tests."
    skipSNI = skipSSL
    skipNPN = skipSSL
    skipALPN = skipSSL

if not skipSSL:
    from twisted.internet import _sslverify as sslverify
    from twisted.internet.ssl import VerificationError, platformTrust
    from twisted.protocols.tls import TLSMemoryBIOFactory


# A couple of static PEM-format certificates to be used by various tests.
A_HOST_CERTIFICATE_PEM = """
-----BEGIN CERTIFICATE-----
        MIIC2jCCAkMCAjA5MA0GCSqGSIb3DQEBBAUAMIG0MQswCQYDVQQGEwJVUzEiMCAG
        A1UEAxMZZXhhbXBsZS50d2lzdGVkbWF0cml4LmNvbTEPMA0GA1UEBxMGQm9zdG9u
        MRwwGgYDVQQKExNUd2lzdGVkIE1hdHJpeCBMYWJzMRYwFAYDVQQIEw1NYXNzYWNo
        dXNldHRzMScwJQYJKoZIhvcNAQkBFhhub2JvZHlAdHdpc3RlZG1hdHJpeC5jb20x
        ETAPBgNVBAsTCFNlY3VyaXR5MB4XDTA2MDgxNjAxMDEwOFoXDTA3MDgxNjAxMDEw
        OFowgbQxCzAJBgNVBAYTAlVTMSIwIAYDVQQDExlleGFtcGxlLnR3aXN0ZWRtYXRy
        aXguY29tMQ8wDQYDVQQHEwZCb3N0b24xHDAaBgNVBAoTE1R3aXN0ZWQgTWF0cml4
        IExhYnMxFjAUBgNVBAgTDU1hc3NhY2h1c2V0dHMxJzAlBgkqhkiG9w0BCQEWGG5v
        Ym9keUB0d2lzdGVkbWF0cml4LmNvbTERMA8GA1UECxMIU2VjdXJpdHkwgZ8wDQYJ
        KoZIhvcNAQEBBQADgY0AMIGJAoGBAMzH8CDF/U91y/bdbdbJKnLgnyvQ9Ig9ZNZp
        8hpsu4huil60zF03+Lexg2l1FIfURScjBuaJMR6HiMYTMjhzLuByRZ17KW4wYkGi
        KXstz03VIKy4Tjc+v4aXFI4XdRw10gGMGQlGGscXF/RSoN84VoDKBfOMWdXeConJ
        VyC4w3iJAgMBAAEwDQYJKoZIhvcNAQEEBQADgYEAviMT4lBoxOgQy32LIgZ4lVCj
        JNOiZYg8GMQ6y0ugp86X80UjOvkGtNf/R7YgED/giKRN/q/XJiLJDEhzknkocwmO
        S+4b2XpiaZYxRyKWwL221O7CGmtWYyZl2+92YYmmCiNzWQPfP6BOMlfax0AGLHls
        fXzCWdG0O/3Lk2SRM0I=
-----END CERTIFICATE-----
"""

A_PEER_CERTIFICATE_PEM = """
-----BEGIN CERTIFICATE-----
        MIIC3jCCAkcCAjA6MA0GCSqGSIb3DQEBBAUAMIG2MQswCQYDVQQGEwJVUzEiMCAG
        A1UEAxMZZXhhbXBsZS50d2lzdGVkbWF0cml4LmNvbTEPMA0GA1UEBxMGQm9zdG9u
        MRwwGgYDVQQKExNUd2lzdGVkIE1hdHJpeCBMYWJzMRYwFAYDVQQIEw1NYXNzYWNo
        dXNldHRzMSkwJwYJKoZIhvcNAQkBFhpzb21lYm9keUB0d2lzdGVkbWF0cml4LmNv
        bTERMA8GA1UECxMIU2VjdXJpdHkwHhcNMDYwODE2MDEwMTU2WhcNMDcwODE2MDEw
        MTU2WjCBtjELMAkGA1UEBhMCVVMxIjAgBgNVBAMTGWV4YW1wbGUudHdpc3RlZG1h
        dHJpeC5jb20xDzANBgNVBAcTBkJvc3RvbjEcMBoGA1UEChMTVHdpc3RlZCBNYXRy
        aXggTGFiczEWMBQGA1UECBMNTWFzc2FjaHVzZXR0czEpMCcGCSqGSIb3DQEJARYa
        c29tZWJvZHlAdHdpc3RlZG1hdHJpeC5jb20xETAPBgNVBAsTCFNlY3VyaXR5MIGf
        MA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCnm+WBlgFNbMlHehib9ePGGDXF+Nz4
        CjGuUmVBaXCRCiVjg3kSDecwqfb0fqTksBZ+oQ1UBjMcSh7OcvFXJZnUesBikGWE
        JE4V8Bjh+RmbJ1ZAlUPZ40bAkww0OpyIRAGMvKG+4yLFTO4WDxKmfDcrOb6ID8WJ
        e1u+i3XGkIf/5QIDAQABMA0GCSqGSIb3DQEBBAUAA4GBAD4Oukm3YYkhedUepBEA
        vvXIQhVDqL7mk6OqYdXmNj6R7ZMC8WWvGZxrzDI1bZuB+4aIxxd1FXC3UOHiR/xg
        i9cDl1y8P/qRp4aEBNF6rI0D4AxTbfnHQx4ERDAOShJdYZs/2zifPJ6va6YvrEyr
        yqDtGhklsWW3ZwBzEh5VEOUp
-----END CERTIFICATE-----
"""

A_KEYPAIR = getModule(__name__).filePath.sibling("server.pem").getContent()


def counter(counter=itertools.count()):
    """
    Each time we're called, return the next integer in the natural numbers.
    """
    return next(counter)


def makeCertificate(**kw):
    keypair = PKey()
    keypair.generate_key(TYPE_RSA, 2048)

    certificate = X509()
    certificate.gmtime_adj_notBefore(0)
    certificate.gmtime_adj_notAfter(60 * 60 * 24 * 365)  # One year
    for xname in certificate.get_issuer(), certificate.get_subject():
        for (k, v) in kw.items():
            setattr(xname, k, nativeString(v))

    certificate.set_serial_number(counter())
    certificate.set_pubkey(keypair)
    certificate.sign(keypair, "md5")

    return keypair, certificate


def certificatesForAuthorityAndServer(serviceIdentity="example.com"):
    """
    Create a self-signed CA certificate and server certificate signed by the
    CA.

    @param serviceIdentity: The identity (hostname) of the server.
    @type serviceIdentity: L{unicode}

    @return: a 2-tuple of C{(certificate_authority_certificate,
        server_certificate)}
    @rtype: L{tuple} of (L{sslverify.Certificate},
        L{sslverify.PrivateCertificate})
    """
    commonNameForCA = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Testing Example CA")]
    )
    commonNameForServer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Testing Example Server")]
    )
    oneDay = datetime.timedelta(1, 0, 0)
    privateKeyForCA = rsa.generate_private_key(
        public_exponent=65537, key_size=4096, backend=default_backend()
    )
    publicKeyForCA = privateKeyForCA.public_key()
    caCertificate = (
        x509.CertificateBuilder()
        .subject_name(commonNameForCA)
        .issuer_name(commonNameForCA)
        .not_valid_before(datetime.datetime.today() - oneDay)
        .not_valid_after(datetime.datetime.today() + oneDay)
        .serial_number(x509.random_serial_number())
        .public_key(publicKeyForCA)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=9),
            critical=True,
        )
        .sign(
            private_key=privateKeyForCA,
            algorithm=hashes.SHA256(),
            backend=default_backend(),
        )
    )

    privateKeyForServer = rsa.generate_private_key(
        public_exponent=65537, key_size=4096, backend=default_backend()
    )
    publicKeyForServer = privateKeyForServer.public_key()

    try:
        ipAddress = ipaddress.ip_address(serviceIdentity)
    except ValueError:
        subjectAlternativeNames = [
            x509.DNSName(serviceIdentity.encode("idna").decode("ascii"))
        ]
    else:
        subjectAlternativeNames = [x509.IPAddress(ipAddress)]

    serverCertificate = (
        x509.CertificateBuilder()
        .subject_name(commonNameForServer)
        .issuer_name(commonNameForCA)
        .not_valid_before(datetime.datetime.today() - oneDay)
        .not_valid_after(datetime.datetime.today() + oneDay)
        .serial_number(x509.random_serial_number())
        .public_key(publicKeyForServer)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName(subjectAlternativeNames),
            critical=True,
        )
        .sign(
            private_key=privateKeyForCA,
            algorithm=hashes.SHA256(),
            backend=default_backend(),
        )
    )
    caSelfCert = sslverify.Certificate.loadPEM(caCertificate.public_bytes(Encoding.PEM))
    serverCert = sslverify.PrivateCertificate.loadPEM(
        b"\n".join(
            [
                privateKeyForServer.private_bytes(
                    Encoding.PEM,
                    PrivateFormat.TraditionalOpenSSL,
                    NoEncryption(),
                ),
                serverCertificate.public_bytes(Encoding.PEM),
            ]
        )
    )

    return caSelfCert, serverCert


def _loopbackTLSConnection(serverOpts, clientOpts):
    """
    Common implementation code for both L{loopbackTLSConnection} and
    L{loopbackTLSConnectionInMemory}. Creates a loopback TLS connection
    using the provided server and client context factories.

    @param serverOpts: An OpenSSL context factory for the server.
    @type serverOpts: C{OpenSSLCertificateOptions}, or any class with an
        equivalent API.

    @param clientOpts: An OpenSSL context factory for the client.
    @type clientOpts: C{OpenSSLCertificateOptions}, or any class with an
        equivalent API.

    @return: 5-tuple of server-tls-protocol, server-inner-protocol,
        client-tls-protocol, client-inner-protocol and L{IOPump}
    @rtype: L{tuple}
    """

    class GreetingServer(protocol.Protocol):
        greeting = b"greetings!"

        def connectionMade(self):
            self.transport.write(self.greeting)

    class ListeningClient(protocol.Protocol):
        data = b""
        lostReason = None

        def dataReceived(self, data):
            self.data += data

        def connectionLost(self, reason):
            self.lostReason = reason

    clientWrappedProto = ListeningClient()
    serverWrappedProto = GreetingServer()

    plainClientFactory = protocol.Factory()
    plainClientFactory.protocol = lambda: clientWrappedProto
    plainServerFactory = protocol.Factory()
    plainServerFactory.protocol = lambda: serverWrappedProto

    clientFactory = TLSMemoryBIOFactory(
        clientOpts, isClient=True, wrappedFactory=plainServerFactory
    )
    serverFactory = TLSMemoryBIOFactory(
        serverOpts, isClient=False, wrappedFactory=plainClientFactory
    )

    sProto, cProto, pump = connectedServerAndClient(
        lambda: serverFactory.buildProtocol(None),
        lambda: clientFactory.buildProtocol(None),
    )
    return sProto, cProto, serverWrappedProto, clientWrappedProto, pump


def loopbackTLSConnection(trustRoot, privateKeyFile, chainedCertFile=None):
    """
    Create a loopback TLS connection with the given trust and keys.

    @param trustRoot: the C{trustRoot} argument for the client connection's
        context.
    @type trustRoot: L{sslverify.IOpenSSLTrustRoot}

    @param privateKeyFile: The name of the file containing the private key.
    @type privateKeyFile: L{str} (native string; file name)

    @param chainedCertFile: The name of the chained certificate file.
    @type chainedCertFile: L{str} (native string; file name)

    @return: 3-tuple of server-protocol, client-protocol, and L{IOPump}
    @rtype: L{tuple}
    """

    class ContextFactory:
        def getContext(self):
            """
            Create a context for the server side of the connection.

            @return: an SSL context using a certificate and key.
            @rtype: C{OpenSSL.SSL.Context}
            """
            ctx = SSL.Context(SSL.SSLv23_METHOD)
            if chainedCertFile is not None:
                ctx.use_certificate_chain_file(chainedCertFile)
            ctx.use_privatekey_file(privateKeyFile)
            # Let the test author know if they screwed something up.
            ctx.check_privatekey()
            return ctx

    serverOpts = ContextFactory()
    clientOpts = sslverify.OpenSSLCertificateOptions(trustRoot=trustRoot)

    return _loopbackTLSConnection(serverOpts, clientOpts)


def loopbackTLSConnectionInMemory(
    trustRoot,
    privateKey,
    serverCertificate,
    clientProtocols=None,
    serverProtocols=None,
    clientOptions=None,
):
    """
    Create a loopback TLS connection with the given trust and keys. Like
    L{loopbackTLSConnection}, but using in-memory certificates and keys rather
    than writing them to disk.

    @param trustRoot: the C{trustRoot} argument for the client connection's
        context.
    @type trustRoot: L{sslverify.IOpenSSLTrustRoot}

    @param privateKey: The private key.
    @type privateKey: L{str} (native string)

    @param serverCertificate: The certificate used by the server.
    @type chainedCertFile: L{str} (native string)

    @param clientProtocols: The protocols the client is willing to negotiate
        using NPN/ALPN.

    @param serverProtocols: The protocols the server is willing to negotiate
        using NPN/ALPN.

    @param clientOptions: The type of C{OpenSSLCertificateOptions} class to
        use for the client. Defaults to C{OpenSSLCertificateOptions}.

    @return: 3-tuple of server-protocol, client-protocol, and L{IOPump}
    @rtype: L{tuple}
    """
    if clientOptions is None:
        clientOptions = sslverify.OpenSSLCertificateOptions

    clientCertOpts = clientOptions(
        trustRoot=trustRoot, acceptableProtocols=clientProtocols
    )
    serverCertOpts = sslverify.OpenSSLCertificateOptions(
        privateKey=privateKey,
        certificate=serverCertificate,
        acceptableProtocols=serverProtocols,
    )

    return _loopbackTLSConnection(serverCertOpts, clientCertOpts)


def pathContainingDumpOf(testCase, *dumpables):
    """
    Create a temporary file to store some serializable-as-PEM objects in, and
    return its name.

    @param testCase: a test case to use for generating a temporary directory.
    @type testCase: L{twisted.trial.unittest.TestCase}

    @param dumpables: arguments are objects from pyOpenSSL with a C{dump}
        method, taking a pyOpenSSL file-type constant, such as
        L{OpenSSL.crypto.FILETYPE_PEM} or L{OpenSSL.crypto.FILETYPE_ASN1}.
    @type dumpables: L{tuple} of L{object} with C{dump} method taking L{int}
        returning L{bytes}

    @return: the path to a file where all of the dumpables were dumped in PEM
        format.
    @rtype: L{str}
    """
    fname = testCase.mktemp()
    with open(fname, "wb") as f:
        for dumpable in dumpables:
            f.write(dumpable.dump(FILETYPE_PEM))
    return fname


class DataCallbackProtocol(protocol.Protocol):
    def dataReceived(self, data):
        d, self.factory.onData = self.factory.onData, None
        if d is not None:
            d.callback(data)

    def connectionLost(self, reason):
        d, self.factory.onLost = self.factory.onLost, None
        if d is not None:
            d.errback(reason)


class WritingProtocol(protocol.Protocol):
    byte = b"x"

    def connectionMade(self):
        self.transport.write(self.byte)

    def connectionLost(self, reason):
        self.factory.onLost.errback(reason)


class FakeContext:
    """
    Introspectable fake of an C{OpenSSL.SSL.Context}.

    Saves call arguments for later introspection.

    Necessary because C{Context} offers poor introspection.  cf. this
    U{pyOpenSSL bug<https://bugs.launchpad.net/pyopenssl/+bug/1173899>}.

    @ivar _method: See C{method} parameter of L{__init__}.

    @ivar _options: L{int} of C{OR}ed values from calls of L{set_options}.

    @ivar _certificate: Set by L{use_certificate}.

    @ivar _privateKey: Set by L{use_privatekey}.

    @ivar _verify: Set by L{set_verify}.

    @ivar _verifyDepth: Set by L{set_verify_depth}.

    @ivar _mode: Set by L{set_mode}.

    @ivar _sessionID: Set by L{set_session_id}.

    @ivar _extraCertChain: Accumulated L{list} of all extra certificates added
        by L{add_extra_chain_cert}.

    @ivar _cipherList: Set by L{set_cipher_list}.

    @ivar _dhFilename: Set by L{load_tmp_dh}.

    @ivar _defaultVerifyPathsSet: Set by L{set_default_verify_paths}

    @ivar _ecCurve: Set by L{set_tmp_ecdh}
    """

    _options = 0

    def __init__(self, method):
        self._method = method
        self._extraCertChain = []
        self._defaultVerifyPathsSet = False
        self._ecCurve = None

        # Note that this value is explicitly documented as the default by
        # https://www.openssl.org/docs/man1.1.1/man3/
        # SSL_CTX_set_session_cache_mode.html
        self._sessionCacheMode = SSL.SESS_CACHE_SERVER

    def set_options(self, options):
        self._options |= options

    def use_certificate(self, certificate):
        self._certificate = certificate

    def use_privatekey(self, privateKey):
        self._privateKey = privateKey

    def check_privatekey(self):
        return None

    def set_mode(self, mode):
        """
        Set the mode. See L{SSL.Context.set_mode}.

        @param mode: See L{SSL.Context.set_mode}.
        """
        self._mode = mode

    def set_verify(self, flags, callback=None):
        self._verify = flags, callback

    def set_verify_depth(self, depth):
        self._verifyDepth = depth

    def set_session_id(self, sessionIDContext):
        # This fake should change when the upstream changes:
        # https://github.com/pyca/pyopenssl/issues/845
        self._sessionIDContext = sessionIDContext

    def set_session_cache_mode(self, cacheMode):
        """
        Set the session cache mode on the context, as per
        L{SSL.Context.set_session_cache_mode}.
        """
        self._sessionCacheMode = cacheMode

    def get_session_cache_mode(self):
        """
        Retrieve the session cache mode from the context, as per
        L{SSL.Context.get_session_cache_mode}.
        """
        return self._sessionCacheMode

    def add_extra_chain_cert(self, cert):
        self._extraCertChain.append(cert)

    def set_cipher_list(self, cipherList):
        self._cipherList = cipherList

    def load_tmp_dh(self, dhfilename):
        self._dhFilename = dhfilename

    def set_default_verify_paths(self):
        """
        Set the default paths for the platform.
        """
        self._defaultVerifyPathsSet = True

    def set_tmp_ecdh(self, curve):
        """
        Set an ECDH curve.  Should only be called by OpenSSL 1.0.1
        code.

        @param curve: See L{OpenSSL.SSL.Context.set_tmp_ecdh}
        """
        self._ecCurve = curve


class ClientOptionsTests(SynchronousTestCase):
    """
    Tests for L{sslverify.optionsForClientTLS}.
    """

    if skipSSL:
        skip = skipSSL

    def test_extraKeywords(self):
        """
        When passed a keyword parameter other than C{extraCertificateOptions},
        L{sslverify.optionsForClientTLS} raises an exception just like a
        normal Python function would.
        """
        error = self.assertRaises(
            TypeError,
            sslverify.optionsForClientTLS,
            hostname="alpha",
            someRandomThing="beta",
        )
        self.assertEqual(
            str(error),
            "optionsForClientTLS() got an unexpected keyword argument "
            "'someRandomThing'",
        )

    def test_bytesFailFast(self):
        """
        If you pass L{bytes} as the hostname to
        L{sslverify.optionsForClientTLS} it immediately raises a L{TypeError}.
        """
        error = self.assertRaises(
            TypeError, sslverify.optionsForClientTLS, b"not-actually-a-hostname.com"
        )
        expectedText = (
            "optionsForClientTLS requires text for host names, not " + bytes.__name__
        )
        self.assertEqual(str(error), expectedText)

    def test_dNSNameHostname(self):
        """
        If you pass a dNSName to L{sslverify.optionsForClientTLS}
        L{_hostnameIsDnsName} will be True
        """
        options = sslverify.optionsForClientTLS("example.com")
        self.assertTrue(options._hostnameIsDnsName)

    def test_IPv4AddressHostname(self):
        """
        If you pass an IPv4 address to L{sslverify.optionsForClientTLS}
        L{_hostnameIsDnsName} will be False
        """
        options = sslverify.optionsForClientTLS("127.0.0.1")
        self.assertFalse(options._hostnameIsDnsName)

    def test_IPv6AddressHostname(self):
        """
        If you pass an IPv6 address to L{sslverify.optionsForClientTLS}
        L{_hostnameIsDnsName} will be False
        """
        options = sslverify.optionsForClientTLS("::1")
        self.assertFalse(options._hostnameIsDnsName)


class FakeChooseDiffieHellmanEllipticCurve:
    """
    A fake implementation of L{_ChooseDiffieHellmanEllipticCurve}
    """

    def __init__(self, versionNumber, openSSLlib, openSSLcrypto):
        """
        A no-op constructor.
        """

    def configureECDHCurve(self, ctx):
        """
        A null configuration.

        @param ctx: An L{OpenSSL.SSL.Context} that would be
            configured.
        """


class OpenSSLOptionsTestsMixin:
    """
    A mixin for L{OpenSSLOptions} test cases creates client and server
    certificates, signs them with a CA, and provides a L{loopback}
    that creates TLS a connections with them.
    """

    if skipSSL:
        skip = skipSSL

    serverPort = clientConn = None
    onServerLost = onClientLost = None

    def setUp(self):
        """
        Create class variables of client and server certificates.
        """
        self.sKey, self.sCert = makeCertificate(
            O=b"Server Test Certificate", CN=b"server"
        )
        self.cKey, self.cCert = makeCertificate(
            O=b"Client Test Certificate", CN=b"client"
        )
        self.caCert1 = makeCertificate(O=b"CA Test Certificate 1", CN=b"ca1")[1]
        self.caCert2 = makeCertificate(O=b"CA Test Certificate", CN=b"ca2")[1]
        self.caCerts = [self.caCert1, self.caCert2]
        self.extraCertChain = self.caCerts

    def tearDown(self):
        if self.serverPort is not None:
            self.serverPort.stopListening()
        if self.clientConn is not None:
            self.clientConn.disconnect()

        L = []
        if self.onServerLost is not None:
            L.append(self.onServerLost)
        if self.onClientLost is not None:
            L.append(self.onClientLost)

        return defer.DeferredList(L, consumeErrors=True)

    def loopback(
        self,
        serverCertOpts,
        clientCertOpts,
        onServerLost=None,
        onClientLost=None,
        onData=None,
    ):
        if onServerLost is None:
            self.onServerLost = onServerLost = defer.Deferred()
        if onClientLost is None:
            self.onClientLost = onClientLost = defer.Deferred()
        if onData is None:
            onData = defer.Deferred()

        serverFactory = protocol.ServerFactory()
        serverFactory.protocol = DataCallbackProtocol
        serverFactory.onLost = onServerLost
        serverFactory.onData = onData

        clientFactory = protocol.ClientFactory()
        clientFactory.protocol = WritingProtocol
        clientFactory.onLost = onClientLost

        self.serverPort = reactor.listenSSL(0, serverFactory, serverCertOpts)
        self.clientConn = reactor.connectSSL(
            "127.0.0.1", self.serverPort.getHost().port, clientFactory, clientCertOpts
        )


class OpenSSLOptionsTests(OpenSSLOptionsTestsMixin, TestCase):
    """
    Tests for L{sslverify.OpenSSLOptions}.
    """

    def setUp(self):
        """
        Same as L{OpenSSLOptionsTestsMixin.setUp}, but it also patches
        L{sslverify._ChooseDiffieHellmanEllipticCurve}.
        """
        super().setUp()
        self.patch(
            sslverify,
            "_ChooseDiffieHellmanEllipticCurve",
            FakeChooseDiffieHellmanEllipticCurve,
        )

    def test_constructorWithOnlyPrivateKey(self):
        """
        C{privateKey} and C{certificate} make only sense if both are set.
        """
        self.assertRaises(
            ValueError, sslverify.OpenSSLCertificateOptions, privateKey=self.sKey
        )

    def test_constructorWithOnlyCertificate(self):
        """
        C{privateKey} and C{certificate} make only sense if both are set.
        """
        self.assertRaises(
            ValueError, sslverify.OpenSSLCertificateOptions, certificate=self.sCert
        )

    def test_constructorWithCertificateAndPrivateKey(self):
        """
        Specifying C{privateKey} and C{certificate} initializes correctly.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey, certificate=self.sCert
        )
        self.assertEqual(opts.privateKey, self.sKey)
        self.assertEqual(opts.certificate, self.sCert)
        self.assertEqual(opts.extraCertChain, [])

    def test_constructorDoesNotAllowVerifyWithoutCACerts(self):
        """
        C{verify} must not be C{True} without specifying C{caCerts}.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey,
            certificate=self.sCert,
            verify=True,
        )

    def test_constructorDoesNotAllowLegacyWithTrustRoot(self):
        """
        C{verify}, C{requireCertificate}, and C{caCerts} must not be specified
        by the caller (to be I{any} value, even the default!) when specifying
        C{trustRoot}.
        """
        self.assertRaises(
            TypeError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey,
            certificate=self.sCert,
            verify=True,
            trustRoot=None,
            caCerts=self.caCerts,
        )
        self.assertRaises(
            TypeError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey,
            certificate=self.sCert,
            trustRoot=None,
            requireCertificate=True,
        )

    def test_constructorAllowsCACertsWithoutVerify(self):
        """
        It's currently a NOP, but valid.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey, certificate=self.sCert, caCerts=self.caCerts
        )
        self.assertFalse(opts.verify)
        self.assertEqual(self.caCerts, opts.caCerts)

    def test_constructorWithVerifyAndCACerts(self):
        """
        Specifying C{verify} and C{caCerts} initializes correctly.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            verify=True,
            caCerts=self.caCerts,
        )
        self.assertTrue(opts.verify)
        self.assertEqual(self.caCerts, opts.caCerts)

    def test_constructorSetsExtraChain(self):
        """
        Setting C{extraCertChain} works if C{certificate} and C{privateKey} are
        set along with it.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            extraCertChain=self.extraCertChain,
        )
        self.assertEqual(self.extraCertChain, opts.extraCertChain)

    def test_constructorDoesNotAllowExtraChainWithoutPrivateKey(self):
        """
        A C{extraCertChain} without C{privateKey} doesn't make sense and is
        thus rejected.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions,
            certificate=self.sCert,
            extraCertChain=self.extraCertChain,
        )

    def test_constructorDoesNotAllowExtraChainWithOutPrivateKey(self):
        """
        A C{extraCertChain} without C{certificate} doesn't make sense and is
        thus rejected.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey,
            extraCertChain=self.extraCertChain,
        )

    def test_extraChainFilesAreAddedIfSupplied(self):
        """
        If C{extraCertChain} is set and all prerequisites are met, the
        specified chain certificates are added to C{Context}s that get
        created.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            extraCertChain=self.extraCertChain,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(self.sKey, ctx._privateKey)
        self.assertEqual(self.sCert, ctx._certificate)
        self.assertEqual(self.extraCertChain, ctx._extraCertChain)

    def test_extraChainDoesNotBreakPyOpenSSL(self):
        """
        C{extraCertChain} doesn't break C{OpenSSL.SSL.Context} creation.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            extraCertChain=self.extraCertChain,
        )
        ctx = opts.getContext()
        self.assertIsInstance(ctx, SSL.Context)

    def test_acceptableCiphersAreAlwaysSet(self):
        """
        If the user doesn't supply custom acceptable ciphers, a shipped secure
        default is used.  We can't check directly for it because the effective
        cipher string we set varies with platforms.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(opts._cipherString.encode("ascii"), ctx._cipherList)

    def test_givesMeaningfulErrorMessageIfNoCipherMatches(self):
        """
        If there is no valid cipher that matches the user's wishes,
        a L{ValueError} is raised.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey,
            certificate=self.sCert,
            acceptableCiphers=sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString(
                ""
            ),
        )

    def test_honorsAcceptableCiphersArgument(self):
        """
        If acceptable ciphers are passed, they are used.
        """

        @implementer(interfaces.IAcceptableCiphers)
        class FakeAcceptableCiphers:
            def selectCiphers(self, _):
                return [sslverify.OpenSSLCipher("sentinel")]

        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            acceptableCiphers=FakeAcceptableCiphers(),
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(b"sentinel", ctx._cipherList)

    def test_basicSecurityOptionsAreSet(self):
        """
        Every context must have C{OP_NO_SSLv2}, C{OP_NO_COMPRESSION}, and
        C{OP_CIPHER_SERVER_PREFERENCE} set.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2 | SSL.OP_NO_COMPRESSION | SSL.OP_CIPHER_SERVER_PREFERENCE
        )
        self.assertEqual(options, ctx._options & options)

    def test_modeIsSet(self):
        """
        Every context must be in C{MODE_RELEASE_BUFFERS} mode.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(SSL.MODE_RELEASE_BUFFERS, ctx._mode)

    def test_singleUseKeys(self):
        """
        If C{singleUseKeys} is set, every context must have
        C{OP_SINGLE_DH_USE} and C{OP_SINGLE_ECDH_USE} set.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            enableSingleUseKeys=True,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = SSL.OP_SINGLE_DH_USE | SSL.OP_SINGLE_ECDH_USE
        self.assertEqual(options, ctx._options & options)

    def test_methodIsDeprecated(self):
        """
        Passing C{method} to L{sslverify.OpenSSLCertificateOptions} is
        deprecated.
        """
        sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            method=SSL.SSLv23_METHOD,
        )

        message = (
            "Passing method to twisted.internet.ssl.CertificateOptions "
            "was deprecated in Twisted 17.1.0. Please use a "
            "combination of insecurelyLowerMinimumTo, raiseMinimumTo, "
            "and lowerMaximumSecurityTo instead, as Twisted will "
            "correctly configure the method."
        )

        warnings = self.flushWarnings([self.test_methodIsDeprecated])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]["category"])
        self.assertEqual(message, warnings[0]["message"])

    def test_tlsv12ByDefault(self):
        """
        L{sslverify.OpenSSLCertificateOptions} will make the default minimum
        TLS version v1.2, if no C{method}, or C{insecurelyLowerMinimumTo} is
        given.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey, certificate=self.sCert
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsAtLeastWithMinimum(self):
        """
        Passing C{insecurelyLowerMinimumTo} along with C{raiseMinimumTo} to
        L{sslverify.OpenSSLCertificateOptions} will cause it to raise an
        exception.
        """
        with self.assertRaises(TypeError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                raiseMinimumTo=sslverify.TLSVersion.TLSv1_2,
                insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_2,
            )

        self.assertIn("raiseMinimumTo", e.exception.args[0])
        self.assertIn("insecurelyLowerMinimumTo", e.exception.args[0])
        self.assertIn("exclusive", e.exception.args[0])

    def test_tlsProtocolsNoMethodWithAtLeast(self):
        """
        Passing C{raiseMinimumTo} along with C{method} to
        L{sslverify.OpenSSLCertificateOptions} will cause it to raise an
        exception.
        """
        with self.assertRaises(TypeError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                method=SSL.SSLv23_METHOD,
                raiseMinimumTo=sslverify.TLSVersion.TLSv1_2,
            )

        self.assertIn("method", e.exception.args[0])
        self.assertIn("raiseMinimumTo", e.exception.args[0])
        self.assertIn("exclusive", e.exception.args[0])

    def test_tlsProtocolsNoMethodWithMinimum(self):
        """
        Passing C{insecurelyLowerMinimumTo} along with C{method} to
        L{sslverify.OpenSSLCertificateOptions} will cause it to raise an
        exception.
        """
        with self.assertRaises(TypeError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                method=SSL.SSLv23_METHOD,
                insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_2,
            )

        self.assertIn("method", e.exception.args[0])
        self.assertIn("insecurelyLowerMinimumTo", e.exception.args[0])
        self.assertIn("exclusive", e.exception.args[0])

    def test_tlsProtocolsNoMethodWithMaximum(self):
        """
        Passing C{lowerMaximumSecurityTo} along with C{method} to
        L{sslverify.OpenSSLCertificateOptions} will cause it to raise an
        exception.
        """
        with self.assertRaises(TypeError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                method=SSL.TLS_METHOD,
                lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_2,
            )

        self.assertIn("method", e.exception.args[0])
        self.assertIn("lowerMaximumSecurityTo", e.exception.args[0])
        self.assertIn("exclusive", e.exception.args[0])

    def test_tlsVersionRangeInOrder(self):
        """
        Passing out of order TLS versions to C{insecurelyLowerMinimumTo} and
        C{lowerMaximumSecurityTo} will cause it to raise an exception.
        """
        with self.assertRaises(ValueError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_0,
                lowerMaximumSecurityTo=sslverify.TLSVersion.SSLv3,
            )

        self.assertEqual(
            e.exception.args,
            (
                (
                    "insecurelyLowerMinimumTo needs to be lower than "
                    "lowerMaximumSecurityTo"
                ),
            ),
        )

    def test_tlsVersionRangeInOrderAtLeast(self):
        """
        Passing out of order TLS versions to C{raiseMinimumTo} and
        C{lowerMaximumSecurityTo} will cause it to raise an exception.
        """
        with self.assertRaises(ValueError) as e:
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                raiseMinimumTo=sslverify.TLSVersion.TLSv1_0,
                lowerMaximumSecurityTo=sslverify.TLSVersion.SSLv3,
            )

        self.assertEqual(
            e.exception.args,
            (("raiseMinimumTo needs to be lower than " "lowerMaximumSecurityTo"),),
        )

    def test_tlsProtocolsreduceToMaxWithoutMin(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{lowerMaximumSecurityTo} but no C{raiseMinimumTo} or
        C{insecurelyLowerMinimumTo} set, and C{lowerMaximumSecurityTo} is
        below the minimum default, the minimum will be made the new maximum.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            lowerMaximumSecurityTo=sslverify.TLSVersion.SSLv3,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
            | SSL.OP_NO_TLSv1_2
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsSSLv3Only(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} and C{lowerMaximumSecurityTo} set to
        SSLv3, it will exclude all others.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.SSLv3,
            lowerMaximumSecurityTo=sslverify.TLSVersion.SSLv3,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
            | SSL.OP_NO_TLSv1_2
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsTLSv1Point0Only(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} and C{lowerMaximumSecurityTo} set to v1.0,
        it will exclude all others.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_0,
            lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_0,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1_1
            | SSL.OP_NO_TLSv1_2
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsTLSv1Point1Only(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} and C{lowerMaximumSecurityTo} set to v1.1,
        it will exclude all others.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_1,
            lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_1,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_2
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsTLSv1Point2Only(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} and C{lowerMaximumSecurityTo} set to v1.2,
        it will exclude all others.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_2,
            lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_2,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsAllModernTLS(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} set to TLSv1.0 and
        C{lowerMaximumSecurityTo} to TLSv1.2, it will exclude both SSLs and
        the (unreleased) TLSv1.3.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_0,
            lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_2,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | opts._OP_NO_TLSv1_3
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsAtLeastAllSecureTLS(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{raiseMinimumTo} set to TLSv1.2, it will ignore all TLSs below
        1.2 and SSL.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            raiseMinimumTo=sslverify.TLSVersion.TLSv1_2,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
        )
        self.assertEqual(options, ctx._options & options)

    def test_tlsProtocolsAtLeastWillAcceptHigherDefault(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{raiseMinimumTo} set to a value lower than Twisted's default will
        cause it to use the more secure default.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            raiseMinimumTo=sslverify.TLSVersion.SSLv3,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        # Future maintainer warning: this will break if we change our default
        # up, so you should change it to add the relevant OP_NO flags when we
        # do make that change and this test fails.
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
        )
        self.assertEqual(options, ctx._options & options)
        self.assertEqual(opts._defaultMinimumTLSVersion, sslverify.TLSVersion.TLSv1_2)

    def test_tlsProtocolsAllSecureTLS(self):
        """
        When calling L{sslverify.OpenSSLCertificateOptions} with
        C{insecurelyLowerMinimumTo} set to TLSv1.2, it will ignore all TLSs below
        1.2 and SSL.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            insecurelyLowerMinimumTo=sslverify.TLSVersion.TLSv1_2,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        options = (
            SSL.OP_NO_SSLv2
            | SSL.OP_NO_COMPRESSION
            | SSL.OP_CIPHER_SERVER_PREFERENCE
            | SSL.OP_NO_SSLv3
            | SSL.OP_NO_TLSv1
            | SSL.OP_NO_TLSv1_1
        )
        self.assertEqual(options, ctx._options & options)

    def test_dhParams(self):
        """
        If C{dhParams} is set, they are loaded into each new context.
        """

        class FakeDiffieHellmanParameters:
            _dhFile = FilePath(b"dh.params")

        dhParams = FakeDiffieHellmanParameters()
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            dhParameters=dhParams,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(FakeDiffieHellmanParameters._dhFile.path, ctx._dhFilename)

    def test_abbreviatingDistinguishedNames(self):
        """
        Check that abbreviations used in certificates correctly map to
        complete names.
        """
        self.assertEqual(
            sslverify.DN(CN=b"a", OU=b"hello"),
            sslverify.DistinguishedName(
                commonName=b"a", organizationalUnitName=b"hello"
            ),
        )
        self.assertNotEqual(
            sslverify.DN(CN=b"a", OU=b"hello"),
            sslverify.DN(CN=b"a", OU=b"hello", emailAddress=b"xxx"),
        )
        dn = sslverify.DN(CN=b"abcdefg")
        self.assertRaises(AttributeError, setattr, dn, "Cn", b"x")
        self.assertEqual(dn.CN, dn.commonName)
        dn.CN = b"bcdefga"
        self.assertEqual(dn.CN, dn.commonName)

    def testInspectDistinguishedName(self):
        n = sslverify.DN(
            commonName=b"common name",
            organizationName=b"organization name",
            organizationalUnitName=b"organizational unit name",
            localityName=b"locality name",
            stateOrProvinceName=b"state or province name",
            countryName=b"country name",
            emailAddress=b"email address",
        )
        s = n.inspect()
        for k in [
            "common name",
            "organization name",
            "organizational unit name",
            "locality name",
            "state or province name",
            "country name",
            "email address",
        ]:
            self.assertIn(k, s, f"{k!r} was not in inspect output.")
            self.assertIn(k.title(), s, f"{k!r} was not in inspect output.")

    def testInspectDistinguishedNameWithoutAllFields(self):
        n = sslverify.DN(localityName=b"locality name")
        s = n.inspect()
        for k in [
            "common name",
            "organization name",
            "organizational unit name",
            "state or province name",
            "country name",
            "email address",
        ]:
            self.assertNotIn(k, s, f"{k!r} was in inspect output.")
            self.assertNotIn(k.title(), s, f"{k!r} was in inspect output.")
        self.assertIn("locality name", s)
        self.assertIn("Locality Name", s)

    def test_inspectCertificate(self):
        """
        Test that the C{inspect} method of L{sslverify.Certificate} returns
        a human-readable string containing some basic information about the
        certificate.
        """
        c = sslverify.Certificate.loadPEM(A_HOST_CERTIFICATE_PEM)
        pk = c.getPublicKey()
        keyHash = pk.keyHash()
        # Maintenance Note: the algorithm used to compute the "public key hash"
        # is highly dubious and can differ between underlying versions of
        # OpenSSL (and across versions of Twisted), since it is not actually
        # the hash of the public key by itself.  If we can get the appropriate
        # APIs to get the hash of the key itself out of OpenSSL, then we should
        # be able to make it statically declared inline below again rather than
        # computing it here.
        self.assertEqual(
            c.inspect().split("\n"),
            [
                "Certificate For Subject:",
                "               Common Name: example.twistedmatrix.com",
                "              Country Name: US",
                "             Email Address: nobody@twistedmatrix.com",
                "             Locality Name: Boston",
                "         Organization Name: Twisted Matrix Labs",
                "  Organizational Unit Name: Security",
                "    State Or Province Name: Massachusetts",
                "",
                "Issuer:",
                "               Common Name: example.twistedmatrix.com",
                "              Country Name: US",
                "             Email Address: nobody@twistedmatrix.com",
                "             Locality Name: Boston",
                "         Organization Name: Twisted Matrix Labs",
                "  Organizational Unit Name: Security",
                "    State Or Province Name: Massachusetts",
                "",
                "Serial Number: 12345",
                "Digest: C4:96:11:00:30:C3:EC:EE:A3:55:AA:ED:8C:84:85:18",
                "Public Key with Hash: " + keyHash,
            ],
        )

    def test_publicKeyMatching(self):
        """
        L{PublicKey.matches} returns L{True} for keys from certificates with
        the same key, and L{False} for keys from certificates with different
        keys.
        """
        hostA = sslverify.Certificate.loadPEM(A_HOST_CERTIFICATE_PEM)
        hostB = sslverify.Certificate.loadPEM(A_HOST_CERTIFICATE_PEM)
        peerA = sslverify.Certificate.loadPEM(A_PEER_CERTIFICATE_PEM)

        self.assertTrue(hostA.getPublicKey().matches(hostB.getPublicKey()))
        self.assertFalse(peerA.getPublicKey().matches(hostA.getPublicKey()))

    def test_enablingAndDisablingSessions(self):
        """
        The enableSessions argument sets the session cache mode; it defaults to
        False (at least until https://twistedmatrix.com/trac/ticket/9764 can be
        resolved).
        """
        options = sslverify.OpenSSLCertificateOptions()
        self.assertEqual(options.enableSessions, False)
        ctx = options.getContext()
        self.assertEqual(ctx.get_session_cache_mode(), SSL.SESS_CACHE_OFF)
        options = sslverify.OpenSSLCertificateOptions(enableSessions=True)
        self.assertEqual(options.enableSessions, True)
        ctx = options.getContext()
        self.assertEqual(ctx.get_session_cache_mode(), SSL.SESS_CACHE_SERVER)

    def test_certificateOptionsSerialization(self):
        """
        Test that __setstate__(__getstate__()) round-trips properly.
        """
        firstOpts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            method=SSL.SSLv23_METHOD,
            verify=True,
            caCerts=[self.sCert],
            verifyDepth=2,
            requireCertificate=False,
            verifyOnce=False,
            enableSingleUseKeys=False,
            enableSessions=False,
            fixBrokenPeers=True,
            enableSessionTickets=True,
        )
        context = firstOpts.getContext()
        self.assertIs(context, firstOpts._context)
        self.assertIsNotNone(context)
        state = firstOpts.__getstate__()
        self.assertNotIn("_context", state)

        opts = sslverify.OpenSSLCertificateOptions()
        opts.__setstate__(state)
        self.assertEqual(opts.privateKey, self.sKey)
        self.assertEqual(opts.certificate, self.sCert)
        self.assertEqual(opts.method, SSL.SSLv23_METHOD)
        self.assertTrue(opts.verify)
        self.assertEqual(opts.caCerts, [self.sCert])
        self.assertEqual(opts.verifyDepth, 2)
        self.assertFalse(opts.requireCertificate)
        self.assertFalse(opts.verifyOnce)
        self.assertFalse(opts.enableSingleUseKeys)
        self.assertFalse(opts.enableSessions)
        self.assertTrue(opts.fixBrokenPeers)
        self.assertTrue(opts.enableSessionTickets)

    test_certificateOptionsSerialization.suppress = [  # type: ignore[attr-defined]
        util.suppress(
            category=DeprecationWarning,
            message=r"twisted\.internet\._sslverify\.*__[gs]etstate__",
        )
    ]

    def test_certificateOptionsSessionTickets(self):
        """
        Enabling session tickets should not set the OP_NO_TICKET option.
        """
        opts = sslverify.OpenSSLCertificateOptions(enableSessionTickets=True)
        ctx = opts.getContext()
        self.assertEqual(0, ctx.set_options(0) & 0x00004000)

    def test_certificateOptionsSessionTicketsDisabled(self):
        """
        Enabling session tickets should set the OP_NO_TICKET option.
        """
        opts = sslverify.OpenSSLCertificateOptions(enableSessionTickets=False)
        ctx = opts.getContext()
        self.assertEqual(0x00004000, ctx.set_options(0) & 0x00004000)

    def test_allowedAnonymousClientConnection(self):
        """
        Check that anonymous connections are allowed when certificates aren't
        required on the server.
        """
        onData = defer.Deferred()
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey, certificate=self.sCert, requireCertificate=False
            ),
            sslverify.OpenSSLCertificateOptions(requireCertificate=False),
            onData=onData,
        )

        return onData.addCallback(
            lambda result: self.assertEqual(result, WritingProtocol.byte)
        )

    def test_refusedAnonymousClientConnection(self):
        """
        Check that anonymous connections are refused when certificates are
        required on the server.
        """
        onServerLost = defer.Deferred()
        onClientLost = defer.Deferred()
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                verify=True,
                caCerts=[self.sCert],
                requireCertificate=True,
            ),
            sslverify.OpenSSLCertificateOptions(requireCertificate=False),
            onServerLost=onServerLost,
            onClientLost=onClientLost,
        )

        d = defer.DeferredList([onClientLost, onServerLost], consumeErrors=True)

        def afterLost(result):
            ((cSuccess, cResult), (sSuccess, sResult)) = result
            self.assertFalse(cSuccess)
            self.assertFalse(sSuccess)
            # Win32 fails to report the SSL Error, and report a connection lost
            # instead: there is a race condition so that's not totally
            # surprising (see ticket #2877 in the tracker)
            self.assertIsInstance(cResult.value, (SSL.Error, ConnectionLost))
            self.assertIsInstance(sResult.value, SSL.Error)

        return d.addCallback(afterLost)

    def test_failedCertificateVerification(self):
        """
        Check that connecting with a certificate not accepted by the server CA
        fails.
        """
        onServerLost = defer.Deferred()
        onClientLost = defer.Deferred()
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                verify=False,
                requireCertificate=False,
            ),
            sslverify.OpenSSLCertificateOptions(
                verify=True, requireCertificate=False, caCerts=[self.cCert]
            ),
            onServerLost=onServerLost,
            onClientLost=onClientLost,
        )

        d = defer.DeferredList([onClientLost, onServerLost], consumeErrors=True)

        def afterLost(result):
            ((cSuccess, cResult), (sSuccess, sResult)) = result
            self.assertFalse(cSuccess)
            self.assertFalse(sSuccess)

        return d.addCallback(afterLost)

    def test_successfulCertificateVerification(self):
        """
        Test a successful connection with client certificate validation on
        server side.
        """
        onData = defer.Deferred()
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                verify=False,
                requireCertificate=False,
            ),
            sslverify.OpenSSLCertificateOptions(
                verify=True, requireCertificate=True, caCerts=[self.sCert]
            ),
            onData=onData,
        )

        return onData.addCallback(
            lambda result: self.assertEqual(result, WritingProtocol.byte)
        )

    def test_successfulSymmetricSelfSignedCertificateVerification(self):
        """
        Test a successful connection with validation on both server and client
        sides.
        """
        onData = defer.Deferred()
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                verify=True,
                requireCertificate=True,
                caCerts=[self.cCert],
            ),
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.cKey,
                certificate=self.cCert,
                verify=True,
                requireCertificate=True,
                caCerts=[self.sCert],
            ),
            onData=onData,
        )

        return onData.addCallback(
            lambda result: self.assertEqual(result, WritingProtocol.byte)
        )

    def test_verification(self):
        """
        Check certificates verification building custom certificates data.
        """
        clientDN = sslverify.DistinguishedName(commonName="client")
        clientKey = sslverify.KeyPair.generate()
        clientCertReq = clientKey.certificateRequest(clientDN)

        serverDN = sslverify.DistinguishedName(commonName="server")
        serverKey = sslverify.KeyPair.generate()
        serverCertReq = serverKey.certificateRequest(serverDN)

        clientSelfCertReq = clientKey.certificateRequest(clientDN)
        clientSelfCertData = clientKey.signCertificateRequest(
            clientDN, clientSelfCertReq, lambda dn: True, 132
        )
        clientSelfCert = clientKey.newCertificate(clientSelfCertData)

        serverSelfCertReq = serverKey.certificateRequest(serverDN)
        serverSelfCertData = serverKey.signCertificateRequest(
            serverDN, serverSelfCertReq, lambda dn: True, 516
        )
        serverSelfCert = serverKey.newCertificate(serverSelfCertData)

        clientCertData = serverKey.signCertificateRequest(
            serverDN, clientCertReq, lambda dn: True, 7
        )
        clientCert = clientKey.newCertificate(clientCertData)

        serverCertData = clientKey.signCertificateRequest(
            clientDN, serverCertReq, lambda dn: True, 42
        )
        serverCert = serverKey.newCertificate(serverCertData)

        onData = defer.Deferred()

        serverOpts = serverCert.options(serverSelfCert)
        clientOpts = clientCert.options(clientSelfCert)

        self.loopback(serverOpts, clientOpts, onData=onData)

        return onData.addCallback(
            lambda result: self.assertEqual(result, WritingProtocol.byte)
        )


class OpenSSLOptionsECDHIntegrationTests(OpenSSLOptionsTestsMixin, TestCase):
    """
    ECDH-related integration tests for L{OpenSSLOptions}.
    """

    def test_ellipticCurveDiffieHellman(self):
        """
        Connections use ECDH when OpenSSL supports it.
        """
        if not get_elliptic_curves():
            raise SkipTest("OpenSSL does not support ECDH.")

        onData = defer.Deferred()
        # TLS 1.3 cipher suites do not specify the key exchange
        # mechanism:
        # https://wiki.openssl.org/index.php/TLS1.3#Differences_with_TLS1.2_and_below
        #
        # and OpenSSL only supports ECHDE groups with TLS 1.3:
        # https://wiki.openssl.org/index.php/TLS1.3#Groups
        #
        # so TLS 1.3 implies ECDHE.  Force this test to use TLS 1.3 to
        # ensure ECDH is selected when it might not be.
        self.loopback(
            sslverify.OpenSSLCertificateOptions(
                privateKey=self.sKey,
                certificate=self.sCert,
                requireCertificate=False,
                lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_3,
            ),
            sslverify.OpenSSLCertificateOptions(
                requireCertificate=False,
                lowerMaximumSecurityTo=sslverify.TLSVersion.TLSv1_3,
            ),
            onData=onData,
        )

        @onData.addCallback
        def assertECDH(_):
            self.assertEqual(len(self.clientConn.factory.protocols), 1)
            [clientProtocol] = self.clientConn.factory.protocols
            cipher = clientProtocol.getHandle().get_cipher_name()
            self.assertIn("ECDH", cipher)

        return onData


class DeprecationTests(SynchronousTestCase):
    """
    Tests for deprecation of L{sslverify.OpenSSLCertificateOptions}'s support
    of the pickle protocol.
    """

    if skipSSL:
        skip = skipSSL

    def test_getstateDeprecation(self):
        """
        L{sslverify.OpenSSLCertificateOptions.__getstate__} is deprecated.
        """
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.OpenSSLCertificateOptions().__getstate__,
        )

    def test_setstateDeprecation(self):
        """
        L{sslverify.OpenSSLCertificateOptions.__setstate__} is deprecated.
        """
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.OpenSSLCertificateOptions().__setstate__,
            {},
        )


class TrustRootTests(TestCase):
    """
    Tests for L{sslverify.OpenSSLCertificateOptions}' C{trustRoot} argument,
    L{sslverify.platformTrust}, and their interactions.
    """

    if skipSSL:
        skip = skipSSL

    def setUp(self):
        """
        Patch L{sslverify._ChooseDiffieHellmanEllipticCurve}.
        """
        self.patch(
            sslverify,
            "_ChooseDiffieHellmanEllipticCurve",
            FakeChooseDiffieHellmanEllipticCurve,
        )

    def test_caCertsPlatformDefaults(self):
        """
        Specifying a C{trustRoot} of L{sslverify.OpenSSLDefaultPaths} when
        initializing L{sslverify.OpenSSLCertificateOptions} loads the
        platform-provided trusted certificates via C{set_default_verify_paths}.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            trustRoot=sslverify.OpenSSLDefaultPaths(),
        )
        fc = FakeContext(SSL.TLSv1_METHOD)
        opts._contextFactory = lambda method: fc
        opts.getContext()
        self.assertTrue(fc._defaultVerifyPathsSet)

    def test_trustRootPlatformRejectsUntrustedCA(self):
        """
        Specifying a C{trustRoot} of L{platformTrust} when initializing
        L{sslverify.OpenSSLCertificateOptions} causes certificates issued by a
        newly created CA to be rejected by an SSL connection using these
        options.

        Note that this test should I{always} pass, even on platforms where the
        CA certificates are not installed, as long as L{platformTrust} rejects
        completely invalid / unknown root CA certificates.  This is simply a
        smoke test to make sure that verification is happening at all.
        """
        caSelfCert, serverCert = certificatesForAuthorityAndServer()
        chainedCert = pathContainingDumpOf(self, serverCert, caSelfCert)
        privateKey = pathContainingDumpOf(self, serverCert.privateKey)

        sProto, cProto, sWrapped, cWrapped, pump = loopbackTLSConnection(
            trustRoot=platformTrust(),
            privateKeyFile=privateKey,
            chainedCertFile=chainedCert,
        )
        # No data was received.
        self.assertEqual(cWrapped.data, b"")

        # It was an L{SSL.Error}.
        self.assertEqual(cWrapped.lostReason.type, SSL.Error)

        # Some combination of OpenSSL and PyOpenSSL is bad at reporting errors.
        err = cWrapped.lostReason.value
        self.assertEqual(err.args[0][0][2], "tlsv1 alert unknown ca")

    def test_trustRootSpecificCertificate(self):
        """
        Specifying a L{Certificate} object for L{trustRoot} will result in that
        certificate being the only trust root for a client.
        """
        caCert, serverCert = certificatesForAuthorityAndServer()
        otherCa, otherServer = certificatesForAuthorityAndServer()
        sProto, cProto, sWrapped, cWrapped, pump = loopbackTLSConnection(
            trustRoot=caCert,
            privateKeyFile=pathContainingDumpOf(self, serverCert.privateKey),
            chainedCertFile=pathContainingDumpOf(self, serverCert),
        )
        pump.flush()
        self.assertIsNone(cWrapped.lostReason)
        self.assertEqual(cWrapped.data, sWrapped.greeting)


class ServiceIdentityTests(SynchronousTestCase):
    """
    Tests for the verification of the peer's service's identity via the
    C{hostname} argument to L{sslverify.OpenSSLCertificateOptions}.
    """

    if skipSSL:
        skip = skipSSL

    def serviceIdentitySetup(
        self,
        clientHostname,
        serverHostname,
        serverContextSetup=lambda ctx: None,
        validCertificate=True,
        clientPresentsCertificate=False,
        validClientCertificate=True,
        serverVerifies=False,
        buggyInfoCallback=False,
        fakePlatformTrust=False,
        useDefaultTrust=False,
    ):
        """
        Connect a server and a client.

        @param clientHostname: The I{client's idea} of the server's hostname;
            passed as the C{hostname} to the
            L{sslverify.OpenSSLCertificateOptions} instance.
        @type clientHostname: L{unicode}

        @param serverHostname: The I{server's own idea} of the server's
            hostname; present in the certificate presented by the server.
        @type serverHostname: L{unicode}

        @param serverContextSetup: a 1-argument callable invoked with the
            L{OpenSSL.SSL.Context} after it's produced.
        @type serverContextSetup: L{callable} taking L{OpenSSL.SSL.Context}
            returning L{None}.

        @param validCertificate: Is the server's certificate valid?  L{True} if
            so, L{False} otherwise.
        @type validCertificate: L{bool}

        @param clientPresentsCertificate: Should the client present a
            certificate to the server?  Defaults to 'no'.
        @type clientPresentsCertificate: L{bool}

        @param validClientCertificate: If the client presents a certificate,
            should it actually be a valid one, i.e. signed by the same CA that
            the server is checking?  Defaults to 'yes'.
        @type validClientCertificate: L{bool}

        @param serverVerifies: Should the server verify the client's
            certificate?  Defaults to 'no'.
        @type serverVerifies: L{bool}

        @param buggyInfoCallback: Should we patch the implementation so that
            the C{info_callback} passed to OpenSSL to have a bug and raise an
            exception (L{ZeroDivisionError})?  Defaults to 'no'.
        @type buggyInfoCallback: L{bool}

        @param fakePlatformTrust: Should we fake the platformTrust to be the
            same as our fake server certificate authority, so that we can test
            it's being used?  Defaults to 'no' and we just pass platform trust.
        @type fakePlatformTrust: L{bool}

        @param useDefaultTrust: Should we avoid passing the C{trustRoot} to
            L{ssl.optionsForClientTLS}?  Defaults to 'no'.
        @type useDefaultTrust: L{bool}

        @return: the client TLS protocol, the client wrapped protocol,
            the server TLS protocol, the server wrapped protocol and
            an L{IOPump} which, when its C{pump} and C{flush} methods are
            called, will move data between the created client and server
            protocol instances
        @rtype: 5-L{tuple} of 4 L{IProtocol}s and L{IOPump}
        """
        serverCA, serverCert = certificatesForAuthorityAndServer(serverHostname)
        other = {}
        passClientCert = None
        clientCA, clientCert = certificatesForAuthorityAndServer("client")
        if serverVerifies:
            other.update(trustRoot=clientCA)

        if clientPresentsCertificate:
            if validClientCertificate:
                passClientCert = clientCert
            else:
                bogusCA, bogus = certificatesForAuthorityAndServer("client")
                passClientCert = bogus

        serverOpts = sslverify.OpenSSLCertificateOptions(
            privateKey=serverCert.privateKey.original,
            certificate=serverCert.original,
            **other,
        )
        serverContextSetup(serverOpts.getContext())
        if not validCertificate:
            serverCA, otherServer = certificatesForAuthorityAndServer(serverHostname)
        if buggyInfoCallback:

            def broken(*a, **k):
                """
                Raise an exception.

                @param a: Arguments for an C{info_callback}

                @param k: Keyword arguments for an C{info_callback}
                """
                1 / 0

            self.patch(
                sslverify.ClientTLSOptions,
                "_identityVerifyingInfoCallback",
                broken,
            )

        signature = {"hostname": clientHostname}
        if passClientCert:
            signature.update(clientCertificate=passClientCert)
        if not useDefaultTrust:
            signature.update(trustRoot=serverCA)
        if fakePlatformTrust:
            self.patch(sslverify, "platformTrust", lambda: serverCA)

        clientOpts = sslverify.optionsForClientTLS(**signature)

        class GreetingServer(protocol.Protocol):
            greeting = b"greetings!"
            lostReason = None
            data = b""

            def connectionMade(self):
                self.transport.write(self.greeting)

            def dataReceived(self, data):
                self.data += data

            def connectionLost(self, reason):
                self.lostReason = reason

        class GreetingClient(protocol.Protocol):
            greeting = b"cheerio!"
            data = b""
            lostReason = None

            def connectionMade(self):
                self.transport.write(self.greeting)

            def dataReceived(self, data):
                self.data += data

            def connectionLost(self, reason):
                self.lostReason = reason

        serverWrappedProto = GreetingServer()
        clientWrappedProto = GreetingClient()

        clientFactory = protocol.Factory()
        clientFactory.protocol = lambda: clientWrappedProto
        serverFactory = protocol.Factory()
        serverFactory.protocol = lambda: serverWrappedProto

        self.serverOpts = serverOpts
        self.clientOpts = clientOpts

        clientTLSFactory = TLSMemoryBIOFactory(
            clientOpts, isClient=True, wrappedFactory=clientFactory
        )
        serverTLSFactory = TLSMemoryBIOFactory(
            serverOpts, isClient=False, wrappedFactory=serverFactory
        )

        cProto, sProto, pump = connectedServerAndClient(
            lambda: serverTLSFactory.buildProtocol(None),
            lambda: clientTLSFactory.buildProtocol(None),
        )
        return cProto, sProto, clientWrappedProto, serverWrappedProto, pump

    def test_invalidHostname(self):
        """
        When a certificate containing an invalid hostname is received from the
        server, the connection is immediately dropped.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "wrong-host.example.com",
            "correct-host.example.com",
        )
        self.assertEqual(cWrapped.data, b"")
        self.assertEqual(sWrapped.data, b"")

        cErr = cWrapped.lostReason.value
        sErr = sWrapped.lostReason.value

        self.assertIsInstance(cErr, VerificationError)
        self.assertIsInstance(sErr, ConnectionClosed)

    def test_validHostname(self):
        """
        Whenever a valid certificate containing a valid hostname is received,
        connection proceeds normally.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
        )
        self.assertEqual(cWrapped.data, b"greetings!")

        cErr = cWrapped.lostReason
        sErr = sWrapped.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)

    def test_validHostnameInvalidCertificate(self):
        """
        When an invalid certificate containing a perfectly valid hostname is
        received, the connection is aborted with an OpenSSL error.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
            validCertificate=False,
        )

        self.assertEqual(cWrapped.data, b"")
        self.assertEqual(sWrapped.data, b"")

        cErr = cWrapped.lostReason.value
        sErr = sWrapped.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)

    def test_realCAsBetterNotSignOurBogusTestCerts(self):
        """
        If we use the default trust from the platform, our dinky certificate
        should I{really} fail.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
            validCertificate=False,
            useDefaultTrust=True,
        )

        self.assertEqual(cWrapped.data, b"")
        self.assertEqual(sWrapped.data, b"")

        cErr = cWrapped.lostReason.value
        sErr = sWrapped.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)

    def test_butIfTheyDidItWouldWork(self):
        """
        L{ssl.optionsForClientTLS} should be using L{ssl.platformTrust} by
        default, so if we fake that out then it should trust ourselves again.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
            useDefaultTrust=True,
            fakePlatformTrust=True,
        )
        self.assertEqual(cWrapped.data, b"greetings!")

        cErr = cWrapped.lostReason
        sErr = sWrapped.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)

    def test_clientPresentsCertificate(self):
        """
        When the server verifies and the client presents a valid certificate
        for that verification by passing it to
        L{sslverify.optionsForClientTLS}, communication proceeds.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
            validCertificate=True,
            serverVerifies=True,
            clientPresentsCertificate=True,
        )

        self.assertEqual(cWrapped.data, b"greetings!")

        cErr = cWrapped.lostReason
        sErr = sWrapped.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)

    def test_clientPresentsBadCertificate(self):
        """
        When the server verifies and the client presents an invalid certificate
        for that verification by passing it to
        L{sslverify.optionsForClientTLS}, the connection cannot be established
        with an SSL error.
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com",
            "valid.example.com",
            validCertificate=True,
            serverVerifies=True,
            validClientCertificate=False,
            clientPresentsCertificate=True,
        )

        self.assertEqual(cWrapped.data, b"")

        cErr = cWrapped.lostReason.value
        sErr = sWrapped.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)

    @skipIf(skipSNI, skipSNI)
    def test_hostnameIsIndicated(self):
        """
        Specifying the C{hostname} argument to L{CertificateOptions} also sets
        the U{Server Name Extension
        <https://en.wikipedia.org/wiki/Server_Name_Indication>} TLS indication
        field to the correct value.
        """
        names = []

        def setupServerContext(ctx):
            def servername_received(conn):
                names.append(conn.get_servername().decode("ascii"))

            ctx.set_tlsext_servername_callback(servername_received)

        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "valid.example.com", "valid.example.com", setupServerContext
        )
        self.assertEqual(names, ["valid.example.com"])

    @skipIf(skipSNI, skipSNI)
    def test_hostnameEncoding(self):
        """
        Hostnames are encoded as IDNA.
        """
        names = []
        hello = "h\N{LATIN SMALL LETTER A WITH ACUTE}llo.example.com"

        def setupServerContext(ctx):
            def servername_received(conn):
                serverIDNA = _idnaText(conn.get_servername())
                names.append(serverIDNA)

            ctx.set_tlsext_servername_callback(servername_received)

        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            hello, hello, setupServerContext
        )
        self.assertEqual(names, [hello])
        self.assertEqual(cWrapped.data, b"greetings!")

        cErr = cWrapped.lostReason
        sErr = sWrapped.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)

    def test_fallback(self):
        """
        L{sslverify.simpleVerifyHostname} checks string equality on the
        commonName of a connection's certificate's subject, doing nothing if it
        matches and raising L{VerificationError} if it doesn't.
        """
        name = "something.example.com"

        class Connection:
            def get_peer_certificate(self):
                """
                Fake of L{OpenSSL.SSL.Connection.get_peer_certificate}.

                @return: A certificate with a known common name.
                @rtype: L{OpenSSL.crypto.X509}
                """
                cert = X509()
                cert.get_subject().commonName = name
                return cert

        conn = Connection()
        self.assertIs(
            sslverify.simpleVerifyHostname(conn, "something.example.com"), None
        )
        self.assertRaises(
            sslverify.SimpleVerificationError,
            sslverify.simpleVerifyHostname,
            conn,
            "nonsense",
        )

    def test_surpriseFromInfoCallback(self):
        """
        pyOpenSSL isn't always so great about reporting errors.  If one occurs
        in the verification info callback, it should be logged and the
        connection should be shut down (if possible, anyway; the app_data could
        be clobbered but there's no point testing for that).
        """
        cProto, sProto, cWrapped, sWrapped, pump = self.serviceIdentitySetup(
            "correct-host.example.com",
            "correct-host.example.com",
            buggyInfoCallback=True,
        )

        self.assertEqual(cWrapped.data, b"")
        self.assertEqual(sWrapped.data, b"")

        cErr = cWrapped.lostReason.value
        sErr = sWrapped.lostReason.value

        self.assertIsInstance(cErr, ZeroDivisionError)
        self.assertIsInstance(sErr, (ConnectionClosed, SSL.Error))
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertTrue(errors)


def negotiateProtocol(serverProtocols, clientProtocols, clientOptions=None):
    """
    Create the TLS connection and negotiate a next protocol.

    @param serverProtocols: The protocols the server is willing to negotiate.
    @param clientProtocols: The protocols the client is willing to negotiate.
    @param clientOptions: The type of C{OpenSSLCertificateOptions} class to
        use for the client. Defaults to C{OpenSSLCertificateOptions}.
    @return: A L{tuple} of the negotiated protocol and the reason the
        connection was lost.
    """
    caCertificate, serverCertificate = certificatesForAuthorityAndServer()
    trustRoot = sslverify.OpenSSLCertificateAuthorities(
        [
            caCertificate.original,
        ]
    )

    sProto, cProto, sWrapped, cWrapped, pump = loopbackTLSConnectionInMemory(
        trustRoot=trustRoot,
        privateKey=serverCertificate.privateKey.original,
        serverCertificate=serverCertificate.original,
        clientProtocols=clientProtocols,
        serverProtocols=serverProtocols,
        clientOptions=clientOptions,
    )
    pump.flush()

    return (cProto.negotiatedProtocol, cWrapped.lostReason)


class NPNOrALPNTests(TestCase):
    """
    NPN and ALPN protocol selection.

    These tests only run on platforms that have a PyOpenSSL version >= 0.15,
    and OpenSSL version 1.0.1 or later.
    """

    if skipSSL:
        skip = skipSSL
    elif skipNPN:
        skip = skipNPN

    def test_nextProtocolMechanismsNPNIsSupported(self):
        """
        When at least NPN is available on the platform, NPN is in the set of
        supported negotiation protocols.
        """
        supportedProtocols = sslverify.protocolNegotiationMechanisms()
        self.assertTrue(sslverify.ProtocolNegotiationSupport.NPN in supportedProtocols)

    def test_NPNAndALPNSuccess(self):
        """
        When both ALPN and NPN are used, and both the client and server have
        overlapping protocol choices, a protocol is successfully negotiated.
        Further, the negotiated protocol is the first one in the list.
        """
        protocols = [b"h2", b"http/1.1"]
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=protocols,
            serverProtocols=protocols,
        )
        self.assertEqual(negotiatedProtocol, b"h2")
        self.assertIsNone(lostReason)

    def test_NPNAndALPNDifferent(self):
        """
        Client and server have different protocol lists: only the common
        element is chosen.
        """
        serverProtocols = [b"h2", b"http/1.1", b"spdy/2"]
        clientProtocols = [b"spdy/3", b"http/1.1"]
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=clientProtocols,
            serverProtocols=serverProtocols,
        )
        self.assertEqual(negotiatedProtocol, b"http/1.1")
        self.assertIsNone(lostReason)

    def test_NPNAndALPNNoAdvertise(self):
        """
        When one peer does not advertise any protocols, the connection is set
        up with no next protocol.
        """
        protocols = [b"h2", b"http/1.1"]
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=protocols,
            serverProtocols=[],
        )
        self.assertIsNone(negotiatedProtocol)
        self.assertIsNone(lostReason)

    def test_NPNAndALPNNoOverlap(self):
        """
        When the client and server have no overlap of protocols, the connection
        fails.
        """
        clientProtocols = [b"h2", b"http/1.1"]
        serverProtocols = [b"spdy/3"]
        negotiatedProtocol, lostReason = negotiateProtocol(
            serverProtocols=clientProtocols,
            clientProtocols=serverProtocols,
        )
        self.assertIsNone(negotiatedProtocol)
        self.assertEqual(lostReason.type, SSL.Error)


class ALPNTests(TestCase):
    """
    ALPN protocol selection.

    These tests only run on platforms that have a PyOpenSSL version >= 0.15,
    and OpenSSL version 1.0.2 or later.

    This covers only the ALPN specific logic, as any platform that has ALPN
    will also have NPN and so will run the NPNAndALPNTest suite as well.
    """

    if skipSSL:
        skip = skipSSL
    elif skipALPN:
        skip = skipALPN

    def test_nextProtocolMechanismsALPNIsSupported(self):
        """
        When ALPN is available on a platform, protocolNegotiationMechanisms
        includes ALPN in the suported protocols.
        """
        supportedProtocols = sslverify.protocolNegotiationMechanisms()
        self.assertTrue(sslverify.ProtocolNegotiationSupport.ALPN in supportedProtocols)


class NPNAndALPNAbsentTests(TestCase):
    """
    NPN/ALPN operations fail on platforms that do not support them.

    These tests only run on platforms that have a PyOpenSSL version < 0.15,
    an OpenSSL version earlier than 1.0.1, or an OpenSSL/cryptography built
    without NPN support.
    """

    if skipSSL:
        skip = skipSSL
    elif not skipNPN or not skipALPN:
        skip = "NPN and/or ALPN is present on this platform"

    def test_nextProtocolMechanismsNoNegotiationSupported(self):
        """
        When neither NPN or ALPN are available on a platform, there are no
        supported negotiation protocols.
        """
        supportedProtocols = sslverify.protocolNegotiationMechanisms()
        self.assertFalse(supportedProtocols)

    def test_NPNAndALPNNotImplemented(self):
        """
        A NotImplementedError is raised when using acceptableProtocols on a
        platform that does not support either NPN or ALPN.
        """
        protocols = [b"h2", b"http/1.1"]
        self.assertRaises(
            NotImplementedError,
            negotiateProtocol,
            serverProtocols=protocols,
            clientProtocols=protocols,
        )

    def test_NegotiatedProtocolReturnsNone(self):
        """
        negotiatedProtocol return L{None} even when NPN/ALPN aren't supported.
        This works because, as neither are supported, negotiation isn't even
        attempted.
        """
        serverProtocols = None
        clientProtocols = None
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=clientProtocols,
            serverProtocols=serverProtocols,
        )
        self.assertIsNone(negotiatedProtocol)
        self.assertIsNone(lostReason)


class _NotSSLTransport:
    def getHandle(self):
        return self


class _MaybeSSLTransport:
    def getHandle(self):
        return self

    def get_peer_certificate(self):
        return None

    def get_host_certificate(self):
        return None


class _ActualSSLTransport:
    def getHandle(self):
        return self

    def get_host_certificate(self):
        return sslverify.Certificate.loadPEM(A_HOST_CERTIFICATE_PEM).original

    def get_peer_certificate(self):
        return sslverify.Certificate.loadPEM(A_PEER_CERTIFICATE_PEM).original


class ConstructorsTests(TestCase):
    if skipSSL:
        skip = skipSSL

    def test_peerFromNonSSLTransport(self):
        """
        Verify that peerFromTransport raises an exception if the transport
        passed is not actually an SSL transport.
        """
        x = self.assertRaises(
            CertificateError,
            sslverify.Certificate.peerFromTransport,
            _NotSSLTransport(),
        )
        self.assertTrue(str(x).startswith("non-TLS"))

    def test_peerFromBlankSSLTransport(self):
        """
        Verify that peerFromTransport raises an exception if the transport
        passed is an SSL transport, but doesn't have a peer certificate.
        """
        x = self.assertRaises(
            CertificateError,
            sslverify.Certificate.peerFromTransport,
            _MaybeSSLTransport(),
        )
        self.assertTrue(str(x).startswith("TLS"))

    def test_hostFromNonSSLTransport(self):
        """
        Verify that hostFromTransport raises an exception if the transport
        passed is not actually an SSL transport.
        """
        x = self.assertRaises(
            CertificateError,
            sslverify.Certificate.hostFromTransport,
            _NotSSLTransport(),
        )
        self.assertTrue(str(x).startswith("non-TLS"))

    def test_hostFromBlankSSLTransport(self):
        """
        Verify that hostFromTransport raises an exception if the transport
        passed is an SSL transport, but doesn't have a host certificate.
        """
        x = self.assertRaises(
            CertificateError,
            sslverify.Certificate.hostFromTransport,
            _MaybeSSLTransport(),
        )
        self.assertTrue(str(x).startswith("TLS"))

    def test_hostFromSSLTransport(self):
        """
        Verify that hostFromTransport successfully creates the correct
        certificate if passed a valid SSL transport.
        """
        self.assertEqual(
            sslverify.Certificate.hostFromTransport(
                _ActualSSLTransport()
            ).serialNumber(),
            12345,
        )

    def test_peerFromSSLTransport(self):
        """
        Verify that peerFromTransport successfully creates the correct
        certificate if passed a valid SSL transport.
        """
        self.assertEqual(
            sslverify.Certificate.peerFromTransport(
                _ActualSSLTransport()
            ).serialNumber(),
            12346,
        )


class MultipleCertificateTrustRootTests(TestCase):
    """
    Test the behavior of the trustRootFromCertificates() API call.
    """

    if skipSSL:
        skip = skipSSL

    def test_trustRootFromCertificatesPrivatePublic(self):
        """
        L{trustRootFromCertificates} accepts either a L{sslverify.Certificate}
        or a L{sslverify.PrivateCertificate} instance.
        """
        privateCert = sslverify.PrivateCertificate.loadPEM(A_KEYPAIR)
        cert = sslverify.Certificate.loadPEM(A_HOST_CERTIFICATE_PEM)

        mt = sslverify.trustRootFromCertificates([privateCert, cert])

        # Verify that the returned object acts correctly when used as a
        # trustRoot= param to optionsForClientTLS.
        sProto, cProto, sWrap, cWrap, pump = loopbackTLSConnectionInMemory(
            trustRoot=mt,
            privateKey=privateCert.privateKey.original,
            serverCertificate=privateCert.original,
        )

        # This connection should succeed
        self.assertEqual(cWrap.data, b"greetings!")
        self.assertIsNone(cWrap.lostReason)

    def test_trustRootSelfSignedServerCertificate(self):
        """
        L{trustRootFromCertificates} called with a single self-signed
        certificate will cause L{optionsForClientTLS} to accept client
        connections to a server with that certificate.
        """
        key, cert = makeCertificate(O=b"Server Test Certificate", CN=b"server")
        selfSigned = sslverify.PrivateCertificate.fromCertificateAndKeyPair(
            sslverify.Certificate(cert),
            sslverify.KeyPair(key),
        )

        trust = sslverify.trustRootFromCertificates([selfSigned])

        # Since we trust this exact certificate, connections to this server
        # should succeed.
        sProto, cProto, sWrap, cWrap, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=selfSigned.privateKey.original,
            serverCertificate=selfSigned.original,
        )
        self.assertEqual(cWrap.data, b"greetings!")
        self.assertIsNone(cWrap.lostReason)

    def test_trustRootCertificateAuthorityTrustsConnection(self):
        """
        L{trustRootFromCertificates} called with certificate A will cause
        L{optionsForClientTLS} to accept client connections to a server with
        certificate B where B is signed by A.
        """
        caCert, serverCert = certificatesForAuthorityAndServer()

        trust = sslverify.trustRootFromCertificates([caCert])

        # Since we've listed the CA's certificate as a trusted cert, a
        # connection to the server certificate it signed should succeed.
        sProto, cProto, sWrap, cWrap, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=serverCert.privateKey.original,
            serverCertificate=serverCert.original,
        )
        self.assertEqual(cWrap.data, b"greetings!")
        self.assertIsNone(cWrap.lostReason)

    def test_trustRootFromCertificatesUntrusted(self):
        """
        L{trustRootFromCertificates} called with certificate A will cause
        L{optionsForClientTLS} to disallow any connections to a server with
        certificate B where B is not signed by A.
        """
        key, cert = makeCertificate(O=b"Server Test Certificate", CN=b"server")
        serverCert = sslverify.PrivateCertificate.fromCertificateAndKeyPair(
            sslverify.Certificate(cert),
            sslverify.KeyPair(key),
        )
        untrustedCert = sslverify.Certificate(
            makeCertificate(O=b"CA Test Certificate", CN=b"unknown CA")[1]
        )

        trust = sslverify.trustRootFromCertificates([untrustedCert])

        # Since we only trust 'untrustedCert' which has not signed our
        # server's cert, we should reject this connection
        sProto, cProto, sWrap, cWrap, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=serverCert.privateKey.original,
            serverCertificate=serverCert.original,
        )

        # This connection should fail, so no data was received.
        self.assertEqual(cWrap.data, b"")

        # It was an L{SSL.Error}.
        self.assertEqual(cWrap.lostReason.type, SSL.Error)

        # Some combination of OpenSSL and PyOpenSSL is bad at reporting errors.
        err = cWrap.lostReason.value
        self.assertEqual(err.args[0][0][2], "tlsv1 alert unknown ca")

    def test_trustRootFromCertificatesOpenSSLObjects(self):
        """
        L{trustRootFromCertificates} rejects any L{OpenSSL.crypto.X509}
        instances in the list passed to it.
        """
        private = sslverify.PrivateCertificate.loadPEM(A_KEYPAIR)
        certX509 = private.original

        exception = self.assertRaises(
            TypeError,
            sslverify.trustRootFromCertificates,
            [certX509],
        )
        self.assertEqual(
            "certificates items must be twisted.internet.ssl.CertBase " "instances",
            exception.args[0],
        )


class OpenSSLCipherTests(TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLCipher.
    """

    if skipSSL:
        skip = skipSSL

    cipherName = "CIPHER-STRING"

    def test_constructorSetsFullName(self):
        """
        The first argument passed to the constructor becomes the full name.
        """
        self.assertEqual(
            self.cipherName, sslverify.OpenSSLCipher(self.cipherName).fullName
        )

    def test_repr(self):
        """
        C{repr(cipher)} returns a valid constructor call.
        """
        cipher = sslverify.OpenSSLCipher(self.cipherName)
        self.assertEqual(
            cipher, eval(repr(cipher), {"OpenSSLCipher": sslverify.OpenSSLCipher})
        )

    def test_eqSameClass(self):
        """
        Equal type and C{fullName} means that the objects are equal.
        """
        cipher1 = sslverify.OpenSSLCipher(self.cipherName)
        cipher2 = sslverify.OpenSSLCipher(self.cipherName)
        self.assertEqual(cipher1, cipher2)

    def test_eqSameNameDifferentType(self):
        """
        If ciphers have the same name but different types, they're still
        different.
        """

        class DifferentCipher:
            fullName = self.cipherName

        self.assertNotEqual(
            sslverify.OpenSSLCipher(self.cipherName),
            DifferentCipher(),
        )


class ExpandCipherStringTests(TestCase):
    """
    Tests for twisted.internet._sslverify._expandCipherString.
    """

    if skipSSL:
        skip = skipSSL

    def test_doesNotStumbleOverEmptyList(self):
        """
        If the expanded cipher list is empty, an empty L{list} is returned.
        """
        self.assertEqual(
            tuple(), sslverify._expandCipherString("", SSL.SSLv23_METHOD, 0)
        )

    def test_doesNotSwallowOtherSSLErrors(self):
        """
        Only no cipher matches get swallowed, every other SSL error gets
        propagated.
        """

        def raiser(_):
            # Unfortunately, there seems to be no way to trigger a real SSL
            # error artificially.
            raise SSL.Error([["", "", ""]])

        ctx = FakeContext(SSL.SSLv23_METHOD)
        ctx.set_cipher_list = raiser
        self.patch(sslverify.SSL, "Context", lambda _: ctx)
        self.assertRaises(
            SSL.Error, sslverify._expandCipherString, "ALL", SSL.SSLv23_METHOD, 0
        )

    def test_returnsTupleOfICiphers(self):
        """
        L{sslverify._expandCipherString} always returns a L{tuple} of
        L{interfaces.ICipher}.
        """
        ciphers = sslverify._expandCipherString("ALL", SSL.SSLv23_METHOD, 0)
        self.assertIsInstance(ciphers, tuple)
        bogus = []
        for c in ciphers:
            if not interfaces.ICipher.providedBy(c):
                bogus.append(c)

        self.assertEqual([], bogus)


class AcceptableCiphersTests(TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLAcceptableCiphers.
    """

    if skipSSL:
        skip = skipSSL

    def test_selectOnEmptyListReturnsEmptyList(self):
        """
        If no ciphers are available, nothing can be selected.
        """
        ac = sslverify.OpenSSLAcceptableCiphers(tuple())
        self.assertEqual(tuple(), ac.selectCiphers(tuple()))

    def test_selectReturnsOnlyFromAvailable(self):
        """
        Select only returns a cross section of what is available and what is
        desirable.
        """
        ac = sslverify.OpenSSLAcceptableCiphers(
            [
                sslverify.OpenSSLCipher("A"),
                sslverify.OpenSSLCipher("B"),
            ]
        )
        self.assertEqual(
            (sslverify.OpenSSLCipher("B"),),
            ac.selectCiphers(
                [sslverify.OpenSSLCipher("B"), sslverify.OpenSSLCipher("C")]
            ),
        )

    def test_fromOpenSSLCipherStringExpandsToTupleOfCiphers(self):
        """
        If L{sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString} is
        called it expands the string to a tuple of ciphers.
        """
        ac = sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString("ALL")
        self.assertIsInstance(ac._ciphers, tuple)
        self.assertTrue(all(sslverify.ICipher.providedBy(c) for c in ac._ciphers))


class DiffieHellmanParametersTests(TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLDHParameters.
    """

    if skipSSL:
        skip = skipSSL
    filePath = FilePath(b"dh.params")

    def test_fromFile(self):
        """
        Calling C{fromFile} with a filename returns an instance with that file
        name saved.
        """
        params = sslverify.OpenSSLDiffieHellmanParameters.fromFile(self.filePath)
        self.assertEqual(self.filePath, params._dhFile)


class FakeLibState:
    """
    State for L{FakeLib}

    @param setECDHAutoRaises: An exception
        L{FakeLib.SSL_CTX_set_ecdh_auto} should raise; if L{None},
        nothing is raised.

    @ivar ecdhContexts: A list of SSL contexts with which
        L{FakeLib.SSL_CTX_set_ecdh_auto} was called
    @type ecdhContexts: L{list} of L{OpenSSL.SSL.Context}s

    @ivar ecdhValues: A list of boolean values with which
        L{FakeLib.SSL_CTX_set_ecdh_auto} was called
    @type ecdhValues: L{list} of L{boolean}s
    """

    __slots__ = ("setECDHAutoRaises", "ecdhContexts", "ecdhValues")

    def __init__(self, setECDHAutoRaises):
        self.setECDHAutoRaises = setECDHAutoRaises
        self.ecdhContexts = []
        self.ecdhValues = []


class FakeLib:
    """
    An introspectable fake of cryptography's lib object.

    @param state: A L{FakeLibState} instance that contains this fake's
        state.
    """

    def __init__(self, state):
        self._state = state

    def SSL_CTX_set_ecdh_auto(self, ctx, value):
        """
        Record the context and value under in the C{_state} instance
        variable.

        @see: L{FakeLibState}

        @param ctx: An SSL context.
        @type ctx: L{OpenSSL.SSL.Context}

        @param value: A boolean value
        @type value: L{bool}
        """
        self._state.ecdhContexts.append(ctx)
        self._state.ecdhValues.append(value)
        if self._state.setECDHAutoRaises is not None:
            raise self._state.setECDHAutoRaises


class FakeLibTests(TestCase):
    """
    Tests for L{FakeLib}.
    """

    def test_SSL_CTX_set_ecdh_auto(self):
        """
        L{FakeLib.SSL_CTX_set_ecdh_auto} records context and value it
        was called with.
        """
        state = FakeLibState(setECDHAutoRaises=None)
        lib = FakeLib(state)
        self.assertNot(state.ecdhContexts)
        self.assertNot(state.ecdhValues)

        context, value = "CONTEXT", True
        lib.SSL_CTX_set_ecdh_auto(context, value)
        self.assertEqual(state.ecdhContexts, [context])
        self.assertEqual(state.ecdhValues, [True])

    def test_SSL_CTX_set_ecdh_autoRaises(self):
        """
        L{FakeLib.SSL_CTX_set_ecdh_auto} raises the exception provided
        by its state, while still recording its arguments.
        """
        state = FakeLibState(setECDHAutoRaises=ValueError)
        lib = FakeLib(state)
        self.assertNot(state.ecdhContexts)
        self.assertNot(state.ecdhValues)

        context, value = "CONTEXT", True
        self.assertRaises(ValueError, lib.SSL_CTX_set_ecdh_auto, context, value)
        self.assertEqual(state.ecdhContexts, [context])
        self.assertEqual(state.ecdhValues, [True])


class FakeCryptoState:
    """
    State for L{FakeCrypto}

    @param getEllipticCurveRaises: What
        L{FakeCrypto.get_elliptic_curve} should raise; L{None} and it
        won't raise anything

    @param getEllipticCurveReturns: What
        L{FakeCrypto.get_elliptic_curve} should return.

    @ivar getEllipticCurveCalls: The arguments with which
        L{FakeCrypto.get_elliptic_curve} has been called.
    @type getEllipticCurveCalls: L{list}
    """

    __slots__ = (
        "getEllipticCurveRaises",
        "getEllipticCurveReturns",
        "getEllipticCurveCalls",
    )

    def __init__(
        self,
        getEllipticCurveRaises,
        getEllipticCurveReturns,
    ):
        self.getEllipticCurveRaises = getEllipticCurveRaises
        self.getEllipticCurveReturns = getEllipticCurveReturns
        self.getEllipticCurveCalls = []


class FakeCrypto:
    """
    An introspectable fake of pyOpenSSL's L{OpenSSL.crypto} module.

    @ivar state: A L{FakeCryptoState} instance
    """

    def __init__(self, state):
        self._state = state

    def get_elliptic_curve(self, curve):
        """
        A fake that records the curve with which it was called.

        @param curve: see L{crypto.get_elliptic_curve}

        @return: see L{FakeCryptoState.getEllipticCurveReturns}
        @raises: see L{FakeCryptoState.getEllipticCurveRaises}
        """
        self._state.getEllipticCurveCalls.append(curve)
        if self._state.getEllipticCurveRaises is not None:
            raise self._state.getEllipticCurveRaises
        return self._state.getEllipticCurveReturns


class FakeCryptoTests(SynchronousTestCase):
    """
    Tests for L{FakeCrypto}.
    """

    def test_get_elliptic_curveRecordsArgument(self):
        """
        L{FakeCrypto.test_get_elliptic_curve} records the curve with
        which it was called.
        """
        state = FakeCryptoState(
            getEllipticCurveRaises=None,
            getEllipticCurveReturns=None,
        )
        crypto = FakeCrypto(state)
        crypto.get_elliptic_curve("a curve name")
        self.assertEqual(state.getEllipticCurveCalls, ["a curve name"])

    def test_get_elliptic_curveReturns(self):
        """
        L{FakeCrypto.test_get_elliptic_curve} returns the value
        specified by its state object and records what it was called
        with.
        """
        returnValue = "object"
        state = FakeCryptoState(
            getEllipticCurveRaises=None,
            getEllipticCurveReturns=returnValue,
        )
        crypto = FakeCrypto(state)
        self.assertIs(
            crypto.get_elliptic_curve("another curve name"),
            returnValue,
        )
        self.assertEqual(state.getEllipticCurveCalls, ["another curve name"])

    def test_get_elliptic_curveRaises(self):
        """
        L{FakeCrypto.test_get_elliptic_curve} raises the exception
        specified by its state object.
        """
        state = FakeCryptoState(
            getEllipticCurveRaises=ValueError, getEllipticCurveReturns=None
        )
        crypto = FakeCrypto(state)
        self.assertRaises(
            ValueError,
            crypto.get_elliptic_curve,
            "yet another curve name",
        )
        self.assertEqual(
            state.getEllipticCurveCalls,
            ["yet another curve name"],
        )


class ChooseDiffieHellmanEllipticCurveTests(SynchronousTestCase):
    """
    Tests for L{sslverify._ChooseDiffieHellmanEllipticCurve}.

    @cvar OPENSSL_110: A version number for OpenSSL 1.1.0

    @cvar OPENSSL_102: A version number for OpenSSL 1.0.2

    @cvar OPENSSL_101: A version number for OpenSSL 1.0.1

    @see:
        U{https://wiki.openssl.org/index.php/Manual:OPENSSL_VERSION_NUMBER(3)}
    """

    if skipSSL:
        skip = skipSSL

    OPENSSL_110 = 0x1010007F
    OPENSSL_102 = 0x100020EF
    OPENSSL_101 = 0x1000114F

    def setUp(self):
        self.libState = FakeLibState(setECDHAutoRaises=False)
        self.lib = FakeLib(self.libState)

        self.cryptoState = FakeCryptoState(
            getEllipticCurveReturns=None, getEllipticCurveRaises=None
        )
        self.crypto = FakeCrypto(self.cryptoState)
        self.context = FakeContext(SSL.SSLv23_METHOD)

    def test_openSSL110(self):
        """
        No configuration of contexts occurs under OpenSSL 1.1.0 and
        later, because they create contexts with secure ECDH curves.

        @see: U{http://twistedmatrix.com/trac/ticket/9210}
        """
        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_110,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(self.context)

        self.assertFalse(self.libState.ecdhContexts)
        self.assertFalse(self.libState.ecdhValues)
        self.assertFalse(self.cryptoState.getEllipticCurveCalls)
        self.assertIsNone(self.context._ecCurve)

    def test_openSSL102(self):
        """
        OpenSSL 1.0.2 does not set ECDH curves by default, but
        C{SSL_CTX_set_ecdh_auto} requests that a context choose a
        secure set curves automatically.
        """
        context = SSL.Context(SSL.SSLv23_METHOD)
        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_102,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(context)

        self.assertEqual(self.libState.ecdhContexts, [context._context])
        self.assertEqual(self.libState.ecdhValues, [True])
        self.assertFalse(self.cryptoState.getEllipticCurveCalls)
        self.assertIsNone(self.context._ecCurve)

    def test_openSSL102SetECDHAutoRaises(self):
        """
        An exception raised by C{SSL_CTX_set_ecdh_auto} under OpenSSL
        1.0.2 is suppressed because ECDH is best-effort.
        """
        self.libState.setECDHAutoRaises = BaseException
        context = SSL.Context(SSL.SSLv23_METHOD)
        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_102,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(context)

        self.assertEqual(self.libState.ecdhContexts, [context._context])
        self.assertEqual(self.libState.ecdhValues, [True])
        self.assertFalse(self.cryptoState.getEllipticCurveCalls)

    def test_openSSL101(self):
        """
        OpenSSL 1.0.1 does not set ECDH curves by default, nor does
        it expose L{SSL_CTX_set_ecdh_auto}.  Instead, a single ECDH
        curve can be set with L{OpenSSL.SSL.Context.set_tmp_ecdh}.
        """
        self.cryptoState.getEllipticCurveReturns = curve = "curve object"
        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_101,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(self.context)

        self.assertFalse(self.libState.ecdhContexts)
        self.assertFalse(self.libState.ecdhValues)
        self.assertEqual(
            self.cryptoState.getEllipticCurveCalls,
            [sslverify._defaultCurveName],
        )
        self.assertIs(self.context._ecCurve, curve)

    def test_openSSL101SetECDHRaises(self):
        """
        An exception raised by L{OpenSSL.SSL.Context.set_tmp_ecdh}
        under OpenSSL 1.0.1 is suppressed because ECHDE is best-effort.
        """

        def set_tmp_ecdh(ctx):
            raise BaseException

        self.context.set_tmp_ecdh = set_tmp_ecdh

        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_101,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(self.context)

        self.assertFalse(self.libState.ecdhContexts)
        self.assertFalse(self.libState.ecdhValues)
        self.assertEqual(
            self.cryptoState.getEllipticCurveCalls,
            [sslverify._defaultCurveName],
        )

    def test_openSSL101NoECC(self):
        """
        Contexts created under an OpenSSL 1.0.1 that doesn't support
        ECC have no configuration applied.
        """
        self.cryptoState.getEllipticCurveRaises = ValueError
        chooser = sslverify._ChooseDiffieHellmanEllipticCurve(
            self.OPENSSL_101,
            openSSLlib=self.lib,
            openSSLcrypto=self.crypto,
        )
        chooser.configureECDHCurve(self.context)

        self.assertFalse(self.libState.ecdhContexts)
        self.assertFalse(self.libState.ecdhValues)
        self.assertIsNone(self.context._ecCurve)


class KeyPairTests(TestCase):
    """
    Tests for L{sslverify.KeyPair}.
    """

    if skipSSL:
        skip = skipSSL

    def setUp(self):
        """
        Create test certificate.
        """
        self.sKey = makeCertificate(O=b"Server Test Certificate", CN=b"server")[0]

    def test_getstateDeprecation(self):
        """
        L{sslverify.KeyPair.__getstate__} is deprecated.
        """
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.KeyPair(self.sKey).__getstate__,
        )

    def test_setstateDeprecation(self):
        """
        {sslverify.KeyPair.__setstate__} is deprecated.
        """
        state = sslverify.KeyPair(self.sKey).dump()
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.KeyPair(self.sKey).__setstate__,
            state,
        )

    def test_noTrailingNewlinePemCert(self):
        noTrailingNewlineKeyPemPath = getModule("twisted.test").filePath.sibling(
            "cert.pem.no_trailing_newline"
        )

        certPEM = noTrailingNewlineKeyPemPath.getContent()
        ssl.Certificate.loadPEM(certPEM)


class SelectVerifyImplementationTests(SynchronousTestCase):
    """
    Tests for L{_selectVerifyImplementation}.
    """

    if skipSSL:
        skip = skipSSL

    def test_dependencyMissing(self):
        """
        If I{service_identity} cannot be imported then
        L{_selectVerifyImplementation} returns L{simpleVerifyHostname} and
        L{SimpleVerificationError}.
        """
        with SetAsideModule("service_identity"):
            sys.modules["service_identity"] = None

            result = sslverify._selectVerifyImplementation()
            expected = (
                sslverify.simpleVerifyHostname,
                sslverify.simpleVerifyIPAddress,
                sslverify.SimpleVerificationError,
            )
            self.assertEqual(expected, result)

    test_dependencyMissing.suppress = [  # type: ignore[attr-defined]
        util.suppress(
            message=(
                "You do not have a working installation of the "
                "service_identity module"
            ),
        ),
    ]

    def test_dependencyMissingWarning(self):
        """
        If I{service_identity} cannot be imported then
        L{_selectVerifyImplementation} emits a L{UserWarning} advising the user
        of the exact error.
        """
        with SetAsideModule("service_identity"):
            sys.modules["service_identity"] = None

            sslverify._selectVerifyImplementation()

        [warning] = list(
            warning
            for warning in self.flushWarnings()
            if warning["category"] == UserWarning
        )

        expectedMessage = (
            "You do not have a working installation of the "
            "service_identity module: "
            "'import of service_identity halted; None in sys.modules'.  "
            "Please install it from "
            "<https://pypi.python.org/pypi/service_identity> "
            "and make sure all of its dependencies are satisfied.  "
            "Without the service_identity module, Twisted can perform only"
            " rudimentary TLS client hostname verification.  Many valid "
            "certificate/hostname mappings may be rejected."
        )

        self.assertEqual(warning["message"], expectedMessage)
        # Make sure we're abusing the warning system to a sufficient
        # degree: there is no filename or line number that makes sense for
        # this warning to "blame" for the problem.  It is a system
        # misconfiguration.  So the location information should be blank
        # (or as blank as we can make it).
        self.assertEqual(warning["filename"], "")
        self.assertEqual(warning["lineno"], 0)
