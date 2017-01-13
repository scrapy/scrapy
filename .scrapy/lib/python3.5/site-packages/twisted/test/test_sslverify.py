# Copyright 2005 Divmod, Inc.  See LICENSE file for details
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet._sslverify}.
"""

from __future__ import division, absolute_import

import sys
import itertools

from zope.interface import implementer

skipSSL = None
skipSNI = None
skipNPN = None
skipALPN = None
try:
    import OpenSSL
except ImportError:
    skipSSL = "OpenSSL is required for SSL tests."
    skipSNI = skipSSL
    skipNPN = skipSSL
    skipALPN = skipSSL
else:
    from OpenSSL import SSL
    from OpenSSL.crypto import PKey, X509
    from OpenSSL.crypto import TYPE_RSA, FILETYPE_PEM

    try:
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.set_npn_advertise_callback(lambda c: None)
    except AttributeError:
        skipNPN = "PyOpenSSL 0.15 or greater is required for NPN support"
    except NotImplementedError:
        skipNPN = "OpenSSL 1.0.1 or greater required for NPN support"

    try:
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.set_alpn_select_callback(lambda c: None)
    except AttributeError:
        skipALPN = "PyOpenSSL 0.15 or greater is required for ALPN support"
    except NotImplementedError:
        skipALPN = "OpenSSL 1.0.2 or greater required for ALPN support"

from twisted.test.test_twisted import SetAsideModule
from twisted.test.iosim import connectedServerAndClient

from twisted.internet.error import ConnectionClosed
from twisted.python.compat import nativeString, _PY3
from twisted.python.constants import NamedConstant, Names
from twisted.python.filepath import FilePath
from twisted.python.modules import getModule

from twisted.trial import unittest, util
from twisted.internet import protocol, defer, reactor

from twisted.internet.error import CertificateError, ConnectionLost
from twisted.internet import interfaces
from twisted.python.versions import Version

if not skipSSL:
    from twisted.internet.ssl import platformTrust, VerificationError
    from twisted.internet import _sslverify as sslverify
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

A_KEYPAIR = getModule(__name__).filePath.sibling('server.pem').getContent()



class DummyOpenSSL(object):
    """
    A fake of the L{OpenSSL} module.

    @ivar __version__: A string describing I{pyOpenSSL} version number the fake
        is emulating.
    @type __version__: L{str}
    """
    def __init__(self, major, minor, patch=None):
        """
        @param major: The major version number to emulate.  I{X} in the version
            I{X.Y}.
        @type major: L{int}

        @param minor: The minor version number to emulate.  I{Y} in the version
            I{X.Y}.
        @type minor: L{int}

        """
        self.__version__ = "%d.%d" % (major, minor)
        if patch is not None:
            self.__version__ += ".%d" % (patch,)

_preTwelveOpenSSL = DummyOpenSSL(0, 11)
_postTwelveOpenSSL = DummyOpenSSL(0, 13, 1)


def counter(counter=itertools.count()):
    """
    Each time we're called, return the next integer in the natural numbers.
    """
    return next(counter)



def makeCertificate(**kw):
    keypair = PKey()
    keypair.generate_key(TYPE_RSA, 768)

    certificate = X509()
    certificate.gmtime_adj_notBefore(0)
    certificate.gmtime_adj_notAfter(60 * 60 * 24 * 365) # One year
    for xname in certificate.get_issuer(), certificate.get_subject():
        for (k, v) in kw.items():
            setattr(xname, k, nativeString(v))

    certificate.set_serial_number(counter())
    certificate.set_pubkey(keypair)
    certificate.sign(keypair, "md5")

    return keypair, certificate



def certificatesForAuthorityAndServer(commonName=b'example.com'):
    """
    Create a self-signed CA certificate and server certificate signed by the
    CA.

    @param commonName: The C{commonName} to embed in the certificate.
    @type commonName: L{bytes}

    @return: a 2-tuple of C{(certificate_authority_certificate,
        server_certificate)}
    @rtype: L{tuple} of (L{sslverify.Certificate},
        L{sslverify.PrivateCertificate})
    """
    serverDN = sslverify.DistinguishedName(commonName=commonName)
    serverKey = sslverify.KeyPair.generate()
    serverCertReq = serverKey.certificateRequest(serverDN)

    caDN = sslverify.DistinguishedName(commonName=b'CA')
    caKey= sslverify.KeyPair.generate()
    caCertReq = caKey.certificateRequest(caDN)
    caSelfCertData = caKey.signCertificateRequest(
            caDN, caCertReq, lambda dn: True, 516)
    caSelfCert = caKey.newCertificate(caSelfCertData)

    serverCertData = caKey.signCertificateRequest(
            caDN, serverCertReq, lambda dn: True, 516)
    serverCert = serverKey.newCertificate(serverCertData)
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

    @return: 3-tuple of server-protocol, client-protocol, and L{IOPump}
    @rtype: L{tuple}
    """
    class GreetingServer(protocol.Protocol):
        greeting = b"greetings!"
        def connectionMade(self):
            self.transport.write(self.greeting)

    class ListeningClient(protocol.Protocol):
        data = b''
        lostReason = None
        def dataReceived(self, data):
            self.data += data
        def connectionLost(self, reason):
            self.lostReason = reason

    clientFactory = TLSMemoryBIOFactory(
        clientOpts, isClient=True,
        wrappedFactory=protocol.Factory.forProtocol(GreetingServer)
    )
    serverFactory = TLSMemoryBIOFactory(
        serverOpts, isClient=False,
        wrappedFactory=protocol.Factory.forProtocol(ListeningClient)
    )

    sProto, cProto, pump = connectedServerAndClient(
        lambda: serverFactory.buildProtocol(None),
        lambda: clientFactory.buildProtocol(None)
    )
    return sProto, cProto, pump



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
    class ContextFactory(object):
        def getContext(self):
            """
            Create a context for the server side of the connection.

            @return: an SSL context using a certificate and key.
            @rtype: C{OpenSSL.SSL.Context}
            """
            ctx = SSL.Context(SSL.TLSv1_METHOD)
            if chainedCertFile is not None:
                ctx.use_certificate_chain_file(chainedCertFile)
            ctx.use_privatekey_file(privateKeyFile)
            # Let the test author know if they screwed something up.
            ctx.check_privatekey()
            return ctx

    serverOpts = ContextFactory()
    clientOpts = sslverify.OpenSSLCertificateOptions(trustRoot=trustRoot)

    return _loopbackTLSConnection(serverOpts, clientOpts)



def loopbackTLSConnectionInMemory(trustRoot, privateKey,
                                  serverCertificate, clientProtocols=None,
                                  serverProtocols=None,
                                  clientOptions=None):
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
        trustRoot=trustRoot,
        acceptableProtocols=clientProtocols
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
    byte = b'x'
    def connectionMade(self):
        self.transport.write(self.byte)

    def connectionLost(self, reason):
        self.factory.onLost.errback(reason)



