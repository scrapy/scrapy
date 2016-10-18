# -*- test-case-name: twisted.test.test_sslverify -*-
# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import itertools
import warnings

from hashlib import md5

import OpenSSL
from OpenSSL import SSL, crypto
try:
    from OpenSSL.SSL import SSL_CB_HANDSHAKE_DONE, SSL_CB_HANDSHAKE_START
except ImportError:
    SSL_CB_HANDSHAKE_START = 0x10
    SSL_CB_HANDSHAKE_DONE = 0x20

from twisted.python import log


def _cantSetHostnameIndication(connection, hostname):
    """
    The option to set SNI is not available, so do nothing.

    @param connection: the connection
    @type connection: L{OpenSSL.SSL.Connection}

    @param hostname: the server's host name
    @type: hostname: L{bytes}
    """



def _setHostNameIndication(connection, hostname):
    """
    Set the server name indication on the given client connection to the given
    value.

    @param connection: the connection
    @type connection: L{OpenSSL.SSL.Connection}

    @param hostname: the server's host name
    @type: hostname: L{bytes}
    """
    connection.set_tlsext_host_name(hostname)



if getattr(SSL.Connection, "set_tlsext_host_name", None) is None:
    _maybeSetHostNameIndication = _cantSetHostnameIndication
else:
    _maybeSetHostNameIndication = _setHostNameIndication



class SimpleVerificationError(Exception):
    """
    Not a very useful verification error.
    """



def _idnaBytes(text):
    """
    Convert some text typed by a human into some ASCII bytes.

    This is provided to allow us to use the U{partially-broken IDNA
    implementation in the standard library <http://bugs.python.org/issue17305>}
    if the more-correct U{idna <https://pypi.python.org/pypi/idna>} package is
    not available; C{service_identity} is somewhat stricter about this.

    @param text: A domain name, hopefully.
    @type text: L{unicode}

    @return: The domain name's IDNA representation, encoded as bytes.
    @rtype: L{bytes}
    """
    try:
        import idna
    except ImportError:
        return text.encode("idna")
    else:
        return idna.encode(text)



def _idnaText(octets):
    """
    Convert some IDNA-encoded octets into some human-readable text.

    Currently only used by the tests.

    @param octets: Some bytes representing a hostname.
    @type octets: L{bytes}

    @return: A human-readable domain name.
    @rtype: L{unicode}
    """
    try:
        import idna
    except ImportError:
        return octets.decode("idna")
    else:
        return idna.decode(octets)



def simpleVerifyHostname(connection, hostname):
    """
    Check only the common name in the certificate presented by the peer and
    only for an exact match.

    This is to provide I{something} in the way of hostname verification to
    users who haven't upgraded past OpenSSL 0.12 or installed
    C{service_identity}.  This check is overly strict, relies on a deprecated
    TLS feature (you're supposed to ignore the commonName if the
    subjectAlternativeName extensions are present, I believe), and lots of
    valid certificates will fail.

    @param connection: the OpenSSL connection to verify.
    @type connection: L{OpenSSL.SSL.Connection}

    @param hostname: The hostname expected by the user.
    @type hostname: L{unicode}

    @raise twisted.internet.ssl.VerificationError: if the common name and
        hostname don't match.
    """
    commonName = connection.get_peer_certificate().get_subject().commonName
    if commonName != hostname:
        raise SimpleVerificationError(repr(commonName) + "!=" +
                                      repr(hostname))



def _usablePyOpenSSL(version):
    """
    Check pyOpenSSL version string whether we can use it for host verification.

    @param version: A pyOpenSSL version string.
    @type version: L{str}

    @rtype: L{bool}
    """
    major, minor = (int(part) for part in version.split(".")[:2])
    return (major, minor) >= (0, 12)



def _selectVerifyImplementation(lib):
    """
    U{service_identity <https://pypi.python.org/pypi/service_identity>}
    requires pyOpenSSL 0.12 or better but our dependency is still back at 0.10.
    Determine if pyOpenSSL has the requisite feature, and whether
    C{service_identity} is installed.  If so, use it.  If not, use simplistic
    and incorrect checking as implemented in L{simpleVerifyHostname}.

    @param lib: The L{OpenSSL} module.  This is necessary to determine whether
        certain fallback implementation strategies will be necessary.
    @type lib: L{types.ModuleType}

    @return: 2-tuple of (C{verify_hostname}, C{VerificationError})
    @rtype: L{tuple}
    """

    whatsWrong = (
        "Without the service_identity module and a recent enough pyOpenSSL to "
        "support it, Twisted can perform only rudimentary TLS client hostname "
        "verification.  Many valid certificate/hostname mappings may be "
        "rejected."
    )

    if _usablePyOpenSSL(lib.__version__):
        try:
            from service_identity import VerificationError
            from service_identity.pyopenssl import verify_hostname
            return verify_hostname, VerificationError
        except ImportError as e:
            warnings.warn_explicit(
                "You do not have a working installation of the "
                "service_identity module: '" + str(e) + "'.  "
                "Please install it from "
                "<https://pypi.python.org/pypi/service_identity> and make "
                "sure all of its dependencies are satisfied.  "
                + whatsWrong,
                # Unfortunately the lineno is required.
                category=UserWarning, filename="", lineno=0)
    else:
        warnings.warn_explicit(
            "Your version of pyOpenSSL, {0}, is out of date.  "
            "Please upgrade to at least 0.12 and install service_identity "
            "from <https://pypi.python.org/pypi/service_identity>.  "
            .format(lib.__version__) + whatsWrong,
            # Unfortunately the lineno is required.
            category=UserWarning, filename="", lineno=0)

    return simpleVerifyHostname, SimpleVerificationError


verifyHostname, VerificationError = _selectVerifyImplementation(OpenSSL)


from zope.interface import Interface, implementer

from twisted.internet.defer import Deferred
from twisted.internet.error import VerifyError, CertificateError
from twisted.internet.interfaces import (
    IAcceptableCiphers, ICipher, IOpenSSLClientConnectionCreator,
    IOpenSSLContextFactory
)

from twisted.python import reflect, util
from twisted.python.deprecate import _mutuallyExclusiveArguments
from twisted.python.compat import nativeString, networkString, unicode
from twisted.python.constants import Flags, FlagConstant
from twisted.python.failure import Failure
from twisted.python.util import FancyEqMixin

from twisted.python.deprecate import deprecated
from twisted.python.versions import Version


def _sessionCounter(counter=itertools.count()):
    """
    Private - shared between all OpenSSLCertificateOptions, counts up to
    provide a unique session id for each context.
    """
    return next(counter)



class ProtocolNegotiationSupport(Flags):
    """
    L{ProtocolNegotiationSupport} defines flags which are used to indicate the
    level of NPN/ALPN support provided by the TLS backend.

    @cvar NOSUPPORT: There is no support for NPN or ALPN. This is exclusive
        with both L{NPN} and L{ALPN}.
    @cvar NPN: The implementation supports Next Protocol Negotiation.
    @cvar ALPN: The implementation supports Application Layer Protocol
        Negotiation.
    """
    NPN = FlagConstant(0x0001)
    ALPN = FlagConstant(0x0002)

# FIXME: https://twistedmatrix.com/trac/ticket/8074
# Currently flags with literal zero values behave incorrectly. However,
# creating a flag by NOTing a flag with itself appears to work totally fine, so
# do that instead.
ProtocolNegotiationSupport.NOSUPPORT = (
    ProtocolNegotiationSupport.NPN ^ ProtocolNegotiationSupport.NPN
)