class FakeContext(object):
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

    @ivar _sessionID: Set by L{set_session_id}.

    @ivar _extraCertChain: Accumulated L{list} of all extra certificates added
        by L{add_extra_chain_cert}.

    @ivar _cipherList: Set by L{set_cipher_list}.

    @ivar _dhFilename: Set by L{load_tmp_dh}.

    @ivar _defaultVerifyPathsSet: Set by L{set_default_verify_paths}
    """
    _options = 0

    def __init__(self, method):
        self._method = method
        self._extraCertChain = []
        self._defaultVerifyPathsSet = False


    def set_options(self, options):
        self._options |= options


    def use_certificate(self, certificate):
        self._certificate = certificate


    def use_privatekey(self, privateKey):
        self._privateKey = privateKey


    def check_privatekey(self):
        return None


    def set_verify(self, flags, callback):
        self._verify = flags, callback


    def set_verify_depth(self, depth):
        self._verifyDepth = depth


    def set_session_id(self, sessionID):
        self._sessionID = sessionID


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



class ClientOptionsTests(unittest.SynchronousTestCase):
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
            hostname=u'alpha', someRandomThing=u'beta',
        )
        self.assertEqual(
            str(error),
            "optionsForClientTLS() got an unexpected keyword argument "
            "'someRandomThing'"
        )


    def test_bytesFailFast(self):
        """
        If you pass L{bytes} as the hostname to
        L{sslverify.optionsForClientTLS} it immediately raises a L{TypeError}.
        """
        error = self.assertRaises(
            TypeError,
            sslverify.optionsForClientTLS, b'not-actually-a-hostname.com'
        )
        expectedText = (
            "optionsForClientTLS requires text for host names, not " +
            bytes.__name__
        )
        self.assertEqual(str(error), expectedText)



class OpenSSLOptionsTests(unittest.TestCase):
    if skipSSL:
        skip = skipSSL

    serverPort = clientConn = None
    onServerLost = onClientLost = None

    sKey = None
    sCert = None
    cKey = None
    cCert = None

    def setUp(self):
        """
        Create class variables of client and server certificates.
        """
        self.sKey, self.sCert = makeCertificate(
            O=b"Server Test Certificate",
            CN=b"server")
        self.cKey, self.cCert = makeCertificate(
            O=b"Client Test Certificate",
            CN=b"client")
        self.caCert1 = makeCertificate(
            O=b"CA Test Certificate 1",
            CN=b"ca1")[1]
        self.caCert2 = makeCertificate(
            O=b"CA Test Certificate",
            CN=b"ca2")[1]
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

    def loopback(self, serverCertOpts, clientCertOpts,
                 onServerLost=None, onClientLost=None, onData=None):
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
        self.clientConn = reactor.connectSSL('127.0.0.1',
                self.serverPort.getHost().port, clientFactory, clientCertOpts)


    def test_constructorWithOnlyPrivateKey(self):
        """
        C{privateKey} and C{certificate} make only sense if both are set.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions, privateKey=self.sKey
        )


    def test_constructorWithOnlyCertificate(self):
        """
        C{privateKey} and C{certificate} make only sense if both are set.
        """
        self.assertRaises(
            ValueError,
            sslverify.OpenSSLCertificateOptions, certificate=self.sCert
        )


    def test_constructorWithCertificateAndPrivateKey(self):
        """
        Specifying C{privateKey} and C{certificate} initializes correctly.
        """
        opts = sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                                                   certificate=self.sCert)
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
            privateKey=self.sKey, certificate=self.sCert, verify=True
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
            privateKey=self.sKey, certificate=self.sCert,
            verify=True, trustRoot=None, caCerts=self.caCerts,
        )
        self.assertRaises(
            TypeError,
            sslverify.OpenSSLCertificateOptions,
            privateKey=self.sKey, certificate=self.sCert,
            trustRoot=None, requireCertificate=True,
        )


    def test_constructorAllowsCACertsWithoutVerify(self):
        """
        It's currently a NOP, but valid.
        """
        opts = sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                                                   certificate=self.sCert,
                                                   caCerts=self.caCerts)
        self.assertFalse(opts.verify)
        self.assertEqual(self.caCerts, opts.caCerts)


    def test_constructorWithVerifyAndCACerts(self):
        """
        Specifying C{verify} and C{caCerts} initializes correctly.
        """
        opts = sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                                                   certificate=self.sCert,
                                                   verify=True,
                                                   caCerts=self.caCerts)
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
        self.assertEqual(opts._cipherString.encode('ascii'), ctx._cipherList)


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
            acceptableCiphers=
            sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString('')
        )


    def test_honorsAcceptableCiphersArgument(self):
        """
        If acceptable ciphers are passed, they are used.
        """
        @implementer(interfaces.IAcceptableCiphers)
        class FakeAcceptableCiphers(object):
            def selectCiphers(self, _):
                return [sslverify.OpenSSLCipher(u'sentinel')]

        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            acceptableCiphers=FakeAcceptableCiphers(),
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(b'sentinel', ctx._cipherList)


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
        options = (SSL.OP_NO_SSLv2 | opts._OP_NO_COMPRESSION |
                   opts._OP_CIPHER_SERVER_PREFERENCE)
        self.assertEqual(options, ctx._options & options)


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
        options = SSL.OP_SINGLE_DH_USE | opts._OP_SINGLE_ECDH_USE
        self.assertEqual(options, ctx._options & options)


    def test_dhParams(self):
        """
        If C{dhParams} is set, they are loaded into each new context.
        """
        class FakeDiffieHellmanParameters(object):
            _dhFile = FilePath(b'dh.params')

        dhParams = FakeDiffieHellmanParameters()
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
            dhParameters=dhParams,
        )
        opts._contextFactory = FakeContext
        ctx = opts.getContext()
        self.assertEqual(
            FakeDiffieHellmanParameters._dhFile.path,
            ctx._dhFilename
        )


    def test_ecDoesNotBreakConstructor(self):
        """
        Missing ECC does not break the constructor and sets C{_ecCurve} to
        L{None}.
        """
        def raiser(self):
            raise NotImplementedError
        self.patch(sslverify._OpenSSLECCurve, "_getBinding", raiser)

        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        self.assertIsNone(opts._ecCurve)


    def test_ecNeverBreaksGetContext(self):
        """
        ECDHE support is best effort only and errors are ignored.
        """
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        opts._ecCurve = object()
        ctx = opts.getContext()
        self.assertIsInstance(ctx, SSL.Context)


    def test_ecSuccessWithRealBindings(self):
        """
        Integration test that checks the positive code path to ensure that we
        use the API properly.
        """
        try:
            defaultCurve = sslverify._OpenSSLECCurve(
                sslverify._defaultCurveName
            )
        except NotImplementedError:
            raise unittest.SkipTest(
                "Underlying pyOpenSSL is not based on cryptography."
            )
        opts = sslverify.OpenSSLCertificateOptions(
            privateKey=self.sKey,
            certificate=self.sCert,
        )
        self.assertEqual(defaultCurve, opts._ecCurve)
        # Exercise positive code path.  getContext swallows errors so we do it
        # explicitly by hand.
        opts._ecCurve.addECKeyToContext(opts.getContext())


    def test_abbreviatingDistinguishedNames(self):
        """
        Check that abbreviations used in certificates correctly map to
        complete names.
        """
        self.assertEqual(
                sslverify.DN(CN=b'a', OU=b'hello'),
                sslverify.DistinguishedName(commonName=b'a',
                                            organizationalUnitName=b'hello'))
        self.assertNotEqual(
                sslverify.DN(CN=b'a', OU=b'hello'),
                sslverify.DN(CN=b'a', OU=b'hello', emailAddress=b'xxx'))
        dn = sslverify.DN(CN=b'abcdefg')
        self.assertRaises(AttributeError, setattr, dn, 'Cn', b'x')
        self.assertEqual(dn.CN, dn.commonName)
        dn.CN = b'bcdefga'
        self.assertEqual(dn.CN, dn.commonName)


    def testInspectDistinguishedName(self):
        n = sslverify.DN(commonName=b'common name',
                         organizationName=b'organization name',
                         organizationalUnitName=b'organizational unit name',
                         localityName=b'locality name',
                         stateOrProvinceName=b'state or province name',
                         countryName=b'country name',
                         emailAddress=b'email address')
        s = n.inspect()
        for k in [
            'common name',
            'organization name',
            'organizational unit name',
            'locality name',
            'state or province name',
            'country name',
            'email address']:
            self.assertIn(k, s, "%r was not in inspect output." % (k,))
            self.assertIn(k.title(), s, "%r was not in inspect output." % (k,))


    def testInspectDistinguishedNameWithoutAllFields(self):
        n = sslverify.DN(localityName=b'locality name')
        s = n.inspect()
        for k in [
            'common name',
            'organization name',
            'organizational unit name',
            'state or province name',
            'country name',
            'email address']:
            self.assertNotIn(k, s, "%r was in inspect output." % (k,))
            self.assertNotIn(k.title(), s, "%r was in inspect output." % (k,))
        self.assertIn('locality name', s)
        self.assertIn('Locality Name', s)


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
            c.inspect().split('\n'),
            ["Certificate For Subject:",
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
             "Public Key with Hash: " + keyHash])


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
            enableSessionTickets=True)
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

    test_certificateOptionsSerialization.suppress = [
        util.suppress(category = DeprecationWarning,
            message='twisted\.internet\._sslverify\.*__[gs]etstate__')]


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
        self.loopback(sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                            certificate=self.sCert, requireCertificate=False),
                      sslverify.OpenSSLCertificateOptions(
                          requireCertificate=False),
                      onData=onData)

        return onData.addCallback(
            lambda result: self.assertEqual(result, WritingProtocol.byte))


    def test_refusedAnonymousClientConnection(self):
        """
        Check that anonymous connections are refused when certificates are
        required on the server.
        """
        onServerLost = defer.Deferred()
        onClientLost = defer.Deferred()
        self.loopback(sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                            certificate=self.sCert, verify=True,
                            caCerts=[self.sCert], requireCertificate=True),
                      sslverify.OpenSSLCertificateOptions(
                          requireCertificate=False),
                      onServerLost=onServerLost,
                      onClientLost=onClientLost)

        d = defer.DeferredList([onClientLost, onServerLost],
                               consumeErrors=True)


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
        self.loopback(sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                            certificate=self.sCert, verify=False,
                            requireCertificate=False),
                      sslverify.OpenSSLCertificateOptions(verify=True,
                            requireCertificate=False, caCerts=[self.cCert]),
                      onServerLost=onServerLost,
                      onClientLost=onClientLost)

        d = defer.DeferredList([onClientLost, onServerLost],
                               consumeErrors=True)
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
        self.loopback(sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                            certificate=self.sCert, verify=False,
                            requireCertificate=False),
                      sslverify.OpenSSLCertificateOptions(verify=True,
                            requireCertificate=True, caCerts=[self.sCert]),
                      onData=onData)

        return onData.addCallback(
                lambda result: self.assertEqual(result, WritingProtocol.byte))

    def test_successfulSymmetricSelfSignedCertificateVerification(self):
        """
        Test a successful connection with validation on both server and client
        sides.
        """
        onData = defer.Deferred()
        self.loopback(sslverify.OpenSSLCertificateOptions(privateKey=self.sKey,
                            certificate=self.sCert, verify=True,
                            requireCertificate=True, caCerts=[self.cCert]),
                      sslverify.OpenSSLCertificateOptions(privateKey=self.cKey,
                            certificate=self.cCert, verify=True,
                            requireCertificate=True, caCerts=[self.sCert]),
                      onData=onData)

        return onData.addCallback(
                lambda result: self.assertEqual(result, WritingProtocol.byte))

    def test_verification(self):
        """
        Check certificates verification building custom certificates data.
        """
        clientDN = sslverify.DistinguishedName(commonName='client')
        clientKey = sslverify.KeyPair.generate()
        clientCertReq = clientKey.certificateRequest(clientDN)

        serverDN = sslverify.DistinguishedName(commonName='server')
        serverKey = sslverify.KeyPair.generate()
        serverCertReq = serverKey.certificateRequest(serverDN)

        clientSelfCertReq = clientKey.certificateRequest(clientDN)
        clientSelfCertData = clientKey.signCertificateRequest(
                clientDN, clientSelfCertReq, lambda dn: True, 132)
        clientSelfCert = clientKey.newCertificate(clientSelfCertData)

        serverSelfCertReq = serverKey.certificateRequest(serverDN)
        serverSelfCertData = serverKey.signCertificateRequest(
                serverDN, serverSelfCertReq, lambda dn: True, 516)
        serverSelfCert = serverKey.newCertificate(serverSelfCertData)

        clientCertData = serverKey.signCertificateRequest(
                serverDN, clientCertReq, lambda dn: True, 7)
        clientCert = clientKey.newCertificate(clientCertData)

        serverCertData = clientKey.signCertificateRequest(
                clientDN, serverCertReq, lambda dn: True, 42)
        serverCert = serverKey.newCertificate(serverCertData)

        onData = defer.Deferred()

        serverOpts = serverCert.options(serverSelfCert)
        clientOpts = clientCert.options(clientSelfCert)

        self.loopback(serverOpts,
                      clientOpts,
                      onData=onData)

        return onData.addCallback(
                lambda result: self.assertEqual(result, WritingProtocol.byte))