def protocolNegotiationMechanisms():
    """
    Checks whether your versions of PyOpenSSL and OpenSSL are recent enough to
    support protocol negotiation, and if they are, what kind of protocol
    negotiation is supported.

    @return: A combination of flags from L{ProtocolNegotiationSupport} that
        indicate which mechanisms for protocol negotiation are supported.
    @rtype: L{FlagConstant}
    """
    support = ProtocolNegotiationSupport.NOSUPPORT
    ctx = SSL.Context(SSL.SSLv23_METHOD)

    try:
        ctx.set_npn_advertise_callback(lambda c: None)
    except (AttributeError, NotImplementedError):
        pass
    else:
        support |= ProtocolNegotiationSupport.NPN

    try:
        ctx.set_alpn_select_callback(lambda c: None)
    except (AttributeError, NotImplementedError):
        pass
    else:
        support |= ProtocolNegotiationSupport.ALPN

    return support



_x509names = {
    'CN': 'commonName',
    'commonName': 'commonName',

    'O': 'organizationName',
    'organizationName': 'organizationName',

    'OU': 'organizationalUnitName',
    'organizationalUnitName': 'organizationalUnitName',

    'L': 'localityName',
    'localityName': 'localityName',

    'ST': 'stateOrProvinceName',
    'stateOrProvinceName': 'stateOrProvinceName',

    'C': 'countryName',
    'countryName': 'countryName',

    'emailAddress': 'emailAddress'}



class DistinguishedName(dict):
    """
    Identify and describe an entity.

    Distinguished names are used to provide a minimal amount of identifying
    information about a certificate issuer or subject.  They are commonly
    created with one or more of the following fields::

        commonName (CN)
        organizationName (O)
        organizationalUnitName (OU)
        localityName (L)
        stateOrProvinceName (ST)
        countryName (C)
        emailAddress

    A L{DistinguishedName} should be constructed using keyword arguments whose
    keys can be any of the field names above (as a native string), and the
    values are either Unicode text which is encodable to ASCII, or L{bytes}
    limited to the ASCII subset. Any fields passed to the constructor will be
    set as attributes, accessible using both their extended name and their
    shortened acronym. The attribute values will be the ASCII-encoded
    bytes. For example::

        >>> dn = DistinguishedName(commonName=b'www.example.com',
        ...                        C='US')
        >>> dn.C
        b'US'
        >>> dn.countryName
        b'US'
        >>> hasattr(dn, "organizationName")
        False

    L{DistinguishedName} instances can also be used as dictionaries; the keys
    are extended name of the fields::

        >>> dn.keys()
        ['countryName', 'commonName']
        >>> dn['countryName']
        b'US'

    """
    __slots__ = ()

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


    def _copyFrom(self, x509name):
        for name in _x509names:
            value = getattr(x509name, name, None)
            if value is not None:
                setattr(self, name, value)


    def _copyInto(self, x509name):
        for k, v in self.items():
            setattr(x509name, k, nativeString(v))


    def __repr__(self):
        return '<DN %s>' % (dict.__repr__(self)[1:-1])


    def __getattr__(self, attr):
        try:
            return self[_x509names[attr]]
        except KeyError:
            raise AttributeError(attr)


    def __setattr__(self, attr, value):
        if attr not in _x509names:
            raise AttributeError("%s is not a valid OpenSSL X509 name field" % (attr,))
        realAttr = _x509names[attr]
        if not isinstance(value, bytes):
            value = value.encode("ascii")
        self[realAttr] = value


    def inspect(self):
        """
        Return a multi-line, human-readable representation of this DN.

        @rtype: L{str}
        """
        l = []
        lablen = 0
        def uniqueValues(mapping):
            return set(mapping.values())
        for k in sorted(uniqueValues(_x509names)):
            label = util.nameToLabel(k)
            lablen = max(len(label), lablen)
            v = getattr(self, k, None)
            if v is not None:
                l.append((label, nativeString(v)))
        lablen += 2
        for n, (label, attr) in enumerate(l):
            l[n] = (label.rjust(lablen)+': '+ attr)
        return '\n'.join(l)

DN = DistinguishedName



class CertBase:
    """
    Base class for public (certificate only) and private (certificate + key
    pair) certificates.

    @ivar original: The underlying OpenSSL certificate object.
    @type original: L{OpenSSL.crypto.X509}
    """

    def __init__(self, original):
        self.original = original


    def _copyName(self, suffix):
        dn = DistinguishedName()
        dn._copyFrom(getattr(self.original, 'get_'+suffix)())
        return dn


    def getSubject(self):
        """
        Retrieve the subject of this certificate.

        @return: A copy of the subject of this certificate.
        @rtype: L{DistinguishedName}
        """
        return self._copyName('subject')


    def __conform__(self, interface):
        """
        Convert this L{CertBase} into a provider of the given interface.

        @param interface: The interface to conform to.
        @type interface: L{zope.interface.interfaces.IInterface}

        @return: an L{IOpenSSLTrustRoot} provider or L{NotImplemented}
        @rtype: L{IOpenSSLTrustRoot} or L{NotImplemented}
        """
        if interface is IOpenSSLTrustRoot:
            return OpenSSLCertificateAuthorities([self.original])
        return NotImplemented



def _handleattrhelper(Class, transport, methodName):
    """
    (private) Helper for L{Certificate.peerFromTransport} and
    L{Certificate.hostFromTransport} which checks for incompatible handle types
    and null certificates and raises the appropriate exception or returns the
    appropriate certificate object.
    """
    method = getattr(transport.getHandle(),
                     "get_%s_certificate" % (methodName,), None)
    if method is None:
        raise CertificateError(
            "non-TLS transport %r did not have %s certificate" % (transport, methodName))
    cert = method()
    if cert is None:
        raise CertificateError(
            "TLS transport %r did not have %s certificate" % (transport, methodName))
    return Class(cert)


class Certificate(CertBase):
    """
    An x509 certificate.
    """
    def __repr__(self):
        return '<%s Subject=%s Issuer=%s>' % (self.__class__.__name__,
                                              self.getSubject().commonName,
                                              self.getIssuer().commonName)

    def __eq__(self, other):
        if isinstance(other, Certificate):
            return self.dump() == other.dump()
        return False


    def __ne__(self, other):
        return not self.__eq__(other)


    def load(Class, requestData, format=crypto.FILETYPE_ASN1, args=()):
        """
        Load a certificate from an ASN.1- or PEM-format string.

        @rtype: C{Class}
        """
        return Class(crypto.load_certificate(format, requestData), *args)
    load = classmethod(load)
    _load = load


    def dumpPEM(self):
        """
        Dump this certificate to a PEM-format data string.

        @rtype: L{str}
        """
        return self.dump(crypto.FILETYPE_PEM)


    def loadPEM(Class, data):
        """
        Load a certificate from a PEM-format data string.

        @rtype: C{Class}
        """
        return Class.load(data, crypto.FILETYPE_PEM)
    loadPEM = classmethod(loadPEM)


    def peerFromTransport(Class, transport):
        """
        Get the certificate for the remote end of the given transport.

        @param transport: an L{ISystemHandle} provider

        @rtype: C{Class}

        @raise: L{CertificateError}, if the given transport does not have a peer
            certificate.
        """
        return _handleattrhelper(Class, transport, 'peer')
    peerFromTransport = classmethod(peerFromTransport)


    def hostFromTransport(Class, transport):
        """
        Get the certificate for the local end of the given transport.

        @param transport: an L{ISystemHandle} provider; the transport we will

        @rtype: C{Class}

        @raise: L{CertificateError}, if the given transport does not have a host
            certificate.
        """
        return _handleattrhelper(Class, transport, 'host')
    hostFromTransport = classmethod(hostFromTransport)


    def getPublicKey(self):
        """
        Get the public key for this certificate.

        @rtype: L{PublicKey}
        """
        return PublicKey(self.original.get_pubkey())


    def dump(self, format=crypto.FILETYPE_ASN1):
        return crypto.dump_certificate(format, self.original)


    def serialNumber(self):
        """
        Retrieve the serial number of this certificate.

        @rtype: L{int}
        """
        return self.original.get_serial_number()


    def digest(self, method='md5'):
        """
        Return a digest hash of this certificate using the specified hash
        algorithm.

        @param method: One of C{'md5'} or C{'sha'}.

        @return: The digest of the object, formatted as b":"-delimited hex pairs
        @rtype: L{bytes}
        """
        return self.original.digest(method)


    def _inspect(self):
        return '\n'.join(['Certificate For Subject:',
                          self.getSubject().inspect(),
                          '\nIssuer:',
                          self.getIssuer().inspect(),
                          '\nSerial Number: %d' % self.serialNumber(),
                          'Digest: %s' % nativeString(self.digest())])


    def inspect(self):
        """
        Return a multi-line, human-readable representation of this
        Certificate, including information about the subject, issuer, and
        public key.
        """
        return '\n'.join((self._inspect(), self.getPublicKey().inspect()))


    def getIssuer(self):
        """
        Retrieve the issuer of this certificate.

        @rtype: L{DistinguishedName}
        @return: A copy of the issuer of this certificate.
        """
        return self._copyName('issuer')


    def options(self, *authorities):
        raise NotImplementedError('Possible, but doubtful we need this yet')