class DeprecationTests(unittest.SynchronousTestCase):
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
            sslverify.OpenSSLCertificateOptions().__getstate__)


    def test_setstateDeprecation(self):
        """
        L{sslverify.OpenSSLCertificateOptions.__setstate__} is deprecated.
        """
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.OpenSSLCertificateOptions().__setstate__, {})



class ProtocolVersion(Names):
    """
    L{ProtocolVersion} provides constants representing each version of the
    SSL/TLS protocol.
    """
    SSLv2 = NamedConstant()
    SSLv3 = NamedConstant()
    TLSv1_0 = NamedConstant()
    TLSv1_1 = NamedConstant()
    TLSv1_2 = NamedConstant()



class ProtocolVersionTests(unittest.TestCase):
    """
    Tests for L{sslverify.OpenSSLCertificateOptions}'s SSL/TLS version
    selection features.
    """
    if skipSSL:
        skip = skipSSL
    else:
        _METHOD_TO_PROTOCOL = {
            SSL.SSLv2_METHOD: set([ProtocolVersion.SSLv2]),
            SSL.SSLv3_METHOD: set([ProtocolVersion.SSLv3]),
            SSL.TLSv1_METHOD: set([ProtocolVersion.TLSv1_0]),
            getattr(SSL, "TLSv1_1_METHOD", object()):
                set([ProtocolVersion.TLSv1_1]),
            getattr(SSL, "TLSv1_2_METHOD", object()):
                set([ProtocolVersion.TLSv1_2]),

            # Presently, SSLv23_METHOD means (SSLv2, SSLv3, TLSv1.0, TLSv1.1,
            # TLSv1.2) (excluding any protocol versions not implemented by the
            # underlying version of OpenSSL).
            SSL.SSLv23_METHOD: set(ProtocolVersion.iterconstants()),
            }

        _EXCLUSION_OPS = {
            SSL.OP_NO_SSLv2: ProtocolVersion.SSLv2,
            SSL.OP_NO_SSLv3: ProtocolVersion.SSLv3,
            SSL.OP_NO_TLSv1: ProtocolVersion.TLSv1_0,
            getattr(SSL, "OP_NO_TLSv1_1", 0): ProtocolVersion.TLSv1_1,
            getattr(SSL, "OP_NO_TLSv1_2", 0): ProtocolVersion.TLSv1_2,
            }


    def _protocols(self, opts):
        """
        Determine which SSL/TLS protocol versions are allowed by C{opts}.

        @param opts: An L{sslverify.OpenSSLCertificateOptions} instance to
            inspect.

        @return: A L{set} of L{NamedConstant}s from L{ProtocolVersion}
            indicating which SSL/TLS protocol versions connections negotiated
            using C{opts} will allow.
        """
        protocols = self._METHOD_TO_PROTOCOL[opts.method].copy()
        context = opts.getContext()
        options = context.set_options(0)
        if opts.method == SSL.SSLv23_METHOD:
            # Exclusions apply only to SSLv23_METHOD and no others.
            for opt, exclude in self._EXCLUSION_OPS.items():
                if options & opt:
                    protocols.discard(exclude)
        return protocols


    def test_default(self):
        """
        When L{sslverify.OpenSSLCertificateOptions} is initialized with no
        specific protocol versions all versions of TLS are allowed and no
        versions of SSL are allowed.
        """
        self.assertEqual(
            set([ProtocolVersion.TLSv1_0,
                 ProtocolVersion.TLSv1_1,
                 ProtocolVersion.TLSv1_2]),
            self._protocols(sslverify.OpenSSLCertificateOptions()))



class TrustRootTests(unittest.TestCase):
    """
    Tests for L{sslverify.OpenSSLCertificateOptions}' C{trustRoot} argument,
    L{sslverify.platformTrust}, and their interactions.
    """
    if skipSSL:
        skip = skipSSL

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

        sProto, cProto, pump = loopbackTLSConnection(
            trustRoot=platformTrust(),
            privateKeyFile=privateKey,
            chainedCertFile=chainedCert,
        )
        # No data was received.
        self.assertEqual(cProto.wrappedProtocol.data, b'')

        # It was an L{SSL.Error}.
        self.assertEqual(cProto.wrappedProtocol.lostReason.type, SSL.Error)

        # Some combination of OpenSSL and PyOpenSSL is bad at reporting errors.
        err = cProto.wrappedProtocol.lostReason.value
        self.assertEqual(err.args[0][0][2], 'tlsv1 alert unknown ca')


    def test_trustRootSpecificCertificate(self):
        """
        Specifying a L{Certificate} object for L{trustRoot} will result in that
        certificate being the only trust root for a client.
        """
        caCert, serverCert = certificatesForAuthorityAndServer()
        otherCa, otherServer = certificatesForAuthorityAndServer()
        sProto, cProto, pump = loopbackTLSConnection(
            trustRoot=caCert,
            privateKeyFile=pathContainingDumpOf(self, serverCert.privateKey),
            chainedCertFile=pathContainingDumpOf(self, serverCert),
        )
        pump.flush()
        self.assertIsNone(cProto.wrappedProtocol.lostReason)
        self.assertEqual(cProto.wrappedProtocol.data,
                         sProto.wrappedProtocol.greeting)