class CertificateRequest(CertBase):
    """
    An x509 certificate request.

    Certificate requests are given to certificate authorities to be signed and
    returned resulting in an actual certificate.
    """
    def load(Class, requestData, requestFormat=crypto.FILETYPE_ASN1):
        req = crypto.load_certificate_request(requestFormat, requestData)
        dn = DistinguishedName()
        dn._copyFrom(req.get_subject())
        if not req.verify(req.get_pubkey()):
            raise VerifyError("Can't verify that request for %r is self-signed." % (dn,))
        return Class(req)
    load = classmethod(load)


    def dump(self, format=crypto.FILETYPE_ASN1):
        return crypto.dump_certificate_request(format, self.original)



class PrivateCertificate(Certificate):
    """
    An x509 certificate and private key.
    """
    def __repr__(self):
        return Certificate.__repr__(self) + ' with ' + repr(self.privateKey)


    def _setPrivateKey(self, privateKey):
        if not privateKey.matches(self.getPublicKey()):
            raise VerifyError(
                "Certificate public and private keys do not match.")
        self.privateKey = privateKey
        return self


    def newCertificate(self, newCertData, format=crypto.FILETYPE_ASN1):
        """
        Create a new L{PrivateCertificate} from the given certificate data and
        this instance's private key.
        """
        return self.load(newCertData, self.privateKey, format)


    def load(Class, data, privateKey, format=crypto.FILETYPE_ASN1):
        return Class._load(data, format)._setPrivateKey(privateKey)
    load = classmethod(load)


    def inspect(self):
        return '\n'.join([Certificate._inspect(self),
                          self.privateKey.inspect()])


    def dumpPEM(self):
        """
        Dump both public and private parts of a private certificate to
        PEM-format data.
        """
        return self.dump(crypto.FILETYPE_PEM) + self.privateKey.dump(crypto.FILETYPE_PEM)


    def loadPEM(Class, data):
        """
        Load both private and public parts of a private certificate from a
        chunk of PEM-format data.
        """
        return Class.load(data, KeyPair.load(data, crypto.FILETYPE_PEM),
                          crypto.FILETYPE_PEM)
    loadPEM = classmethod(loadPEM)


    def fromCertificateAndKeyPair(Class, certificateInstance, privateKey):
        privcert = Class(certificateInstance.original)
        return privcert._setPrivateKey(privateKey)
    fromCertificateAndKeyPair = classmethod(fromCertificateAndKeyPair)


    def options(self, *authorities):
        """
        Create a context factory using this L{PrivateCertificate}'s certificate
        and private key.

        @param authorities: A list of L{Certificate} object

        @return: A context factory.
        @rtype: L{CertificateOptions <twisted.internet.ssl.CertificateOptions>}
        """
        options = dict(privateKey=self.privateKey.original,
                       certificate=self.original)
        if authorities:
            options.update(dict(trustRoot=OpenSSLCertificateAuthorities(
                [auth.original for auth in authorities]
            )))
        return OpenSSLCertificateOptions(**options)


    def certificateRequest(self, format=crypto.FILETYPE_ASN1,
                           digestAlgorithm='sha256'):
        return self.privateKey.certificateRequest(
            self.getSubject(),
            format,
            digestAlgorithm)


    def signCertificateRequest(self,
                               requestData,
                               verifyDNCallback,
                               serialNumber,
                               requestFormat=crypto.FILETYPE_ASN1,
                               certificateFormat=crypto.FILETYPE_ASN1):
        issuer = self.getSubject()
        return self.privateKey.signCertificateRequest(
            issuer,
            requestData,
            verifyDNCallback,
            serialNumber,
            requestFormat,
            certificateFormat)


    def signRequestObject(self, certificateRequest, serialNumber,
                          secondsToExpiry=60 * 60 * 24 * 365, # One year
                          digestAlgorithm='sha256'):
        return self.privateKey.signRequestObject(self.getSubject(),
                                                 certificateRequest,
                                                 serialNumber,
                                                 secondsToExpiry,
                                                 digestAlgorithm)


class PublicKey:
    """
    A L{PublicKey} is a representation of the public part of a key pair.

    You can't do a whole lot with it aside from comparing it to other
    L{PublicKey} objects.

    @note: If constructing a L{PublicKey} manually, be sure to pass only a
        L{OpenSSL.crypto.PKey} that does not contain a private key!

    @ivar original: The original private key.
    """

    def __init__(self, osslpkey):
        """
        @param osslpkey: The underlying pyOpenSSL key object.
        @type osslpkey: L{OpenSSL.crypto.PKey}
        """
        self.original = osslpkey


    def matches(self, otherKey):
        """
        Does this L{PublicKey} contain the same value as another L{PublicKey}?

        @param otherKey: The key to compare C{self} to.
        @type otherKey: L{PublicKey}

        @return: L{True} if these keys match, L{False} if not.
        @rtype: L{bool}
        """
        return self.keyHash() == otherKey.keyHash()


    # XXX This could be a useful method, but sometimes it triggers a segfault,
    # so we'll steer clear for now.
#     def verifyCertificate(self, certificate):
#         """
#         returns None, or raises a VerifyError exception if the certificate
#         could not be verified.
#         """
#         if not certificate.original.verify(self.original):
#             raise VerifyError("We didn't sign that certificate.")

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.keyHash())


    def keyHash(self):
        """
        Compute a hash of the underlying PKey object.

        The purpose of this method is to allow you to determine if two
        certificates share the same public key; it is not really useful for
        anything else.

        In versions of Twisted prior to 15.0, C{keyHash} used a technique
        involving certificate requests for computing the hash that was not
        stable in the face of changes to the underlying OpenSSL library.

        @return: Return a 32-character hexadecimal string uniquely identifying
            this public key, I{for this version of Twisted}.
        @rtype: native L{str}
        """
        raw = crypto.dump_publickey(crypto.FILETYPE_ASN1, self.original)
        h = md5()
        h.update(raw)
        return h.hexdigest()


    def inspect(self):
        return 'Public Key with Hash: %s' % (self.keyHash(),)