class ServiceIdentityTests(unittest.SynchronousTestCase):
    """
    Tests for the verification of the peer's service's identity via the
    C{hostname} argument to L{sslverify.OpenSSLCertificateOptions}.
    """

    if skipSSL:
        skip = skipSSL

    def serviceIdentitySetup(self, clientHostname, serverHostname,
                             serverContextSetup=lambda ctx: None,
                             validCertificate=True,
                             clientPresentsCertificate=False,
                             validClientCertificate=True,
                             serverVerifies=False,
                             buggyInfoCallback=False,
                             fakePlatformTrust=False,
                             useDefaultTrust=False):
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

        @return: see L{connectedServerAndClient}.
        @rtype: see L{connectedServerAndClient}.
        """
        serverIDNA = sslverify._idnaBytes(serverHostname)
        serverCA, serverCert = certificatesForAuthorityAndServer(serverIDNA)
        other = {}
        passClientCert = None
        clientCA, clientCert = certificatesForAuthorityAndServer(u'client')
        if serverVerifies:
            other.update(trustRoot=clientCA)

        if clientPresentsCertificate:
            if validClientCertificate:
                passClientCert = clientCert
            else:
                bogusCA, bogus = certificatesForAuthorityAndServer(u'client')
                passClientCert = bogus

        serverOpts = sslverify.OpenSSLCertificateOptions(
            privateKey=serverCert.privateKey.original,
            certificate=serverCert.original,
            **other
        )
        serverContextSetup(serverOpts.getContext())
        if not validCertificate:
            serverCA, otherServer = certificatesForAuthorityAndServer(
                serverIDNA
            )
        if buggyInfoCallback:
            def broken(*a, **k):
                """
                Raise an exception.

                @param a: Arguments for an C{info_callback}

                @param k: Keyword arguments for an C{info_callback}
                """
                1 / 0
            self.patch(
                sslverify.ClientTLSOptions, "_identityVerifyingInfoCallback",
                broken,
            )

        signature = {'hostname': clientHostname}
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
            data = b''
            def connectionMade(self):
                self.transport.write(self.greeting)
            def dataReceived(self, data):
                self.data += data
            def connectionLost(self, reason):
                self.lostReason = reason

        class GreetingClient(protocol.Protocol):
            greeting = b'cheerio!'
            data = b''
            lostReason = None
            def connectionMade(self):
                self.transport.write(self.greeting)
            def dataReceived(self, data):
                self.data += data
            def connectionLost(self, reason):
                self.lostReason = reason

        self.serverOpts = serverOpts
        self.clientOpts = clientOpts

        clientFactory = TLSMemoryBIOFactory(
            clientOpts, isClient=True,
            wrappedFactory=protocol.Factory.forProtocol(GreetingClient)
        )
        serverFactory = TLSMemoryBIOFactory(
            serverOpts, isClient=False,
            wrappedFactory=protocol.Factory.forProtocol(GreetingServer)
        )
        return connectedServerAndClient(
            lambda: serverFactory.buildProtocol(None),
            lambda: clientFactory.buildProtocol(None),
        )


    def test_invalidHostname(self):
        """
        When a certificate containing an invalid hostname is received from the
        server, the connection is immediately dropped.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"wrong-host.example.com",
            u"correct-host.example.com",
        )
        self.assertEqual(cProto.wrappedProtocol.data, b'')
        self.assertEqual(sProto.wrappedProtocol.data, b'')

        cErr = cProto.wrappedProtocol.lostReason.value
        sErr = sProto.wrappedProtocol.lostReason.value

        self.assertIsInstance(cErr, VerificationError)
        self.assertIsInstance(sErr, ConnectionClosed)


    def test_validHostname(self):
        """
        Whenever a valid certificate containing a valid hostname is received,
        connection proceeds normally.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
        )
        self.assertEqual(cProto.wrappedProtocol.data,
                         b'greetings!')

        cErr = cProto.wrappedProtocol.lostReason
        sErr = sProto.wrappedProtocol.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)


    def test_validHostnameInvalidCertificate(self):
        """
        When an invalid certificate containing a perfectly valid hostname is
        received, the connection is aborted with an OpenSSL error.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            validCertificate=False,
        )

        self.assertEqual(cProto.wrappedProtocol.data, b'')
        self.assertEqual(sProto.wrappedProtocol.data, b'')

        cErr = cProto.wrappedProtocol.lostReason.value
        sErr = sProto.wrappedProtocol.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)


    def test_realCAsBetterNotSignOurBogusTestCerts(self):
        """
        If we use the default trust from the platform, our dinky certificate
        should I{really} fail.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            validCertificate=False,
            useDefaultTrust=True,
        )

        self.assertEqual(cProto.wrappedProtocol.data, b'')
        self.assertEqual(sProto.wrappedProtocol.data, b'')

        cErr = cProto.wrappedProtocol.lostReason.value
        sErr = sProto.wrappedProtocol.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)


    def test_butIfTheyDidItWouldWork(self):
        """
        L{ssl.optionsForClientTLS} should be using L{ssl.platformTrust} by
        default, so if we fake that out then it should trust ourselves again.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            useDefaultTrust=True,
            fakePlatformTrust=True,
        )
        self.assertEqual(cProto.wrappedProtocol.data,
                         b'greetings!')

        cErr = cProto.wrappedProtocol.lostReason
        sErr = sProto.wrappedProtocol.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)


    def test_clientPresentsCertificate(self):
        """
        When the server verifies and the client presents a valid certificate
        for that verification by passing it to
        L{sslverify.optionsForClientTLS}, communication proceeds.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            validCertificate=True,
            serverVerifies=True,
            clientPresentsCertificate=True,
        )

        self.assertEqual(cProto.wrappedProtocol.data,
                         b'greetings!')

        cErr = cProto.wrappedProtocol.lostReason
        sErr = sProto.wrappedProtocol.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)


    def test_clientPresentsBadCertificate(self):
        """
        When the server verifies and the client presents an invalid certificate
        for that verification by passing it to
        L{sslverify.optionsForClientTLS}, the connection cannot be established
        with an SSL error.
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            validCertificate=True,
            serverVerifies=True,
            validClientCertificate=False,
            clientPresentsCertificate=True,
        )

        self.assertEqual(cProto.wrappedProtocol.data,
                         b'')

        cErr = cProto.wrappedProtocol.lostReason.value
        sErr = sProto.wrappedProtocol.lostReason.value

        self.assertIsInstance(cErr, SSL.Error)
        self.assertIsInstance(sErr, SSL.Error)


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
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"valid.example.com",
            u"valid.example.com",
            setupServerContext
        )
        self.assertEqual(names, [u"valid.example.com"])

    if skipSNI is not None:
        test_hostnameIsIndicated.skip = skipSNI


    def test_hostnameEncoding(self):
        """
        Hostnames are encoded as IDNA.
        """
        names = []
        hello = u"h\N{LATIN SMALL LETTER A WITH ACUTE}llo.example.com"
        def setupServerContext(ctx):
            def servername_received(conn):
                serverIDNA = sslverify._idnaText(conn.get_servername())
                names.append(serverIDNA)
            ctx.set_tlsext_servername_callback(servername_received)
        cProto, sProto, pump = self.serviceIdentitySetup(
            hello, hello, setupServerContext
        )
        self.assertEqual(names, [hello])
        self.assertEqual(cProto.wrappedProtocol.data,
                         b'greetings!')

        cErr = cProto.wrappedProtocol.lostReason
        sErr = sProto.wrappedProtocol.lostReason
        self.assertIsNone(cErr)
        self.assertIsNone(sErr)

    if skipSNI is not None:
        test_hostnameEncoding.skip = skipSNI


    def test_fallback(self):
        """
        L{sslverify.simpleVerifyHostname} checks string equality on the
        commonName of a connection's certificate's subject, doing nothing if it
        matches and raising L{VerificationError} if it doesn't.
        """
        name = 'something.example.com'
        class Connection(object):
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
            sslverify.simpleVerifyHostname(conn, u'something.example.com'),
            None
        )
        self.assertRaises(
            sslverify.SimpleVerificationError,
            sslverify.simpleVerifyHostname, conn, u'nonsense'
        )

    def test_surpriseFromInfoCallback(self):
        """
        pyOpenSSL isn't always so great about reporting errors.  If one occurs
        in the verification info callback, it should be logged and the
        connection should be shut down (if possible, anyway; the app_data could
        be clobbered but there's no point testing for that).
        """
        cProto, sProto, pump = self.serviceIdentitySetup(
            u"correct-host.example.com",
            u"correct-host.example.com",
            buggyInfoCallback=True,
        )
        self.assertEqual(cProto.wrappedProtocol.data, b'')
        self.assertEqual(sProto.wrappedProtocol.data, b'')

        cErr = cProto.wrappedProtocol.lostReason.value
        sErr = sProto.wrappedProtocol.lostReason.value

        self.assertIsInstance(cErr, ZeroDivisionError)
        self.assertIsInstance(sErr, (ConnectionClosed, SSL.Error))
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertTrue(errors)



def negotiateProtocol(serverProtocols,
                      clientProtocols,
                      clientOptions=None):
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
    trustRoot = sslverify.OpenSSLCertificateAuthorities([
        caCertificate.original,
    ])

    sProto, cProto, pump = loopbackTLSConnectionInMemory(
        trustRoot=trustRoot,
        privateKey=serverCertificate.privateKey.original,
        serverCertificate=serverCertificate.original,
        clientProtocols=clientProtocols,
        serverProtocols=serverProtocols,
        clientOptions=clientOptions,
    )
    pump.flush()

    return (cProto.negotiatedProtocol, cProto.wrappedProtocol.lostReason)



class NPNOrALPNTests(unittest.TestCase):
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
        self.assertTrue(
            sslverify.ProtocolNegotiationSupport.NPN in supportedProtocols
        )


    def test_NPNAndALPNSuccess(self):
        """
        When both ALPN and NPN are used, and both the client and server have
        overlapping protocol choices, a protocol is successfully negotiated.
        Further, the negotiated protocol is the first one in the list.
        """
        protocols = [b'h2', b'http/1.1']
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=protocols,
            serverProtocols=protocols,
        )
        self.assertEqual(negotiatedProtocol, b'h2')
        self.assertIsNone(lostReason)


    def test_NPNAndALPNDifferent(self):
        """
        Client and server have different protocol lists: only the common
        element is chosen.
        """
        serverProtocols = [b'h2', b'http/1.1', b'spdy/2']
        clientProtocols = [b'spdy/3', b'http/1.1']
        negotiatedProtocol, lostReason = negotiateProtocol(
            clientProtocols=clientProtocols,
            serverProtocols=serverProtocols,
        )
        self.assertEqual(negotiatedProtocol, b'http/1.1')
        self.assertIsNone(lostReason)


    def test_NPNAndALPNNoAdvertise(self):
        """
        When one peer does not advertise any protocols, the connection is set
        up with no next protocol.
        """
        protocols = [b'h2', b'http/1.1']
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
        clientProtocols = [b'h2', b'http/1.1']
        serverProtocols = [b'spdy/3']
        negotiatedProtocol, lostReason = negotiateProtocol(
            serverProtocols=clientProtocols,
            clientProtocols=serverProtocols,
        )
        self.assertIsNone(negotiatedProtocol)
        self.assertEqual(lostReason.type, SSL.Error)



class ALPNTests(unittest.TestCase):
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
        self.assertTrue(
            sslverify.ProtocolNegotiationSupport.ALPN in
            supportedProtocols
        )



class NPNAndALPNAbsentTests(unittest.TestCase):
    """
    NPN/ALPN operations fail on platforms that do not support them.

    These tests only run on platforms that have a PyOpenSSL version < 0.15,
    or an OpenSSL version earlier than 1.0.1
    """
    if skipSSL:
        skip = skipSSL
    elif not skipNPN:
        skip = "NPN/ALPN is present on this platform"


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
        protocols = [b'h2', b'http/1.1']
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



class ConstructorsTests(unittest.TestCase):
    if skipSSL:
        skip = skipSSL

    def test_peerFromNonSSLTransport(self):
        """
        Verify that peerFromTransport raises an exception if the transport
        passed is not actually an SSL transport.
        """
        x = self.assertRaises(CertificateError,
                              sslverify.Certificate.peerFromTransport,
                              _NotSSLTransport())
        self.assertTrue(str(x).startswith("non-TLS"))


    def test_peerFromBlankSSLTransport(self):
        """
        Verify that peerFromTransport raises an exception if the transport
        passed is an SSL transport, but doesn't have a peer certificate.
        """
        x = self.assertRaises(CertificateError,
                              sslverify.Certificate.peerFromTransport,
                              _MaybeSSLTransport())
        self.assertTrue(str(x).startswith("TLS"))


    def test_hostFromNonSSLTransport(self):
        """
        Verify that hostFromTransport raises an exception if the transport
        passed is not actually an SSL transport.
        """
        x = self.assertRaises(CertificateError,
                              sslverify.Certificate.hostFromTransport,
                              _NotSSLTransport())
        self.assertTrue(str(x).startswith("non-TLS"))


    def test_hostFromBlankSSLTransport(self):
        """
        Verify that hostFromTransport raises an exception if the transport
        passed is an SSL transport, but doesn't have a host certificate.
        """
        x = self.assertRaises(CertificateError,
                              sslverify.Certificate.hostFromTransport,
                              _MaybeSSLTransport())
        self.assertTrue(str(x).startswith("TLS"))


    def test_hostFromSSLTransport(self):
        """
        Verify that hostFromTransport successfully creates the correct
        certificate if passed a valid SSL transport.
        """
        self.assertEqual(
            sslverify.Certificate.hostFromTransport(
                _ActualSSLTransport()).serialNumber(),
            12345)


    def test_peerFromSSLTransport(self):
        """
        Verify that peerFromTransport successfully creates the correct
        certificate if passed a valid SSL transport.
        """
        self.assertEqual(
            sslverify.Certificate.peerFromTransport(
                _ActualSSLTransport()).serialNumber(),
            12346)



class MultipleCertificateTrustRootTests(unittest.TestCase):
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
        sProto, cProto, pump = loopbackTLSConnectionInMemory(
            trustRoot=mt,
            privateKey=privateCert.privateKey.original,
            serverCertificate=privateCert.original,
        )

        # This connection should succeed
        self.assertEqual(cProto.wrappedProtocol.data, b'greetings!')
        self.assertIsNone(cProto.wrappedProtocol.lostReason)


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
        sProto, cProto, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=selfSigned.privateKey.original,
            serverCertificate=selfSigned.original,
        )
        self.assertEqual(cProto.wrappedProtocol.data, b'greetings!')
        self.assertIsNone(cProto.wrappedProtocol.lostReason)


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
        sProto, cProto, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=serverCert.privateKey.original,
            serverCertificate=serverCert.original,
        )
        self.assertEqual(cProto.wrappedProtocol.data, b'greetings!')
        self.assertIsNone(cProto.wrappedProtocol.lostReason)


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
        sProto, cProto, pump = loopbackTLSConnectionInMemory(
            trustRoot=trust,
            privateKey=serverCert.privateKey.original,
            serverCertificate=serverCert.original,
        )

        # This connection should fail, so no data was received.
        self.assertEqual(cProto.wrappedProtocol.data, b'')

        # It was an L{SSL.Error}.
        self.assertEqual(cProto.wrappedProtocol.lostReason.type, SSL.Error)

        # Some combination of OpenSSL and PyOpenSSL is bad at reporting errors.
        err = cProto.wrappedProtocol.lostReason.value
        self.assertEqual(err.args[0][0][2], 'tlsv1 alert unknown ca')


    def test_trustRootFromCertificatesOpenSSLObjects(self):
        """
        L{trustRootFromCertificates} rejects any L{OpenSSL.crypto.X509}
        instances in the list passed to it.
        """
        private = sslverify.PrivateCertificate.loadPEM(A_KEYPAIR)
        certX509 = private.original

        exception = self.assertRaises(
            TypeError,
            sslverify.trustRootFromCertificates, [certX509],
        )
        self.assertEqual(
            "certificates items must be twisted.internet.ssl.CertBase "
            "instances",
            exception.args[0],
        )