class KeyPair(PublicKey):

    def load(Class, data, format=crypto.FILETYPE_ASN1):
        return Class(crypto.load_privatekey(format, data))
    load = classmethod(load)


    def dump(self, format=crypto.FILETYPE_ASN1):
        return crypto.dump_privatekey(format, self.original)


    def __getstate__(self):
        return self.dump()


    def __setstate__(self, state):
        self.__init__(crypto.load_privatekey(crypto.FILETYPE_ASN1, state))


    def inspect(self):
        t = self.original.type()
        if t == crypto.TYPE_RSA:
            ts = 'RSA'
        elif t == crypto.TYPE_DSA:
            ts = 'DSA'
        else:
            ts = '(Unknown Type!)'
        L = (self.original.bits(), ts, self.keyHash())
        return '%s-bit %s Key Pair with Hash: %s' % L


    def generate(Class, kind=crypto.TYPE_RSA, size=1024):
        pkey = crypto.PKey()
        pkey.generate_key(kind, size)
        return Class(pkey)


    def newCertificate(self, newCertData, format=crypto.FILETYPE_ASN1):
        return PrivateCertificate.load(newCertData, self, format)
    generate = classmethod(generate)


    def requestObject(self, distinguishedName, digestAlgorithm='sha256'):
        req = crypto.X509Req()
        req.set_pubkey(self.original)
        distinguishedName._copyInto(req.get_subject())
        req.sign(self.original, digestAlgorithm)
        return CertificateRequest(req)


    def certificateRequest(self, distinguishedName,
                           format=crypto.FILETYPE_ASN1,
                           digestAlgorithm='sha256'):
        """Create a certificate request signed with this key.

        @return: a string, formatted according to the 'format' argument.
        """
        return self.requestObject(distinguishedName, digestAlgorithm).dump(format)


    def signCertificateRequest(self,
                               issuerDistinguishedName,
                               requestData,
                               verifyDNCallback,
                               serialNumber,
                               requestFormat=crypto.FILETYPE_ASN1,
                               certificateFormat=crypto.FILETYPE_ASN1,
                               secondsToExpiry=60 * 60 * 24 * 365, # One year
                               digestAlgorithm='sha256'):
        """
        Given a blob of certificate request data and a certificate authority's
        DistinguishedName, return a blob of signed certificate data.

        If verifyDNCallback returns a Deferred, I will return a Deferred which
        fires the data when that Deferred has completed.
        """
        hlreq = CertificateRequest.load(requestData, requestFormat)

        dn = hlreq.getSubject()
        vval = verifyDNCallback(dn)

        def verified(value):
            if not value:
                raise VerifyError("DN callback %r rejected request DN %r" % (verifyDNCallback, dn))
            return self.signRequestObject(issuerDistinguishedName, hlreq,
                                          serialNumber, secondsToExpiry, digestAlgorithm).dump(certificateFormat)

        if isinstance(vval, Deferred):
            return vval.addCallback(verified)
        else:
            return verified(vval)


    def signRequestObject(self,
                          issuerDistinguishedName,
                          requestObject,
                          serialNumber,
                          secondsToExpiry=60 * 60 * 24 * 365, # One year
                          digestAlgorithm='sha256'):
        """
        Sign a CertificateRequest instance, returning a Certificate instance.
        """
        req = requestObject.original
        cert = crypto.X509()
        issuerDistinguishedName._copyInto(cert.get_issuer())
        cert.set_subject(req.get_subject())
        cert.set_pubkey(req.get_pubkey())
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(secondsToExpiry)
        cert.set_serial_number(serialNumber)
        cert.sign(self.original, digestAlgorithm)
        return Certificate(cert)


    def selfSignedCert(self, serialNumber, **kw):
        dn = DN(**kw)
        return PrivateCertificate.fromCertificateAndKeyPair(
            self.signRequestObject(dn, self.requestObject(dn), serialNumber),
            self)

KeyPair.__getstate__ = deprecated(Version("Twisted", 15, 0, 0),
    "a real persistence system")(KeyPair.__getstate__)
KeyPair.__setstate__ = deprecated(Version("Twisted", 15, 0, 0),
    "a real persistence system")(KeyPair.__setstate__)



class IOpenSSLTrustRoot(Interface):
    """
    Trust settings for an OpenSSL context.

    Note that this interface's methods are private, so things outside of
    Twisted shouldn't implement it.
    """

    def _addCACertsToContext(context):
        """
        Add certificate-authority certificates to an SSL context whose
        connections should trust those authorities.

        @param context: An SSL context for a connection which should be
            verified by some certificate authority.
        @type context: L{OpenSSL.SSL.Context}

        @return: L{None}
        """



@implementer(IOpenSSLTrustRoot)
class OpenSSLCertificateAuthorities(object):
    """
    Trust an explicitly specified set of certificates, represented by a list of
    L{OpenSSL.crypto.X509} objects.
    """

    def __init__(self, caCerts):
        """
        @param caCerts: The certificate authorities to trust when using this
            object as a C{trustRoot} for L{OpenSSLCertificateOptions}.
        @type caCerts: L{list} of L{OpenSSL.crypto.X509}
        """
        self._caCerts = caCerts


    def _addCACertsToContext(self, context):
        store = context.get_cert_store()
        for cert in self._caCerts:
            store.add_cert(cert)



def trustRootFromCertificates(certificates):
    """
    Builds an object that trusts multiple root L{Certificate}s.

    When passed to L{optionsForClientTLS}, connections using those options will
    reject any server certificate not signed by at least one of the
    certificates in the `certificates` list.

    @since: 16.0.0

    @param certificates: All certificates which will be trusted.
    @type certificates: C{iterable} of L{CertBase}

    @rtype: L{IOpenSSLTrustRoot}
    @return: an object suitable for use as the trustRoot= keyword argument to
        L{optionsForClientTLS}
    """

    certs = []
    for cert in certificates:
        # PrivateCertificate or Certificate are both okay
        if isinstance(cert, CertBase):
            cert = cert.original
        else:
            raise TypeError(
                "certificates items must be twisted.internet.ssl.CertBase"
                " instances"
            )
        certs.append(cert)
    return OpenSSLCertificateAuthorities(certs)



@implementer(IOpenSSLTrustRoot)
class OpenSSLDefaultPaths(object):
    """
    Trust the set of default verify paths that OpenSSL was built with, as
    specified by U{SSL_CTX_set_default_verify_paths
    <https://www.openssl.org/docs/ssl/SSL_CTX_load_verify_locations.html>}.
    """

    def _addCACertsToContext(self, context):
        context.set_default_verify_paths()



def platformTrust():
    """
    Attempt to discover a set of trusted certificate authority certificates
    (or, in other words: trust roots, or root certificates) whose trust is
    managed and updated by tools outside of Twisted.

    If you are writing any client-side TLS code with Twisted, you should use
    this as the C{trustRoot} argument to L{CertificateOptions
    <twisted.internet.ssl.CertificateOptions>}.

    The result of this function should be like the up-to-date list of
    certificates in a web browser.  When developing code that uses
    C{platformTrust}, you can think of it that way.  However, the choice of
    which certificate authorities to trust is never Twisted's responsibility.
    Unless you're writing a very unusual application or library, it's not your
    code's responsibility either.  The user may use platform-specific tools for
    defining which server certificates should be trusted by programs using TLS.
    The purpose of using this API is to respect that decision as much as
    possible.

    This should be a set of trust settings most appropriate for I{client} TLS
    connections; i.e. those which need to verify a server's authenticity.  You
    should probably use this by default for any client TLS connection that you
    create.  For servers, however, client certificates are typically not
    verified; or, if they are, their verification will depend on a custom,
    application-specific certificate authority.

    @since: 14.0

    @note: Currently, L{platformTrust} depends entirely upon your OpenSSL build
        supporting a set of "L{default verify paths <OpenSSLDefaultPaths>}"
        which correspond to certificate authority trust roots.  Unfortunately,
        whether this is true of your system is both outside of Twisted's
        control and difficult (if not impossible) for Twisted to detect
        automatically.

        Nevertheless, this ought to work as desired by default on:

            - Ubuntu Linux machines with the U{ca-certificates
              <https://launchpad.net/ubuntu/+source/ca-certificates>} package
              installed,

            - Mac OS X when using the system-installed version of OpenSSL (i.e.
              I{not} one installed via MacPorts or Homebrew),

            - any build of OpenSSL which has had certificate authority
              certificates installed into its default verify paths (by default,
              C{/usr/local/ssl/certs} if you've built your own OpenSSL), or

            - any process where the C{SSL_CERT_FILE} environment variable is
              set to the path of a file containing your desired CA certificates
              bundle.

        Hopefully soon, this API will be updated to use more sophisticated
        trust-root discovery mechanisms.  Until then, you can follow tickets in
        the Twisted tracker for progress on this implementation on U{Microsoft
        Windows <https://twistedmatrix.com/trac/ticket/6371>}, U{Mac OS X
        <https://twistedmatrix.com/trac/ticket/6372>}, and U{a fallback for
        other platforms which do not have native trust management tools
        <https://twistedmatrix.com/trac/ticket/6934>}.

    @return: an appropriate trust settings object for your platform.
    @rtype: L{IOpenSSLTrustRoot}

    @raise NotImplementedError: if this platform is not yet supported by
        Twisted.  At present, only OpenSSL is supported.
    """
    return OpenSSLDefaultPaths()



def _tolerateErrors(wrapped):
    """
    Wrap up an C{info_callback} for pyOpenSSL so that if something goes wrong
    the error is immediately logged and the connection is dropped if possible.

    This wrapper exists because some versions of pyOpenSSL don't handle errors
    from callbacks at I{all}, and those which do write tracebacks directly to
    stderr rather than to a supplied logging system.  This reports unexpected
    errors to the Twisted logging system.

    Also, this terminates the connection immediately if possible because if
    you've got bugs in your verification logic it's much safer to just give up.

    @param wrapped: A valid C{info_callback} for pyOpenSSL.
    @type wrapped: L{callable}

    @return: A valid C{info_callback} for pyOpenSSL that handles any errors in
        C{wrapped}.
    @rtype: L{callable}
    """
    def infoCallback(connection, where, ret):
        try:
            return wrapped(connection, where, ret)
        except:
            f = Failure()
            log.err(f, "Error during info_callback")
            connection.get_app_data().failVerification(f)
    return infoCallback



@implementer(IOpenSSLClientConnectionCreator)
class ClientTLSOptions(object):
    """
    Client creator for TLS.

    Private implementation type (not exposed to applications) for public
    L{optionsForClientTLS} API.

    @ivar _ctx: The context to use for new connections.
    @type _ctx: L{OpenSSL.SSL.Context}

    @ivar _hostname: The hostname to verify, as specified by the application,
        as some human-readable text.
    @type _hostname: L{unicode}

    @ivar _hostnameBytes: The hostname to verify, decoded into IDNA-encoded
        bytes.  This is passed to APIs which think that hostnames are bytes,
        such as OpenSSL's SNI implementation.
    @type _hostnameBytes: L{bytes}

    @ivar _hostnameASCII: The hostname, as transcoded into IDNA ASCII-range
        unicode code points.  This is pre-transcoded because the
        C{service_identity} package is rather strict about requiring the
        C{idna} package from PyPI for internationalized domain names, rather
        than working with Python's built-in (but sometimes broken) IDNA
        encoding.  ASCII values, however, will always work.
    @type _hostnameASCII: L{unicode}
    """

    def __init__(self, hostname, ctx):
        """
        Initialize L{ClientTLSOptions}.

        @param hostname: The hostname to verify as input by a human.
        @type hostname: L{unicode}

        @param ctx: an L{OpenSSL.SSL.Context} to use for new connections.
        @type ctx: L{OpenSSL.SSL.Context}.
        """
        self._ctx = ctx
        self._hostname = hostname
        self._hostnameBytes = _idnaBytes(hostname)
        self._hostnameASCII = self._hostnameBytes.decode("ascii")
        ctx.set_info_callback(
            _tolerateErrors(self._identityVerifyingInfoCallback)
        )


    def clientConnectionForTLS(self, tlsProtocol):
        """
        Create a TLS connection for a client.

        @note: This will call C{set_app_data} on its connection.  If you're
            delegating to this implementation of this method, don't ever call
            C{set_app_data} or C{set_info_callback} on the returned connection,
            or you'll break the implementation of various features of this
            class.

        @param tlsProtocol: the TLS protocol initiating the connection.
        @type tlsProtocol: L{twisted.protocols.tls.TLSMemoryBIOProtocol}

        @return: the configured client connection.
        @rtype: L{OpenSSL.SSL.Connection}
        """
        context = self._ctx
        connection = SSL.Connection(context, None)
        connection.set_app_data(tlsProtocol)
        return connection


    def _identityVerifyingInfoCallback(self, connection, where, ret):
        """
        U{info_callback
        <http://pythonhosted.org/pyOpenSSL/api/ssl.html#OpenSSL.SSL.Context.set_info_callback>
        } for pyOpenSSL that verifies the hostname in the presented certificate
        matches the one passed to this L{ClientTLSOptions}.

        @param connection: the connection which is handshaking.
        @type connection: L{OpenSSL.SSL.Connection}

        @param where: flags indicating progress through a TLS handshake.
        @type where: L{int}

        @param ret: ignored
        @type ret: ignored
        """
        if where & SSL_CB_HANDSHAKE_START:
            _maybeSetHostNameIndication(connection, self._hostnameBytes)
        elif where & SSL_CB_HANDSHAKE_DONE:
            try:
                verifyHostname(connection, self._hostnameASCII)
            except VerificationError:
                f = Failure()
                transport = connection.get_app_data()
                transport.failVerification(f)



def optionsForClientTLS(hostname, trustRoot=None, clientCertificate=None,
                        acceptableProtocols=None, **kw):
    """
    Create a L{client connection creator <IOpenSSLClientConnectionCreator>} for
    use with APIs such as L{SSL4ClientEndpoint
    <twisted.internet.endpoints.SSL4ClientEndpoint>}, L{connectSSL
    <twisted.internet.interfaces.IReactorSSL.connectSSL>}, and L{startTLS
    <twisted.internet.interfaces.ITLSTransport.startTLS>}.

    @since: 14.0

    @param hostname: The expected name of the remote host.  This serves two
        purposes: first, and most importantly, it verifies that the certificate
        received from the server correctly identifies the specified hostname.
        The second purpose is (if the local C{pyOpenSSL} supports it) to use
        the U{Server Name Indication extension
        <https://en.wikipedia.org/wiki/Server_Name_Indication>} to indicate to
        the server which certificate should be used.
    @type hostname: L{unicode}

    @param trustRoot: Specification of trust requirements of peers.  This may
        be a L{Certificate} or the result of L{platformTrust}.  By default it
        is L{platformTrust} and you probably shouldn't adjust it unless you
        really know what you're doing.  Be aware that clients using this
        interface I{must} verify the server; you cannot explicitly pass L{None}
        since that just means to use L{platformTrust}.
    @type trustRoot: L{IOpenSSLTrustRoot}

    @param clientCertificate: The certificate and private key that the client
        will use to authenticate to the server.  If unspecified, the client
        will not authenticate.
    @type clientCertificate: L{PrivateCertificate}

    @param acceptableProtocols: The protocols this peer is willing to speak
        after the TLS negotiation has completed, advertised over both ALPN and
        NPN. If this argument is specified, and no overlap can be found with
        the other peer, the connection will fail to be established. If the
        remote peer does not offer NPN or ALPN, the connection will be
        established, but no protocol wil be negotiated. Protocols earlier in
        the list are preferred over those later in the list.
    @type acceptableProtocols: L{list} of L{bytes}

    @param extraCertificateOptions: keyword-only argument; this is a dictionary
        of additional keyword arguments to be presented to
        L{CertificateOptions}.  Please avoid using this unless you absolutely
        need to; any time you need to pass an option here that is a bug in this
        interface.
    @type extraCertificateOptions: L{dict}

    @param kw: (Backwards compatibility hack to allow keyword-only arguments on
        Python 2.  Please ignore; arbitrary keyword arguments will be errors.)
    @type kw: L{dict}

    @return: A client connection creator.
    @rtype: L{IOpenSSLClientConnectionCreator}
    """
    extraCertificateOptions = kw.pop('extraCertificateOptions', None) or {}
    if trustRoot is None:
        trustRoot = platformTrust()
    if kw:
        raise TypeError(
            "optionsForClientTLS() got an unexpected keyword argument"
            " '{arg}'".format(
                arg=kw.popitem()[0]
            )
        )
    if not isinstance(hostname, unicode):
        raise TypeError(
            "optionsForClientTLS requires text for host names, not "
            + hostname.__class__.__name__
        )
    if clientCertificate:
        extraCertificateOptions.update(
            privateKey=clientCertificate.privateKey.original,
            certificate=clientCertificate.original
        )
    certificateOptions = OpenSSLCertificateOptions(
        trustRoot=trustRoot,
        acceptableProtocols=acceptableProtocols,
        **extraCertificateOptions
    )
    return ClientTLSOptions(hostname, certificateOptions.getContext())