class OpenSSLCipherTests(unittest.TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLCipher.
    """
    if skipSSL:
        skip = skipSSL

    cipherName = u'CIPHER-STRING'

    def test_constructorSetsFullName(self):
        """
        The first argument passed to the constructor becomes the full name.
        """
        self.assertEqual(
            self.cipherName,
            sslverify.OpenSSLCipher(self.cipherName).fullName
        )


    def test_repr(self):
        """
        C{repr(cipher)} returns a valid constructor call.
        """
        cipher = sslverify.OpenSSLCipher(self.cipherName)
        self.assertEqual(
            cipher,
            eval(repr(cipher), {'OpenSSLCipher': sslverify.OpenSSLCipher})
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
        class DifferentCipher(object):
            fullName = self.cipherName

        self.assertNotEqual(
            sslverify.OpenSSLCipher(self.cipherName),
            DifferentCipher(),
        )



class ExpandCipherStringTests(unittest.TestCase):
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
            [],
            sslverify._expandCipherString(u'', SSL.SSLv23_METHOD, 0)
        )


    def test_doesNotSwallowOtherSSLErrors(self):
        """
        Only no cipher matches get swallowed, every other SSL error gets
        propagated.
        """
        def raiser(_):
            # Unfortunately, there seems to be no way to trigger a real SSL
            # error artificially.
            raise SSL.Error([['', '', '']])
        ctx = FakeContext(SSL.SSLv23_METHOD)
        ctx.set_cipher_list = raiser
        self.patch(sslverify.SSL, 'Context', lambda _: ctx)
        self.assertRaises(
            SSL.Error,
            sslverify._expandCipherString, u'ALL', SSL.SSLv23_METHOD, 0
        )


    def test_returnsListOfICiphers(self):
        """
        L{sslverify._expandCipherString} always returns a L{list} of
        L{interfaces.ICipher}.
        """
        ciphers = sslverify._expandCipherString(u'ALL', SSL.SSLv23_METHOD, 0)
        self.assertIsInstance(ciphers, list)
        bogus = []
        for c in ciphers:
            if not interfaces.ICipher.providedBy(c):
                bogus.append(c)

        self.assertEqual([], bogus)



class AcceptableCiphersTests(unittest.TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLAcceptableCiphers.
    """
    if skipSSL:
        skip = skipSSL

    def test_selectOnEmptyListReturnsEmptyList(self):
        """
        If no ciphers are available, nothing can be selected.
        """
        ac = sslverify.OpenSSLAcceptableCiphers([])
        self.assertEqual([], ac.selectCiphers([]))


    def test_selectReturnsOnlyFromAvailable(self):
        """
        Select only returns a cross section of what is available and what is
        desirable.
        """
        ac = sslverify.OpenSSLAcceptableCiphers([
            sslverify.OpenSSLCipher('A'),
            sslverify.OpenSSLCipher('B'),
        ])
        self.assertEqual([sslverify.OpenSSLCipher('B')],
                         ac.selectCiphers([sslverify.OpenSSLCipher('B'),
                                           sslverify.OpenSSLCipher('C')]))


    def test_fromOpenSSLCipherStringExpandsToListOfCiphers(self):
        """
        If L{sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString} is
        called it expands the string to a list of ciphers.
        """
        ac = sslverify.OpenSSLAcceptableCiphers.fromOpenSSLCipherString('ALL')
        self.assertIsInstance(ac._ciphers, list)
        self.assertTrue(all(sslverify.ICipher.providedBy(c)
                            for c in ac._ciphers))



class DiffieHellmanParametersTests(unittest.TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLDHParameters.
    """
    if skipSSL:
        skip = skipSSL
    filePath = FilePath(b'dh.params')

    def test_fromFile(self):
        """
        Calling C{fromFile} with a filename returns an instance with that file
        name saved.
        """
        params = sslverify.OpenSSLDiffieHellmanParameters.fromFile(
            self.filePath
        )
        self.assertEqual(self.filePath, params._dhFile)



class FakeECKey(object):
    """
    An introspectable fake of a key.

    @ivar _nid: A free form nid.
    """
    def __init__(self, nid):
        self._nid = nid



class FakeNID(object):
    """
    An introspectable fake of a NID.

    @ivar _snName: A free form sn name.
    """
    def __init__(self, snName):
        self._snName = snName



class FakeLib(object):
    """
    An introspectable fake of cryptography's lib object.

    @ivar _createdKey: A set of keys that have been created by this instance.
    @type _createdKey: L{set} of L{FakeKey}

    @cvar NID_undef: A symbolic constant for undefined NIDs.
    @type NID_undef: L{FakeNID}
    """
    NID_undef = FakeNID("undef")

    def __init__(self):
        self._createdKeys = set()


    def OBJ_sn2nid(self, snName):
        """
        Create a L{FakeNID} with C{snName} and return it.

        @param snName: a free form name that gets passed to the constructor
            of L{FakeNID}.

        @return: a new L{FakeNID}.
        @rtype: L{FakeNID}.
        """
        return FakeNID(snName)


    def EC_KEY_new_by_curve_name(self, nid):
        """
        Create a L{FakeECKey}, save it to C{_createdKeys} and return it.

        @param nid: an arbitrary object that is passed to the constructor of
            L{FakeECKey}.

        @return: a new L{FakeECKey}
        @rtype: L{FakeECKey}
        """
        key = FakeECKey(nid)
        self._createdKeys.add(key)
        return key


    def EC_KEY_free(self, key):
        """
        Remove C{key} from C{_createdKey}.

        @param key: a key object to be freed; i.e. removed from
            C{_createdKeys}.

        @raises ValueError: If C{key} is not in C{_createdKeys} and thus not
            created by us.
        """
        try:
            self._createdKeys.remove(key)
        except KeyError:
            raise ValueError("Unallocated EC key attempted to free.")


    def SSL_CTX_set_tmp_ecdh(self, ffiContext, key):
        """
        Does not do anything.

        @param ffiContext: ignored
        @param key: ignored
        """



class FakeLibTests(unittest.TestCase):
    """
    Tests for FakeLib
    """
    def test_objSn2Nid(self):
        """
        Returns a L{FakeNID} with correct name.
        """
        nid = FakeNID("test")
        self.assertEqual("test", nid._snName)


    def test_emptyKeys(self):
        """
        A new L{FakeLib} has an empty set for created keys.
        """
        self.assertEqual(set(), FakeLib()._createdKeys)


    def test_newKey(self):
        """
        If a new key is created, it's added to C{_createdKeys}.
        """
        lib = FakeLib()
        key = lib.EC_KEY_new_by_curve_name(FakeNID("name"))
        self.assertEqual(set([key]), lib._createdKeys)


    def test_freeUnknownKey(self):
        """
        Raise L{ValueError} if an unknown key is attempted to be freed.
        """
        key = FakeECKey(object())
        self.assertRaises(
            ValueError,
            FakeLib().EC_KEY_free, key
        )


    def test_freeKnownKey(self):
        """
        Freeing an allocated key removes it from C{_createdKeys}.
        """
        lib = FakeLib()
        key = lib.EC_KEY_new_by_curve_name(FakeNID("name"))
        lib.EC_KEY_free(key)
        self.assertEqual(set(), lib._createdKeys)



class FakeFFI(object):
    """
    A fake of a cryptography's ffi object.

    @cvar NULL: Symbolic constant for CFFI's NULL objects.
    """
    NULL = object()



class FakeBinding(object):
    """
    A fake of cryptography's binding object.

    @type lib: L{FakeLib}
    @type ffi: L{FakeFFI}
    """
    def __init__(self, lib=None, ffi=None):
        self.lib = lib or FakeLib()
        self.ffi = ffi or FakeFFI()



class ECCurveTests(unittest.TestCase):
    """
    Tests for twisted.internet._sslverify.OpenSSLECCurve.
    """
    if skipSSL:
        skip = skipSSL

    def test_missingBinding(self):
        """
        Raise L{NotImplementedError} if pyOpenSSL is not based on cryptography.
        """
        def raiser(self):
            raise NotImplementedError
        self.patch(sslverify._OpenSSLECCurve, "_getBinding", raiser)
        self.assertRaises(
            NotImplementedError,
            sslverify._OpenSSLECCurve, sslverify._defaultCurveName,
        )


    def test_nonECbinding(self):
        """
        Raise L{NotImplementedError} if pyOpenSSL is based on cryptography but
        cryptography lacks required EC methods.
        """
        def raiser(self):
            raise AttributeError
        lib = FakeLib()
        lib.OBJ_sn2nid = raiser
        self.patch(sslverify._OpenSSLECCurve,
                   "_getBinding",
                   lambda self: FakeBinding(lib=lib))
        self.assertRaises(
            NotImplementedError,
            sslverify._OpenSSLECCurve, sslverify._defaultCurveName,
        )


    def test_wrongName(self):
        """
        Raise L{ValueError} on unknown sn names.
        """
        lib = FakeLib()
        lib.OBJ_sn2nid = lambda self: FakeLib.NID_undef
        self.patch(sslverify._OpenSSLECCurve,
                   "_getBinding",
                   lambda self: FakeBinding(lib=lib))
        self.assertRaises(
            ValueError,
            sslverify._OpenSSLECCurve, u"doesNotExist",
        )


    def test_keyFails(self):
        """
        Raise L{EnvironmentError} if key creation fails.
        """
        lib = FakeLib()
        lib.EC_KEY_new_by_curve_name = lambda *a, **kw: FakeFFI.NULL
        self.patch(sslverify._OpenSSLECCurve,
                   "_getBinding",
                   lambda self: FakeBinding(lib=lib))
        curve = sslverify._OpenSSLECCurve(sslverify._defaultCurveName)
        self.assertRaises(
            EnvironmentError,
            curve.addECKeyToContext, object()
        )


    def test_keyGetsFreed(self):
        """
        Don't leak a key when adding it to a context.
        """
        lib = FakeLib()
        self.patch(sslverify._OpenSSLECCurve,
                   "_getBinding",
                   lambda self: FakeBinding(lib=lib))
        curve = sslverify._OpenSSLECCurve(sslverify._defaultCurveName)
        ctx = FakeContext(None)
        ctx._context = None
        curve.addECKeyToContext(ctx)
        self.assertEqual(set(), lib._createdKeys)



class KeyPairTests(unittest.TestCase):
    """
    Tests for L{sslverify.KeyPair}.
    """
    if skipSSL:
        skip = skipSSL

    def setUp(self):
        """
        Create test certificate.
        """
        self.sKey = makeCertificate(
            O=b"Server Test Certificate",
            CN=b"server")[0]


    def test_getstateDeprecation(self):
        """
        L{sslverify.KeyPair.__getstate__} is deprecated.
        """
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.KeyPair(self.sKey).__getstate__)


    def test_setstateDeprecation(self):
        """
        {sslverify.KeyPair.__setstate__} is deprecated.
        """
        state = sslverify.KeyPair(self.sKey).dump()
        self.callDeprecated(
            (Version("Twisted", 15, 0, 0), "a real persistence system"),
            sslverify.KeyPair(self.sKey).__setstate__, state)



class OpenSSLVersionTestsMixin(object):
    """
    A mixin defining tests relating to the version declaration interface of
    I{pyOpenSSL}.

    This is used to verify that the fake I{OpenSSL} module presents its fake
    version information in the same way as the real L{OpenSSL} module.
    """
    def test_string(self):
        """
        C{OpenSSL.__version__} is a native string.
        """
        self.assertIsInstance(self.OpenSSL.__version__, str)


    def test_majorDotMinor(self):
        """
        C{OpenSSL.__version__} declares the major and minor versions as
        non-negative integers separated by C{"."}.
        """
        parts = self.OpenSSL.__version__.split(".")
        major = int(parts[0])
        minor = int(parts[1])
        self.assertEqual(
            (True, True),
            (major >= 0, minor >= 0))



class RealOpenSSLTests(OpenSSLVersionTestsMixin, unittest.SynchronousTestCase):
    """
    Apply the pyOpenSSL version tests to the real C{OpenSSL} package.
    """
    if skipSSL is None:
        OpenSSL = OpenSSL
    else:
        skip = skipSSL



class PreTwelveDummyOpenSSLTests(OpenSSLVersionTestsMixin,
                                 unittest.SynchronousTestCase):
    """
    Apply the pyOpenSSL version tests to an instance of L{DummyOpenSSL} that
    pretends to be older than 0.12.
    """
    OpenSSL = _preTwelveOpenSSL



class PostTwelveDummyOpenSSLTests(OpenSSLVersionTestsMixin,
                                  unittest.SynchronousTestCase):
    """
    Apply the pyOpenSSL version tests to an instance of L{DummyOpenSSL} that
    pretends to be newer than 0.12.
    """
    OpenSSL = _postTwelveOpenSSL



class UsablePyOpenSSLTests(unittest.SynchronousTestCase):
    """
    Tests for L{UsablePyOpenSSLTests}.
    """
    if skipSSL is not None:
        skip = skipSSL

    def test_ok(self):
        """
        Return C{True} for usable versions including possible changes in
        versioning.
        """
        for version in ["0.15.1", "1.0.0", "16.0.0"]:
            self.assertTrue(sslverify._usablePyOpenSSL(version))

    def test_tooOld(self):
        """
        Return C{False} for unusable versions.
        """
        self.assertFalse(sslverify._usablePyOpenSSL("0.11.1"))

    def test_inDev(self):
        """
        A .dev0 suffix does not trip us up.  Since it has been introduced after
        0.15.1, it's always C{True}.
        """
        for version in ["0.16.0", "1.0.0", "16.0.0"]:
            self.assertTrue(sslverify._usablePyOpenSSL(version + ".dev0"))



class SelectVerifyImplementationTests(unittest.SynchronousTestCase):
    """
    Tests for L{_selectVerifyImplementation}.
    """
    if skipSSL is not None:
        skip = skipSSL

    def test_pyOpenSSLTooOld(self):
        """
        If the version of I{pyOpenSSL} installed is older than 0.12 then
        L{_selectVerifyImplementation} returns L{simpleVerifyHostname} and
        L{SimpleVerificationError}.
        """
        result = sslverify._selectVerifyImplementation(_preTwelveOpenSSL)
        expected = (
            sslverify.simpleVerifyHostname, sslverify.SimpleVerificationError)
        self.assertEqual(expected, result)
    test_pyOpenSSLTooOld.suppress = [
        util.suppress(
            message="Your version of pyOpenSSL, 0.11, is out of date."),
        ]


    def test_pyOpenSSLTooOldWarning(self):
        """
        If the version of I{pyOpenSSL} installed is older than 0.12 then
        L{_selectVerifyImplementation} emits a L{UserWarning} advising the user
        to upgrade.
        """
        sslverify._selectVerifyImplementation(_preTwelveOpenSSL)
        [warning] = list(
            warning
            for warning
            in self.flushWarnings()
            if warning["category"] == UserWarning)

        expectedMessage = (
            "Your version of pyOpenSSL, 0.11, is out of date.  Please upgrade "
            "to at least 0.12 and install service_identity from "
            "<https://pypi.python.org/pypi/service_identity>.  Without the "
            "service_identity module and a recent enough pyOpenSSL to support "
            "it, Twisted can perform only rudimentary TLS client hostname "
            "verification.  Many valid certificate/hostname mappings may be "
            "rejected.")

        self.assertEqual(
            (warning["message"], warning["filename"], warning["lineno"]),
            # Make sure we're abusing the warning system to a sufficient
            # degree: there is no filename or line number that makes sense for
            # this warning to "blame" for the problem.  It is a system
            # misconfiguration.  So the location information should be blank
            # (or as blank as we can make it).
            (expectedMessage, "", 0))


    def test_dependencyMissing(self):
        """
        If I{service_identity} cannot be imported then
        L{_selectVerifyImplementation} returns L{simpleVerifyHostname} and
        L{SimpleVerificationError}.
        """
        with SetAsideModule("service_identity"):
            sys.modules["service_identity"] = None

            result = sslverify._selectVerifyImplementation(_postTwelveOpenSSL)
            expected = (
                sslverify.simpleVerifyHostname,
                sslverify.SimpleVerificationError)
            self.assertEqual(expected, result)
    test_dependencyMissing.suppress = [
        util.suppress(
            message=(
                "You do not have a working installation of the "
                "service_identity module"),
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

            sslverify._selectVerifyImplementation(_postTwelveOpenSSL)

        [warning] = list(
            warning
            for warning
            in self.flushWarnings()
            if warning["category"] == UserWarning)

        if _PY3:
            importError = (
                "'import of 'service_identity' halted; None in sys.modules'")
        else:
            importError = "'No module named service_identity'"

        expectedMessage = (
            "You do not have a working installation of the "
            "service_identity module: {message}.  Please install it from "
            "<https://pypi.python.org/pypi/service_identity> "
            "and make sure all of its dependencies are satisfied.  "
            "Without the service_identity module and a recent enough "
            "pyOpenSSL to support it, Twisted can perform only "
            "rudimentary TLS client hostname verification.  Many valid "
            "certificate/hostname mappings may be rejected.").format(
                message=importError)

        self.assertEqual(
            (warning["message"], warning["filename"], warning["lineno"]),
            # See the comment in test_pyOpenSSLTooOldWarning.
            (expectedMessage, "", 0))