@implementer(IOpenSSLContextFactory)
class OpenSSLCertificateOptions(object):
    """
    A L{CertificateOptions <twisted.internet.ssl.CertificateOptions>} specifies
    the security properties for a client or server TLS connection used with
    OpenSSL.

    @ivar _options: Any option flags to set on the L{OpenSSL.SSL.Context}
        object that will be created.
    @type _options: L{int}

    @ivar _cipherString: An OpenSSL-specific cipher string.
    @type _cipherString: L{unicode}
    """

    # Factory for creating contexts.  Configurable for testability.
    _contextFactory = SSL.Context
    _context = None
    # Some option constants may not be exposed by PyOpenSSL yet.
    _OP_ALL = getattr(SSL, 'OP_ALL', 0x0000FFFF)
    _OP_NO_TICKET = getattr(SSL, 'OP_NO_TICKET', 0x00004000)
    _OP_NO_COMPRESSION = getattr(SSL, 'OP_NO_COMPRESSION', 0x00020000)
    _OP_CIPHER_SERVER_PREFERENCE = getattr(SSL, 'OP_CIPHER_SERVER_PREFERENCE',
                                           0x00400000)
    _OP_SINGLE_ECDH_USE = getattr(SSL, 'OP_SINGLE_ECDH_USE', 0x00080000)


    @_mutuallyExclusiveArguments([
        ['trustRoot', 'requireCertificate'],
        ['trustRoot', 'verify'],
        ['trustRoot', 'caCerts'],
    ])
    def __init__(self,
                 privateKey=None,
                 certificate=None,
                 method=None,
                 verify=False,
                 caCerts=None,
                 verifyDepth=9,
                 requireCertificate=True,
                 verifyOnce=True,
                 enableSingleUseKeys=True,
                 enableSessions=True,
                 fixBrokenPeers=False,
                 enableSessionTickets=False,
                 extraCertChain=None,
                 acceptableCiphers=None,
                 dhParameters=None,
                 trustRoot=None,
                 acceptableProtocols=None,
                 ):
        """
        Create an OpenSSL context SSL connection context factory.

        @param privateKey: A PKey object holding the private key.

        @param certificate: An X509 object holding the certificate.

        @param method: The SSL protocol to use, one of SSLv23_METHOD,
            SSLv2_METHOD, SSLv3_METHOD, TLSv1_METHOD (or any other method
            constants provided by pyOpenSSL).  By default, a setting will be
            used which allows TLSv1.0, TLSv1.1, and TLSv1.2.

        @param verify: Please use a C{trustRoot} keyword argument instead,
            since it provides the same functionality in a less error-prone way.
            By default this is L{False}.

            If L{True}, verify certificates received from the peer and fail the
            handshake if verification fails.  Otherwise, allow anonymous
            sessions and sessions with certificates which fail validation.

        @param caCerts: Please use a C{trustRoot} keyword argument instead,
            since it provides the same functionality in a less error-prone way.

            List of certificate authority certificate objects to use to verify
            the peer's certificate.  Only used if verify is L{True} and will be
            ignored otherwise.  Since verify is L{False} by default, this is
            L{None} by default.

        @type caCerts: L{list} of L{OpenSSL.crypto.X509}

        @param verifyDepth: Depth in certificate chain down to which to verify.
            If unspecified, use the underlying default (9).

        @param requireCertificate: Please use a C{trustRoot} keyword argument
            instead, since it provides the same functionality in a less
            error-prone way.

            If L{True}, do not allow anonymous sessions; defaults to L{True}.

        @param verifyOnce: If True, do not re-verify the certificate on session
            resumption.

        @param enableSingleUseKeys: If L{True}, generate a new key whenever
            ephemeral DH and ECDH parameters are used to prevent small subgroup
            attacks and to ensure perfect forward secrecy.

        @param enableSessions: If True, set a session ID on each context.  This
            allows a shortened handshake to be used when a known client
            reconnects.

        @param fixBrokenPeers: If True, enable various non-spec protocol fixes
            for broken SSL implementations.  This should be entirely safe,
            according to the OpenSSL documentation, but YMMV.  This option is
            now off by default, because it causes problems with connections
            between peers using OpenSSL 0.9.8a.

        @param enableSessionTickets: If L{True}, enable session ticket
            extension for session resumption per RFC 5077.  Note there is no
            support for controlling session tickets.  This option is off by
            default, as some server implementations don't correctly process
            incoming empty session ticket extensions in the hello.

        @param extraCertChain: List of certificates that I{complete} your
            verification chain if the certificate authority that signed your
            C{certificate} isn't widely supported.  Do I{not} add
            C{certificate} to it.
        @type extraCertChain: C{list} of L{OpenSSL.crypto.X509}

        @param acceptableCiphers: Ciphers that are acceptable for connections.
            Uses a secure default if left L{None}.
        @type acceptableCiphers: L{IAcceptableCiphers}

        @param dhParameters: Key generation parameters that are required for
            Diffie-Hellman key exchange.  If this argument is left L{None},
            C{EDH} ciphers are I{disabled} regardless of C{acceptableCiphers}.
        @type dhParameters: L{DiffieHellmanParameters
            <twisted.internet.ssl.DiffieHellmanParameters>}

        @param trustRoot: Specification of trust requirements of peers.  If
            this argument is specified, the peer is verified.  It requires a
            certificate, and that certificate must be signed by one of the
            certificate authorities specified by this object.

            Note that since this option specifies the same information as
            C{caCerts}, C{verify}, and C{requireCertificate}, specifying any of
            those options in combination with this one will raise a
            L{TypeError}.

        @type trustRoot: L{IOpenSSLTrustRoot}

        @param acceptableProtocols: The protocols this peer is willing to speak
            after the TLS negotiation has completed, advertised over both ALPN
            and NPN. If this argument is specified, and no overlap can be found
            with the other peer, the connection will fail to be established.
            If the remote peer does not offer NPN or ALPN, the connection will
            be established, but no protocol wil be negotiated. Protocols
            earlier in the list are preferred over those later in the list.
        @type acceptableProtocols: L{list} of L{bytes}

        @raise ValueError: when C{privateKey} or C{certificate} are set without
            setting the respective other.
        @raise ValueError: when C{verify} is L{True} but C{caCerts} doesn't
            specify any CA certificates.
        @raise ValueError: when C{extraCertChain} is passed without specifying
            C{privateKey} or C{certificate}.
        @raise ValueError: when C{acceptableCiphers} doesn't yield any usable
            ciphers for the current platform.

        @raise TypeError: if C{trustRoot} is passed in combination with
            C{caCert}, C{verify}, or C{requireCertificate}.  Please prefer
            C{trustRoot} in new code, as its semantics are less tricky.
        @raises NotImplementedError: If acceptableProtocols were provided but
            no negotiation mechanism is available.
        """

        if (privateKey is None) != (certificate is None):
            raise ValueError(
                "Specify neither or both of privateKey and certificate")
        self.privateKey = privateKey
        self.certificate = certificate

        # Set basic security options: disallow insecure SSLv2, disallow TLS
        # compression to avoid CRIME attack, make the server choose the
        # ciphers.
        self._options = (
            SSL.OP_NO_SSLv2 | self._OP_NO_COMPRESSION |
            self._OP_CIPHER_SERVER_PREFERENCE
        )

        if method is None:
            # If no method is specified set things up so that TLSv1.0 and newer
            # will be supported.
            self.method = SSL.SSLv23_METHOD
            self._options |= SSL.OP_NO_SSLv3
        else:
            # Otherwise respect the application decision.
            self.method = method

        if verify and not caCerts:
            raise ValueError("Specify client CA certificate information if and"
                             " only if enabling certificate verification")
        self.verify = verify
        if extraCertChain is not None and None in (privateKey, certificate):
            raise ValueError("A private key and a certificate are required "
                             "when adding a supplemental certificate chain.")
        if extraCertChain is not None:
            self.extraCertChain = extraCertChain
        else:
            self.extraCertChain = []

        self.caCerts = caCerts
        self.verifyDepth = verifyDepth
        self.requireCertificate = requireCertificate
        self.verifyOnce = verifyOnce
        self.enableSingleUseKeys = enableSingleUseKeys
        if enableSingleUseKeys:
            self._options |= SSL.OP_SINGLE_DH_USE | self._OP_SINGLE_ECDH_USE
        self.enableSessions = enableSessions
        self.fixBrokenPeers = fixBrokenPeers
        if fixBrokenPeers:
            self._options |= self._OP_ALL
        self.enableSessionTickets = enableSessionTickets

        if not enableSessionTickets:
            self._options |= self._OP_NO_TICKET
        self.dhParameters = dhParameters

        try:
            self._ecCurve = _OpenSSLECCurve(_defaultCurveName)
        except NotImplementedError:
            self._ecCurve = None

        if acceptableCiphers is None:
            acceptableCiphers = defaultCiphers
        # This needs to run when method and _options are finalized.
        self._cipherString = u':'.join(
            c.fullName
            for c in acceptableCiphers.selectCiphers(
                _expandCipherString(u'ALL', self.method, self._options)
            )
        )
        if self._cipherString == u'':
            raise ValueError(
                'Supplied IAcceptableCiphers yielded no usable ciphers '
                'on this platform.'
            )

        if trustRoot is None:
            if self.verify:
                trustRoot = OpenSSLCertificateAuthorities(caCerts)
        else:
            self.verify = True
            self.requireCertificate = True
            trustRoot = IOpenSSLTrustRoot(trustRoot)
        self.trustRoot = trustRoot

        if acceptableProtocols is not None and not protocolNegotiationMechanisms():
            raise NotImplementedError(
                "No support for protocol negotiation on this platform."
            )

        self._acceptableProtocols = acceptableProtocols


    def __getstate__(self):
        d = self.__dict__.copy()
        try:
            del d['_context']
        except KeyError:
            pass
        return d


    def __setstate__(self, state):
        self.__dict__ = state


    def getContext(self):
        """
        Return an L{OpenSSL.SSL.Context} object.
        """
        if self._context is None:
            self._context = self._makeContext()
        return self._context


    def _makeContext(self):
        ctx = self._contextFactory(self.method)
        ctx.set_options(self._options)

        if self.certificate is not None and self.privateKey is not None:
            ctx.use_certificate(self.certificate)
            ctx.use_privatekey(self.privateKey)
            for extraCert in self.extraCertChain:
                ctx.add_extra_chain_cert(extraCert)
            # Sanity check
            ctx.check_privatekey()

        verifyFlags = SSL.VERIFY_NONE
        if self.verify:
            verifyFlags = SSL.VERIFY_PEER
            if self.requireCertificate:
                verifyFlags |= SSL.VERIFY_FAIL_IF_NO_PEER_CERT
            if self.verifyOnce:
                verifyFlags |= SSL.VERIFY_CLIENT_ONCE
            self.trustRoot._addCACertsToContext(ctx)

        # It'd be nice if pyOpenSSL let us pass None here for this behavior (as
        # the underlying OpenSSL API call allows NULL to be passed).  It
        # doesn't, so we'll supply a function which does the same thing.
        def _verifyCallback(conn, cert, errno, depth, preverify_ok):
            return preverify_ok
        ctx.set_verify(verifyFlags, _verifyCallback)
        if self.verifyDepth is not None:
            ctx.set_verify_depth(self.verifyDepth)

        if self.enableSessions:
            name = "%s-%d" % (reflect.qual(self.__class__), _sessionCounter())
            sessionName = md5(networkString(name)).hexdigest()

            ctx.set_session_id(sessionName.encode('ascii'))

        if self.dhParameters:
            ctx.load_tmp_dh(self.dhParameters._dhFile.path)
        ctx.set_cipher_list(self._cipherString.encode('ascii'))

        if self._ecCurve is not None:
            try:
                self._ecCurve.addECKeyToContext(ctx)
            except BaseException:
                pass  # ECDHE support is best effort only.

        if self._acceptableProtocols:
            # Try to set NPN and ALPN. _acceptableProtocols cannot be set by
            # the constructor unless at least one mechanism is supported.
            _setAcceptableProtocols(ctx, self._acceptableProtocols)

        return ctx


OpenSSLCertificateOptions.__getstate__ = deprecated(
        Version("Twisted", 15, 0, 0),
        "a real persistence system")(OpenSSLCertificateOptions.__getstate__)
OpenSSLCertificateOptions.__setstate__ = deprecated(
        Version("Twisted", 15, 0, 0),
        "a real persistence system")(OpenSSLCertificateOptions.__setstate__)



class _OpenSSLECCurve(FancyEqMixin, object):
    """
    A private representation of an OpenSSL ECC curve.
    """
    compareAttributes = ("snName", )

    def __init__(self, snName):
        """
        @param snName: The name of the curve as used by C{OBJ_sn2nid}.
        @param snName: L{unicode}

        @raises NotImplementedError: If ECC support is not available.
        @raises ValueError: If C{snName} is not a supported curve.
        """
        self.snName = nativeString(snName)

        # As soon as pyOpenSSL supports ECDHE directly, attempt to use its
        # APIs first.  See #7033.

        # If pyOpenSSL is based on cryptography.io (0.14+), we use its
        # bindings directly to set the ECDHE curve.
        try:
            binding = self._getBinding()
            self._lib = binding.lib
            self._ffi = binding.ffi
            self._nid = self._lib.OBJ_sn2nid(self.snName.encode('ascii'))
            if self._nid == self._lib.NID_undef:
                raise ValueError("Unknown ECC curve.")
        except AttributeError:
            raise NotImplementedError(
                "This version of pyOpenSSL does not support ECC."
            )


    def _getBinding(self):
        """
        Attempt to get cryptography's binding instance.

        @raises NotImplementedError: If underlying pyOpenSSL is not based on
            cryptography.

        @return: cryptograpy bindings.
        @rtype: C{cryptography.hazmat.bindings.openssl.Binding}
        """
        try:
            from OpenSSL._util import binding
            return binding
        except ImportError:
            raise NotImplementedError(
                "This version of pyOpenSSL does not support ECC."
            )


    def addECKeyToContext(self, context):
        """
        Add a temporary EC key to C{context}.

        @param context: The context to add a key to.
        @type context: L{OpenSSL.SSL.Context}
        """
        ecKey = self._lib.EC_KEY_new_by_curve_name(self._nid)
        if ecKey == self._ffi.NULL:
            raise EnvironmentError("EC key creation failed.")

        self._lib.SSL_CTX_set_tmp_ecdh(context._context, ecKey)
        self._lib.EC_KEY_free(ecKey)



@implementer(ICipher)
class OpenSSLCipher(FancyEqMixin, object):
    """
    A representation of an OpenSSL cipher.
    """
    compareAttributes = ('fullName',)

    def __init__(self, fullName):
        """
        @param fullName: The full name of the cipher. For example
            C{u"ECDHE-RSA-AES256-GCM-SHA384"}.
        @type fullName: L{unicode}
        """
        self.fullName = fullName


    def __repr__(self):
        """
        A runnable representation of the cipher.
        """
        return 'OpenSSLCipher({0!r})'.format(self.fullName)



def _expandCipherString(cipherString, method, options):
    """
    Expand C{cipherString} according to C{method} and C{options} to a list
    of explicit ciphers that are supported by the current platform.

    @param cipherString: An OpenSSL cipher string to expand.
    @type cipherString: L{unicode}

    @param method: An OpenSSL method like C{SSL.TLSv1_METHOD} used for
        determining the effective ciphers.

    @param options: OpenSSL options like C{SSL.OP_NO_SSLv3} ORed together.
    @type options: L{int}

    @return: The effective list of explicit ciphers that results from the
        arguments on the current platform.
    @rtype: L{list} of L{ICipher}
    """
    ctx = SSL.Context(method)
    ctx.set_options(options)
    try:
        ctx.set_cipher_list(cipherString.encode('ascii'))
    except SSL.Error as e:
        if e.args[0][0][2] == 'no cipher match':
            return []
        else:
            raise
    conn = SSL.Connection(ctx, None)
    ciphers = conn.get_cipher_list()
    if isinstance(ciphers[0], unicode):
        return [OpenSSLCipher(cipher) for cipher in ciphers]
    else:
        return [OpenSSLCipher(cipher.decode('ascii')) for cipher in ciphers]



@implementer(IAcceptableCiphers)
class OpenSSLAcceptableCiphers(object):
    """
    A representation of ciphers that are acceptable for TLS connections.
    """
    def __init__(self, ciphers):
        self._ciphers = ciphers

    def selectCiphers(self, availableCiphers):
        return [cipher
                for cipher in self._ciphers
                if cipher in availableCiphers]


    @classmethod
    def fromOpenSSLCipherString(cls, cipherString):
        """
        Create a new instance using an OpenSSL cipher string.

        @param cipherString: An OpenSSL cipher string that describes what
            cipher suites are acceptable.
            See the documentation of U{OpenSSL
            <http://www.openssl.org/docs/apps/ciphers.html#CIPHER_STRINGS>} or
            U{Apache
            <http://httpd.apache.org/docs/2.4/mod/mod_ssl.html#sslciphersuite>}
            for details.
        @type cipherString: L{unicode}

        @return: Instance representing C{cipherString}.
        @rtype: L{twisted.internet.ssl.AcceptableCiphers}
        """
        return cls(_expandCipherString(
            nativeString(cipherString),
            SSL.SSLv23_METHOD, SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3)
        )


# A secure default.
# Sources for more information on TLS ciphers:
#
# - https://wiki.mozilla.org/Security/Server_Side_TLS
# - https://www.ssllabs.com/projects/best-practices/index.html
# - https://hynek.me/articles/hardening-your-web-servers-ssl-ciphers/
#
# The general intent is:
# - Prefer cipher suites that offer perfect forward secrecy (DHE/ECDHE),
# - prefer ECDHE over DHE for better performance,
# - prefer any AES-GCM and ChaCha20 over any AES-CBC for better performance and
#   security,
# - prefer AES-GCM to ChaCha20 because AES hardware support is common,
# - disable NULL authentication, MD5 MACs and DSS for security reasons.
#
defaultCiphers = OpenSSLAcceptableCiphers.fromOpenSSLCipherString(
    "ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:DH+CHACHA20:ECDH+AES256:DH+AES256:"
    "ECDH+AES128:DH+AES:RSA+AESGCM:RSA+AES:"
    "!aNULL:!MD5:!DSS"
)
_defaultCurveName = u"prime256v1"



class OpenSSLDiffieHellmanParameters(object):
    """
    A representation of key generation parameters that are required for
    Diffie-Hellman key exchange.
    """
    def __init__(self, parameters):
        self._dhFile = parameters


    @classmethod
    def fromFile(cls, filePath):
        """
        Load parameters from a file.

        Such a file can be generated using the C{openssl} command line tool as
        following:

        C{openssl dhparam -out dh_param_1024.pem -2 1024}

        Please refer to U{OpenSSL's C{dhparam} documentation
        <http://www.openssl.org/docs/apps/dhparam.html>} for further details.

        @param filePath: A file containing parameters for Diffie-Hellman key
            exchange.
        @type filePath: L{FilePath <twisted.python.filepath.FilePath>}

        @return: An instance that loads its parameters from C{filePath}.
        @rtype: L{DiffieHellmanParameters
            <twisted.internet.ssl.DiffieHellmanParameters>}
        """
        return cls(filePath)


def _setAcceptableProtocols(context, acceptableProtocols):
    """
    Called to set up the L{OpenSSL.SSL.Context} for doing NPN and/or ALPN
    negotiation.

    @param context: The context which is set up.
    @type context: L{OpenSSL.SSL.Context}

    @param acceptableProtocols: The protocols this peer is willing to speak
        after the TLS negotiation has completed, advertised over both ALPN and
        NPN. If this argument is specified, and no overlap can be found with
        the other peer, the connection will fail to be established. If the
        remote peer does not offer NPN or ALPN, the connection will be
        established, but no protocol wil be negotiated. Protocols earlier in
        the list are preferred over those later in the list.
    @type acceptableProtocols: L{list} of L{bytes}
    """
    def protoSelectCallback(conn, protocols):
        """
        NPN client-side and ALPN server-side callback used to select
        the next protocol. Prefers protocols found earlier in
        C{_acceptableProtocols}.

        @param conn: The context which is set up.
        @type conn: L{OpenSSL.SSL.Connection}

        @param conn: Protocols advertised by the other side.
        @type conn: L{list} of L{bytes}
        """
        overlap = set(protocols) & set(acceptableProtocols)

        for p in acceptableProtocols:
            if p in overlap:
                return p
        else:
            return b''

    # If we don't actually have protocols to negotiate, don't set anything up.
    # Depending on OpenSSL version, failing some of the selection callbacks can
    # cause the handshake to fail, which is presumably not what was intended
    # here.
    if not acceptableProtocols:
        return

    supported = protocolNegotiationMechanisms()

    if supported & ProtocolNegotiationSupport.NPN:
        def npnAdvertiseCallback(conn):
            return acceptableProtocols

        context.set_npn_advertise_callback(npnAdvertiseCallback)
        context.set_npn_select_callback(protoSelectCallback)

    if supported & ProtocolNegotiationSupport.ALPN:
        context.set_alpn_select_callback(protoSelectCallback)
        context.set_alpn_protos(acceptableProtocols)
