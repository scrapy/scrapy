# -*- test-case-name: twisted.test.test_sslverify -*-
# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import warnings
from binascii import hexlify
from functools import lru_cache
from hashlib import md5

from zope.interface import Interface, implementer

from OpenSSL import SSL, crypto
from OpenSSL._util import lib as pyOpenSSLlib  # type: ignore[import]

import attr
from constantly import FlagConstant, Flags, NamedConstant, Names  # type: ignore[import]
from incremental import Version

from twisted.internet.abstract import isIPAddress, isIPv6Address
from twisted.internet.defer import Deferred
from twisted.internet.error import CertificateError, VerifyError
from twisted.internet.interfaces import (
    IAcceptableCiphers,
    ICipher,
    IOpenSSLClientConnectionCreator,
    IOpenSSLContextFactory,
)
from twisted.python import log, util
from twisted.python.compat import nativeString
from twisted.python.deprecate import _mutuallyExclusiveArguments, deprecated
from twisted.python.failure import Failure
from twisted.python.randbytes import secureRandom
from ._idna import _idnaBytes


class TLSVersion(Names):
    """
    TLS versions that we can negotiate with the client/server.
    """

    SSLv3 = NamedConstant()
    TLSv1_0 = NamedConstant()
    TLSv1_1 = NamedConstant()
    TLSv1_2 = NamedConstant()
    TLSv1_3 = NamedConstant()


_tlsDisableFlags = {
    TLSVersion.SSLv3: SSL.OP_NO_SSLv3,
    TLSVersion.TLSv1_0: SSL.OP_NO_TLSv1,
    TLSVersion.TLSv1_1: SSL.OP_NO_TLSv1_1,
    TLSVersion.TLSv1_2: SSL.OP_NO_TLSv1_2,
    # If we don't have TLS v1.3 yet, we can't disable it -- this is just so
    # when it makes it into OpenSSL, connections knowingly bracketed to v1.2
    # don't end up going to v1.3
    TLSVersion.TLSv1_3: getattr(SSL, "OP_NO_TLSv1_3", 0x00),
}


def _getExcludedTLSProtocols(oldest, newest):
    """
    Given a pair of L{TLSVersion} constants, figure out what versions we want
    to disable (as OpenSSL is an exclusion based API).

    @param oldest: The oldest L{TLSVersion} we want to allow.
    @type oldest: L{TLSVersion} constant

    @param newest: The newest L{TLSVersion} we want to allow, or L{None} for no
        upper limit.
    @type newest: L{TLSVersion} constant or L{None}

    @return: The versions we want to disable.
    @rtype: L{list} of L{TLSVersion} constants.
    """
    versions = list(TLSVersion.iterconstants())
    excludedVersions = [x for x in versions[: versions.index(oldest)]]

    if newest:
        excludedVersions.extend([x for x in versions[versions.index(newest) :]])

    return excludedVersions


class SimpleVerificationError(Exception):
    """
    Not a very useful verification error.
    """


def simpleVerifyHostname(connection, hostname):
    """
    Check only the common name in the certificate presented by the peer and
    only for an exact match.

    This is to provide I{something} in the way of hostname verification to
    users who haven't installed C{service_identity}. This check is overly
    strict, relies on a deprecated TLS feature (you're supposed to ignore the
    commonName if the subjectAlternativeName extensions are present, I
    believe), and lots of valid certificates will fail.

    @param connection: the OpenSSL connection to verify.
    @type connection: L{OpenSSL.SSL.Connection}

    @param hostname: The hostname expected by the user.
    @type hostname: L{unicode}

    @raise twisted.internet.ssl.VerificationError: if the common name and
        hostname don't match.
    """
    commonName = connection.get_peer_certificate().get_subject().commonName
    if commonName != hostname:
        raise SimpleVerificationError(repr(commonName) + "!=" + repr(hostname))


def simpleVerifyIPAddress(connection, hostname):
    """
    Always fails validation of IP addresses

    @param connection: the OpenSSL connection to verify.
    @type connection: L{OpenSSL.SSL.Connection}

    @param hostname: The hostname expected by the user.
    @type hostname: L{unicode}

    @raise twisted.internet.ssl.VerificationError: Always raised
    """
    raise SimpleVerificationError("Cannot verify certificate IP addresses")


def _usablePyOpenSSL(version):
    """
    Check pyOpenSSL version string whether we can use it for host verification.

    @param version: A pyOpenSSL version string.
    @type version: L{str}

    @rtype: L{bool}
    """
    major, minor = (int(part) for part in version.split(".")[:2])
    return (major, minor) >= (0, 12)


def _selectVerifyImplementation():
    """
    Determine if C{service_identity} is installed. If so, use it. If not, use
    simplistic and incorrect checking as implemented in
    L{simpleVerifyHostname}.

    @return: 2-tuple of (C{verify_hostname}, C{VerificationError})
    @rtype: L{tuple}
    """

    whatsWrong = (
        "Without the service_identity module, Twisted can perform only "
        "rudimentary TLS client hostname verification.  Many valid "
        "certificate/hostname mappings may be rejected."
    )

    try:
        from service_identity import VerificationError  # type: ignore[import]
        from service_identity.pyopenssl import (  # type: ignore[import]
            verify_hostname,
            verify_ip_address,
        )

        return verify_hostname, verify_ip_address, VerificationError
    except ImportError as e:
        warnings.warn_explicit(
            "You do not have a working installation of the "
            "service_identity module: '" + str(e) + "'.  "
            "Please install it from "
            "<https://pypi.python.org/pypi/service_identity> and make "
            "sure all of its dependencies are satisfied.  " + whatsWrong,
            # Unfortunately the lineno is required.
            category=UserWarning,
            filename="",
            lineno=0,
        )

    return simpleVerifyHostname, simpleVerifyIPAddress, SimpleVerificationError


verifyHostname, verifyIPAddress, VerificationError = _selectVerifyImplementation()


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
    @rtype: L{constantly.FlagConstant}
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
    "CN": "commonName",
    "commonName": "commonName",
    "O": "organizationName",
    "organizationName": "organizationName",
    "OU": "organizationalUnitName",
    "organizationalUnitName": "organizationalUnitName",
    "L": "localityName",
    "localityName": "localityName",
    "ST": "stateOrProvinceName",
    "stateOrProvinceName": "stateOrProvinceName",
    "C": "countryName",
    "countryName": "countryName",
    "emailAddress": "emailAddress",
}


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

    def __repr__(self) -> str:
        return "<DN %s>" % (dict.__repr__(self)[1:-1])

    def __getattr__(self, attr):
        try:
            return self[_x509names[attr]]
        except KeyError:
            raise AttributeError(attr)

    def __setattr__(self, attr, value):
        if attr not in _x509names:
            raise AttributeError(f"{attr} is not a valid OpenSSL X509 name field")
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
        for n, (label, attrib) in enumerate(l):
            l[n] = label.rjust(lablen) + ": " + attrib
        return "\n".join(l)


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
        dn._copyFrom(getattr(self.original, "get_" + suffix)())
        return dn

    def getSubject(self):
        """
        Retrieve the subject of this certificate.

        @return: A copy of the subject of this certificate.
        @rtype: L{DistinguishedName}
        """
        return self._copyName("subject")

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
    method = getattr(transport.getHandle(), f"get_{methodName}_certificate", None)
    if method is None:
        raise CertificateError(
            "non-TLS transport {!r} did not have {} certificate".format(
                transport, methodName
            )
        )
    cert = method()
    if cert is None:
        raise CertificateError(
            "TLS transport {!r} did not have {} certificate".format(
                transport, methodName
            )
        )
    return Class(cert)


class Certificate(CertBase):
    """
    An x509 certificate.
    """

    def __repr__(self) -> str:
        return "<{} Subject={} Issuer={}>".format(
            self.__class__.__name__,
            self.getSubject().commonName,
            self.getIssuer().commonName,
        )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Certificate):
            return self.dump() == other.dump()
        return NotImplemented

    @classmethod
    def load(Class, requestData, format=crypto.FILETYPE_ASN1, args=()):
        """
        Load a certificate from an ASN.1- or PEM-format string.

        @rtype: C{Class}
        """
        return Class(crypto.load_certificate(format, requestData), *args)

    # We can't use super() because it is old style still, so we have to hack
    # around things wanting to call the parent function
    _load = load

    def dumpPEM(self):
        """
        Dump this certificate to a PEM-format data string.

        @rtype: L{str}
        """
        return self.dump(crypto.FILETYPE_PEM)

    @classmethod
    def loadPEM(Class, data):
        """
        Load a certificate from a PEM-format data string.

        @rtype: C{Class}
        """
        return Class.load(data, crypto.FILETYPE_PEM)

    @classmethod
    def peerFromTransport(Class, transport):
        """
        Get the certificate for the remote end of the given transport.

        @param transport: an L{ISystemHandle} provider

        @rtype: C{Class}

        @raise CertificateError: if the given transport does not have a peer
            certificate.
        """
        return _handleattrhelper(Class, transport, "peer")

    @classmethod
    def hostFromTransport(Class, transport):
        """
        Get the certificate for the local end of the given transport.

        @param transport: an L{ISystemHandle} provider; the transport we will

        @rtype: C{Class}

        @raise CertificateError: if the given transport does not have a host
            certificate.
        """
        return _handleattrhelper(Class, transport, "host")

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

    def digest(self, method="md5"):
        """
        Return a digest hash of this certificate using the specified hash
        algorithm.

        @param method: One of C{'md5'} or C{'sha'}.

        @return: The digest of the object, formatted as b":"-delimited hex
            pairs
        @rtype: L{bytes}
        """
        return self.original.digest(method)

    def _inspect(self):
        return "\n".join(
            [
                "Certificate For Subject:",
                self.getSubject().inspect(),
                "\nIssuer:",
                self.getIssuer().inspect(),
                "\nSerial Number: %d" % self.serialNumber(),
                "Digest: %s" % nativeString(self.digest()),
            ]
        )

    def inspect(self):
        """
        Return a multi-line, human-readable representation of this
        Certificate, including information about the subject, issuer, and
        public key.
        """
        return "\n".join((self._inspect(), self.getPublicKey().inspect()))

    def getIssuer(self):
        """
        Retrieve the issuer of this certificate.

        @rtype: L{DistinguishedName}
        @return: A copy of the issuer of this certificate.
        """
        return self._copyName("issuer")

    def options(self, *authorities):
        raise NotImplementedError("Possible, but doubtful we need this yet")


class CertificateRequest(CertBase):
    """
    An x509 certificate request.

    Certificate requests are given to certificate authorities to be signed and
    returned resulting in an actual certificate.
    """

    @classmethod
    def load(Class, requestData, requestFormat=crypto.FILETYPE_ASN1):
        req = crypto.load_certificate_request(requestFormat, requestData)
        dn = DistinguishedName()
        dn._copyFrom(req.get_subject())
        if not req.verify(req.get_pubkey()):
            raise VerifyError(f"Can't verify that request for {dn!r} is self-signed.")
        return Class(req)

    def dump(self, format=crypto.FILETYPE_ASN1):
        return crypto.dump_certificate_request(format, self.original)


class PrivateCertificate(Certificate):
    """
    An x509 certificate and private key.
    """

    def __repr__(self) -> str:
        return Certificate.__repr__(self) + " with " + repr(self.privateKey)

    def _setPrivateKey(self, privateKey):
        if not privateKey.matches(self.getPublicKey()):
            raise VerifyError("Certificate public and private keys do not match.")
        self.privateKey = privateKey
        return self

    def newCertificate(self, newCertData, format=crypto.FILETYPE_ASN1):
        """
        Create a new L{PrivateCertificate} from the given certificate data and
        this instance's private key.
        """
        return self.load(newCertData, self.privateKey, format)

    @classmethod
    def load(Class, data, privateKey, format=crypto.FILETYPE_ASN1):
        return Class._load(data, format)._setPrivateKey(privateKey)

    def inspect(self):
        return "\n".join([Certificate._inspect(self), self.privateKey.inspect()])

    def dumpPEM(self):
        """
        Dump both public and private parts of a private certificate to
        PEM-format data.
        """
        return self.dump(crypto.FILETYPE_PEM) + self.privateKey.dump(
            crypto.FILETYPE_PEM
        )

    @classmethod
    def loadPEM(Class, data):
        """
        Load both private and public parts of a private certificate from a
        chunk of PEM-format data.
        """
        return Class.load(
            data, KeyPair.load(data, crypto.FILETYPE_PEM), crypto.FILETYPE_PEM
        )

    @classmethod
    def fromCertificateAndKeyPair(Class, certificateInstance, privateKey):
        privcert = Class(certificateInstance.original)
        return privcert._setPrivateKey(privateKey)

    def options(self, *authorities):
        """
        Create a context factory using this L{PrivateCertificate}'s certificate
        and private key.

        @param authorities: A list of L{Certificate} object

        @return: A context factory.
        @rtype: L{CertificateOptions <twisted.internet.ssl.CertificateOptions>}
        """
        options = dict(privateKey=self.privateKey.original, certificate=self.original)
        if authorities:
            options.update(
                dict(
                    trustRoot=OpenSSLCertificateAuthorities(
                        [auth.original for auth in authorities]
                    )
                )
            )
        return OpenSSLCertificateOptions(**options)

    def certificateRequest(self, format=crypto.FILETYPE_ASN1, digestAlgorithm="sha256"):
        return self.privateKey.certificateRequest(
            self.getSubject(), format, digestAlgorithm
        )

    def signCertificateRequest(
        self,
        requestData,
        verifyDNCallback,
        serialNumber,
        requestFormat=crypto.FILETYPE_ASN1,
        certificateFormat=crypto.FILETYPE_ASN1,
    ):
        issuer = self.getSubject()
        return self.privateKey.signCertificateRequest(
            issuer,
            requestData,
            verifyDNCallback,
            serialNumber,
            requestFormat,
            certificateFormat,
        )

    def signRequestObject(
        self,
        certificateRequest,
        serialNumber,
        secondsToExpiry=60 * 60 * 24 * 365,  # One year
        digestAlgorithm="sha256",
    ):
        return self.privateKey.signRequestObject(
            self.getSubject(),
            certificateRequest,
            serialNumber,
            secondsToExpiry,
            digestAlgorithm,
        )


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

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.keyHash()}>"

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
        return f"Public Key with Hash: {self.keyHash()}"


class KeyPair(PublicKey):
    @classmethod
    def load(Class, data, format=crypto.FILETYPE_ASN1):
        return Class(crypto.load_privatekey(format, data))

    def dump(self, format=crypto.FILETYPE_ASN1):
        return crypto.dump_privatekey(format, self.original)

    @deprecated(Version("Twisted", 15, 0, 0), "a real persistence system")
    def __getstate__(self):
        return self.dump()

    @deprecated(Version("Twisted", 15, 0, 0), "a real persistence system")
    def __setstate__(self, state):
        self.__init__(crypto.load_privatekey(crypto.FILETYPE_ASN1, state))

    def inspect(self):
        t = self.original.type()
        if t == crypto.TYPE_RSA:
            ts = "RSA"
        elif t == crypto.TYPE_DSA:
            ts = "DSA"
        else:
            ts = "(Unknown Type!)"
        L = (self.original.bits(), ts, self.keyHash())
        return "%s-bit %s Key Pair with Hash: %s" % L

    @classmethod
    def generate(Class, kind=crypto.TYPE_RSA, size=2048):
        pkey = crypto.PKey()
        pkey.generate_key(kind, size)
        return Class(pkey)

    def newCertificate(self, newCertData, format=crypto.FILETYPE_ASN1):
        return PrivateCertificate.load(newCertData, self, format)

    def requestObject(self, distinguishedName, digestAlgorithm="sha256"):
        req = crypto.X509Req()
        req.set_pubkey(self.original)
        distinguishedName._copyInto(req.get_subject())
        req.sign(self.original, digestAlgorithm)
        return CertificateRequest(req)

    def certificateRequest(
        self, distinguishedName, format=crypto.FILETYPE_ASN1, digestAlgorithm="sha256"
    ):
        """
        Create a certificate request signed with this key.

        @return: a string, formatted according to the 'format' argument.
        """
        return self.requestObject(distinguishedName, digestAlgorithm).dump(format)

    def signCertificateRequest(
        self,
        issuerDistinguishedName,
        requestData,
        verifyDNCallback,
        serialNumber,
        requestFormat=crypto.FILETYPE_ASN1,
        certificateFormat=crypto.FILETYPE_ASN1,
        secondsToExpiry=60 * 60 * 24 * 365,  # One year
        digestAlgorithm="sha256",
    ):
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
                raise VerifyError(
                    "DN callback {!r} rejected request DN {!r}".format(
                        verifyDNCallback, dn
                    )
                )
            return self.signRequestObject(
                issuerDistinguishedName,
                hlreq,
                serialNumber,
                secondsToExpiry,
                digestAlgorithm,
            ).dump(certificateFormat)

        if isinstance(vval, Deferred):
            return vval.addCallback(verified)
        else:
            return verified(vval)

    def signRequestObject(
        self,
        issuerDistinguishedName,
        requestObject,
        serialNumber,
        secondsToExpiry=60 * 60 * 24 * 365,  # One year
        digestAlgorithm="sha256",
    ):
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
            self.signRequestObject(dn, self.requestObject(dn), serialNumber), self
        )


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
class OpenSSLCertificateAuthorities:
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

    @since: 16.0

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
                "certificates items must be twisted.internet.ssl.CertBase" " instances"
            )
        certs.append(cert)
    return OpenSSLCertificateAuthorities(certs)


@implementer(IOpenSSLTrustRoot)
class OpenSSLDefaultPaths:
    """
    Trust the set of default verify paths that OpenSSL was built with, as
    specified by U{SSL_CTX_set_default_verify_paths
    <https://www.openssl.org/docs/man1.1.1/man3/SSL_CTX_load_verify_locations.html>}.
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

            - macOS when using the system-installed version of OpenSSL (i.e.
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
        Windows <https://twistedmatrix.com/trac/ticket/6371>}, U{macOS
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
        except BaseException:
            f = Failure()
            log.err(f, "Error during info_callback")
            connection.get_app_data().failVerification(f)

    return infoCallback


@implementer(IOpenSSLClientConnectionCreator)
class ClientTLSOptions:
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

    @ivar _hostnameIsDnsName: Whether or not the C{_hostname} is a DNSName.
        Will be L{False} if C{_hostname} is an IP address or L{True} if
        C{_hostname} is a DNSName
    @type _hostnameIsDnsName: L{bool}
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

        if isIPAddress(hostname) or isIPv6Address(hostname):
            self._hostnameBytes = hostname.encode("ascii")
            self._hostnameIsDnsName = False
        else:
            self._hostnameBytes = _idnaBytes(hostname)
            self._hostnameIsDnsName = True

        self._hostnameASCII = self._hostnameBytes.decode("ascii")
        ctx.set_info_callback(_tolerateErrors(self._identityVerifyingInfoCallback))

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
        # Literal IPv4 and IPv6 addresses are not permitted
        # as host names according to the RFCs
        if where & SSL.SSL_CB_HANDSHAKE_START and self._hostnameIsDnsName:
            connection.set_tlsext_host_name(self._hostnameBytes)
        elif where & SSL.SSL_CB_HANDSHAKE_DONE:
            try:
                if self._hostnameIsDnsName:
                    verifyHostname(connection, self._hostnameASCII)
                else:
                    verifyIPAddress(connection, self._hostnameASCII)
            except VerificationError:
                f = Failure()
                transport = connection.get_app_data()
                transport.failVerification(f)


def optionsForClientTLS(
    hostname,
    trustRoot=None,
    clientCertificate=None,
    acceptableProtocols=None,
    *,
    extraCertificateOptions=None,
):
    """
    Create a L{client connection creator <IOpenSSLClientConnectionCreator>} for
    use with APIs such as L{SSL4ClientEndpoint
    <twisted.internet.endpoints.SSL4ClientEndpoint>}, L{connectSSL
    <twisted.internet.interfaces.IReactorSSL.connectSSL>}, and L{startTLS
    <twisted.internet.interfaces.ITLSTransport.startTLS>}.

    @since: 14.0

    @param hostname: The expected name of the remote host. This serves two
        purposes: first, and most importantly, it verifies that the certificate
        received from the server correctly identifies the specified hostname.
        The second purpose is to use the U{Server Name Indication extension
        <https://en.wikipedia.org/wiki/Server_Name_Indication>} to indicate to
        the server which certificate should be used.
    @type hostname: L{unicode}

    @param trustRoot: Specification of trust requirements of peers. This may be
        a L{Certificate} or the result of L{platformTrust}. By default it is
        L{platformTrust} and you probably shouldn't adjust it unless you really
        know what you're doing. Be aware that clients using this interface
        I{must} verify the server; you cannot explicitly pass L{None} since
        that just means to use L{platformTrust}.
    @type trustRoot: L{IOpenSSLTrustRoot}

    @param clientCertificate: The certificate and private key that the client
        will use to authenticate to the server. If unspecified, the client will
        not authenticate.
    @type clientCertificate: L{PrivateCertificate}

    @param acceptableProtocols: The protocols this peer is willing to speak
        after the TLS negotiation has completed, advertised over both ALPN and
        NPN. If this argument is specified, and no overlap can be found with
        the other peer, the connection will fail to be established. If the
        remote peer does not offer NPN or ALPN, the connection will be
        established, but no protocol wil be negotiated. Protocols earlier in
        the list are preferred over those later in the list.
    @type acceptableProtocols: L{list} of L{bytes}

    @param extraCertificateOptions: A dictionary of additional keyword arguments
        to be presented to L{CertificateOptions}. Please avoid using this unless
        you absolutely need to; any time you need to pass an option here that is
        a bug in this interface.
    @type extraCertificateOptions: L{dict}

    @return: A client connection creator.
    @rtype: L{IOpenSSLClientConnectionCreator}
    """
    if extraCertificateOptions is None:
        extraCertificateOptions = {}
    if trustRoot is None:
        trustRoot = platformTrust()
    if not isinstance(hostname, str):
        raise TypeError(
            "optionsForClientTLS requires text for host names, not "
            + hostname.__class__.__name__
        )
    if clientCertificate:
        extraCertificateOptions.update(
            privateKey=clientCertificate.privateKey.original,
            certificate=clientCertificate.original,
        )
    certificateOptions = OpenSSLCertificateOptions(
        trustRoot=trustRoot,
        acceptableProtocols=acceptableProtocols,
        **extraCertificateOptions,
    )
    return ClientTLSOptions(hostname, certificateOptions.getContext())


@implementer(IOpenSSLContextFactory)
class OpenSSLCertificateOptions:
    """
    A L{CertificateOptions <twisted.internet.ssl.CertificateOptions>} specifies
    the security properties for a client or server TLS connection used with
    OpenSSL.

    @ivar _options: Any option flags to set on the L{OpenSSL.SSL.Context}
        object that will be created.
    @type _options: L{int}

    @ivar _cipherString: An OpenSSL-specific cipher string.
    @type _cipherString: L{unicode}

    @ivar _defaultMinimumTLSVersion: The default TLS version that will be
        negotiated.  This should be a "safe default", with wide client and
        server support, vs an optimally secure one that excludes a large number
        of users.  As of May 2022, TLSv1.2 is that safe default.
    @type _defaultMinimumTLSVersion: L{TLSVersion} constant
    """

    # Factory for creating contexts.  Configurable for testability.
    _contextFactory = SSL.Context
    _context = None

    _OP_NO_TLSv1_3 = _tlsDisableFlags[TLSVersion.TLSv1_3]

    _defaultMinimumTLSVersion = TLSVersion.TLSv1_2

    @_mutuallyExclusiveArguments(
        [
            ["trustRoot", "requireCertificate"],
            ["trustRoot", "verify"],
            ["trustRoot", "caCerts"],
            ["method", "insecurelyLowerMinimumTo"],
            ["method", "raiseMinimumTo"],
            ["raiseMinimumTo", "insecurelyLowerMinimumTo"],
            ["method", "lowerMaximumSecurityTo"],
        ]
    )
    def __init__(
        self,
        privateKey=None,
        certificate=None,
        method=None,
        verify=False,
        caCerts=None,
        verifyDepth=9,
        requireCertificate=True,
        verifyOnce=True,
        enableSingleUseKeys=True,
        enableSessions=False,
        fixBrokenPeers=False,
        enableSessionTickets=False,
        extraCertChain=None,
        acceptableCiphers=None,
        dhParameters=None,
        trustRoot=None,
        acceptableProtocols=None,
        raiseMinimumTo=None,
        insecurelyLowerMinimumTo=None,
        lowerMaximumSecurityTo=None,
    ):
        """
        Create an OpenSSL context SSL connection context factory.

        @param privateKey: A PKey object holding the private key.

        @param certificate: An X509 object holding the certificate.

        @param method: Deprecated, use a combination of
            C{insecurelyLowerMinimumTo}, C{raiseMinimumTo}, or
            C{lowerMaximumSecurityTo} instead.  The SSL protocol to use, one of
            C{TLS_METHOD}, C{TLSv1_2_METHOD}, or C{TLSv1_2_METHOD} (or any
            future method constants provided by pyOpenSSL).  By default, a
            setting will be used which allows TLSv1.2 and TLSv1.3.  Can not be
            used with C{insecurelyLowerMinimumTo}, C{raiseMinimumTo}, or
            C{lowerMaximumSecurityTo}.

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

        @param enableSessions: This allows a shortened handshake to be used
            when a known client reconnects to the same process.  If True,
            enable OpenSSL's session caching.  Note that session caching only
            works on a single Twisted node at once.  Also, it is currently
            somewhat risky due to U{a crashing bug when using OpenSSL 1.1.1
            <https://twistedmatrix.com/trac/ticket/9764>}.

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
            and NPN.  If this argument is specified, and no overlap can be
            found with the other peer, the connection will fail to be
            established.  If the remote peer does not offer NPN or ALPN, the
            connection will be established, but no protocol wil be negotiated.
            Protocols earlier in the list are preferred over those later in the
            list.
        @type acceptableProtocols: L{list} of L{bytes}

        @param raiseMinimumTo: The minimum TLS version that you want to use, or
            Twisted's default if it is higher.  Use this if you want to make
            your client/server more secure than Twisted's default, but will
            accept Twisted's default instead if it moves higher than this
            value.  You probably want to use this over
            C{insecurelyLowerMinimumTo}.
        @type raiseMinimumTo: L{TLSVersion} constant

        @param insecurelyLowerMinimumTo: The minimum TLS version to use,
            possibly lower than Twisted's default.  If not specified, it is a
            generally considered safe default (TLSv1.0).  If you want to raise
            your minimum TLS version to above that of this default, use
            C{raiseMinimumTo}.  DO NOT use this argument unless you are
            absolutely sure this is what you want.
        @type insecurelyLowerMinimumTo: L{TLSVersion} constant

        @param lowerMaximumSecurityTo: The maximum TLS version to use.  If not
            specified, it is the most recent your OpenSSL supports.  You only
            want to set this if the peer that you are communicating with has
            problems with more recent TLS versions, it lowers your security
            when communicating with newer peers.  DO NOT use this argument
            unless you are absolutely sure this is what you want.
        @type lowerMaximumSecurityTo: L{TLSVersion} constant

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
        @raise TypeError: if C{method} is passed in combination with
            C{tlsProtocols}.  Please prefer the more explicit C{tlsProtocols}
            in new code.

        @raises NotImplementedError: If acceptableProtocols were provided but
            no negotiation mechanism is available.
        """

        if (privateKey is None) != (certificate is None):
            raise ValueError("Specify neither or both of privateKey and certificate")
        self.privateKey = privateKey
        self.certificate = certificate

        # Set basic security options: disallow insecure SSLv2, disallow TLS
        # compression to avoid CRIME attack, make the server choose the
        # ciphers.
        self._options = (
            SSL.OP_NO_SSLv2 | SSL.OP_NO_COMPRESSION | SSL.OP_CIPHER_SERVER_PREFERENCE
        )

        # Set the mode to Release Buffers, which demallocs send/recv buffers on
        # idle TLS connections to save memory
        self._mode = SSL.MODE_RELEASE_BUFFERS

        if method is None:
            self.method = SSL.TLS_METHOD

            if raiseMinimumTo:
                if lowerMaximumSecurityTo and raiseMinimumTo > lowerMaximumSecurityTo:
                    raise ValueError(
                        "raiseMinimumTo needs to be lower than "
                        "lowerMaximumSecurityTo"
                    )

                if raiseMinimumTo > self._defaultMinimumTLSVersion:
                    insecurelyLowerMinimumTo = raiseMinimumTo

            if insecurelyLowerMinimumTo is None:
                insecurelyLowerMinimumTo = self._defaultMinimumTLSVersion

                # If you set the max lower than the default, but don't set the
                # minimum, pull it down to that
                if (
                    lowerMaximumSecurityTo
                    and insecurelyLowerMinimumTo > lowerMaximumSecurityTo
                ):
                    insecurelyLowerMinimumTo = lowerMaximumSecurityTo

            if (
                lowerMaximumSecurityTo
                and insecurelyLowerMinimumTo > lowerMaximumSecurityTo
            ):
                raise ValueError(
                    "insecurelyLowerMinimumTo needs to be lower than "
                    "lowerMaximumSecurityTo"
                )

            excludedVersions = _getExcludedTLSProtocols(
                insecurelyLowerMinimumTo, lowerMaximumSecurityTo
            )

            for version in excludedVersions:
                self._options |= _tlsDisableFlags[version]
        else:
            warnings.warn(
                (
                    "Passing method to twisted.internet.ssl.CertificateOptions "
                    "was deprecated in Twisted 17.1.0. Please use a combination "
                    "of insecurelyLowerMinimumTo, raiseMinimumTo, and "
                    "lowerMaximumSecurityTo instead, as Twisted will correctly "
                    "configure the method."
                ),
                DeprecationWarning,
                stacklevel=3,
            )

            # Otherwise respect the application decision.
            self.method = method

        if verify and not caCerts:
            raise ValueError(
                "Specify client CA certificate information if and"
                " only if enabling certificate verification"
            )
        self.verify = verify
        if extraCertChain is not None and None in (privateKey, certificate):
            raise ValueError(
                "A private key and a certificate are required "
                "when adding a supplemental certificate chain."
            )
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
            self._options |= SSL.OP_SINGLE_DH_USE | SSL.OP_SINGLE_ECDH_USE
        self.enableSessions = enableSessions
        self.fixBrokenPeers = fixBrokenPeers
        if fixBrokenPeers:
            self._options |= SSL.OP_ALL
        self.enableSessionTickets = enableSessionTickets

        if not enableSessionTickets:
            self._options |= SSL.OP_NO_TICKET
        self.dhParameters = dhParameters

        self._ecChooser = _ChooseDiffieHellmanEllipticCurve(
            SSL.OPENSSL_VERSION_NUMBER,
            openSSLlib=pyOpenSSLlib,
            openSSLcrypto=crypto,
        )

        if acceptableCiphers is None:
            acceptableCiphers = defaultCiphers
        # This needs to run when method and _options are finalized.
        self._cipherString = ":".join(
            c.fullName
            for c in acceptableCiphers.selectCiphers(
                _expandCipherString("ALL", self.method, self._options)
            )
        )
        if self._cipherString == "":
            raise ValueError(
                "Supplied IAcceptableCiphers yielded no usable ciphers "
                "on this platform."
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
            del d["_context"]
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
        ctx.set_mode(self._mode)

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

        ctx.set_verify(verifyFlags)
        if self.verifyDepth is not None:
            ctx.set_verify_depth(self.verifyDepth)

        # Until we know what's going on with
        # https://twistedmatrix.com/trac/ticket/9764 let's be conservative
        # in naming this; ASCII-only, short, as the recommended value (a
        # hostname) might be:
        sessionIDContext = hexlify(secureRandom(7))
        # Note that this doesn't actually set the session ID (which had
        # better be per-connection anyway!):
        # https://github.com/pyca/pyopenssl/issues/845

        # This is set unconditionally because it's apparently required for
        # client certificates to work:
        # https://www.openssl.org/docs/man1.1.1/man3/SSL_CTX_set_session_id_context.html
        ctx.set_session_id(sessionIDContext)

        if self.enableSessions:
            ctx.set_session_cache_mode(SSL.SESS_CACHE_SERVER)
        else:
            ctx.set_session_cache_mode(SSL.SESS_CACHE_OFF)

        if self.dhParameters:
            ctx.load_tmp_dh(self.dhParameters._dhFile.path)
        ctx.set_cipher_list(self._cipherString.encode("ascii"))

        self._ecChooser.configureECDHCurve(ctx)

        if self._acceptableProtocols:
            # Try to set NPN and ALPN. _acceptableProtocols cannot be set by
            # the constructor unless at least one mechanism is supported.
            _setAcceptableProtocols(ctx, self._acceptableProtocols)

        return ctx


OpenSSLCertificateOptions.__getstate__ = deprecated(
    Version("Twisted", 15, 0, 0), "a real persistence system"
)(OpenSSLCertificateOptions.__getstate__)
OpenSSLCertificateOptions.__setstate__ = deprecated(
    Version("Twisted", 15, 0, 0), "a real persistence system"
)(OpenSSLCertificateOptions.__setstate__)


@implementer(ICipher)
@attr.s(frozen=True, auto_attribs=True)
class OpenSSLCipher:
    """
    A representation of an OpenSSL cipher.

    @ivar fullName: The full name of the cipher. For example
        C{u"ECDHE-RSA-AES256-GCM-SHA384"}.
    @type fullName: L{unicode}
    """

    fullName: str


@lru_cache(maxsize=32)
def _expandCipherString(cipherString, method, options):
    """
    Expand C{cipherString} according to C{method} and C{options} to a tuple of
    explicit ciphers that are supported by the current platform.

    @param cipherString: An OpenSSL cipher string to expand.
    @type cipherString: L{unicode}

    @param method: An OpenSSL method like C{SSL.TLS_METHOD} used for
        determining the effective ciphers.

    @param options: OpenSSL options like C{SSL.OP_NO_SSLv3} ORed together.
    @type options: L{int}

    @return: The effective list of explicit ciphers that results from the
        arguments on the current platform.
    @rtype: L{tuple} of L{ICipher}
    """
    ctx = SSL.Context(method)
    ctx.set_options(options)
    try:
        ctx.set_cipher_list(cipherString.encode("ascii"))
    except SSL.Error as e:
        # OpenSSL 1.1.1 turns an invalid cipher list into TLS 1.3
        # ciphers, so pyOpenSSL >= 19.0.0 raises an artificial Error
        # that lacks a corresponding OpenSSL error if the cipher list
        # consists only of these after a call to set_cipher_list.
        if not e.args[0]:
            return tuple()
        if e.args[0][0][2] == "no cipher match":
            return tuple()
        else:
            raise
    conn = SSL.Connection(ctx, None)
    ciphers = conn.get_cipher_list()
    if isinstance(ciphers[0], str):
        return tuple(OpenSSLCipher(cipher) for cipher in ciphers)
    else:
        return tuple(OpenSSLCipher(cipher.decode("ascii")) for cipher in ciphers)


@lru_cache(maxsize=128)
def _selectCiphers(wantedCiphers, availableCiphers):
    """
    Caclulate the acceptable list of ciphers from the ciphers we want and the
    ciphers we have support for.

    @param wantedCiphers: The ciphers we want to use.
    @type wantedCiphers: L{tuple} of L{OpenSSLCipher}

    @param availableCiphers: The ciphers we have available to use.
    @type availableCiphers: L{tuple} of L{OpenSSLCipher}

    @rtype: L{tuple} of L{OpenSSLCipher}
    """
    return tuple(cipher for cipher in wantedCiphers if cipher in availableCiphers)


@implementer(IAcceptableCiphers)
class OpenSSLAcceptableCiphers:
    """
    A representation of ciphers that are acceptable for TLS connections.
    """

    def __init__(self, ciphers):
        self._ciphers = tuple(ciphers)

    def selectCiphers(self, availableCiphers):
        return _selectCiphers(self._ciphers, tuple(availableCiphers))

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
        return cls(
            _expandCipherString(
                nativeString(cipherString),
                SSL.TLS_METHOD,
                SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3,
            )
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
    "TLS13-AES-256-GCM-SHA384:TLS13-CHACHA20-POLY1305-SHA256:"
    "TLS13-AES-128-GCM-SHA256:"
    "ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:DH+CHACHA20:ECDH+AES256:DH+AES256:"
    "ECDH+AES128:DH+AES:RSA+AESGCM:RSA+AES:"
    "!aNULL:!MD5:!DSS"
)
_defaultCurveName = "prime256v1"


class _ChooseDiffieHellmanEllipticCurve:
    """
    Chooses the best elliptic curve for Elliptic Curve Diffie-Hellman
    key exchange, and provides a C{configureECDHCurve} method to set
    the curve, when appropriate, on a new L{OpenSSL.SSL.Context}.

    The C{configureECDHCurve} method will be set to one of the
    following based on the provided OpenSSL version and configuration:

        - L{_configureOpenSSL110}

        - L{_configureOpenSSL102}

        - L{_configureOpenSSL101}

        - L{_configureOpenSSL101NoCurves}.

    @param openSSLVersion: The OpenSSL version number.
    @type openSSLVersion: L{int}

    @see: L{OpenSSL.SSL.OPENSSL_VERSION_NUMBER}

    @param openSSLlib: The OpenSSL C{cffi} library module.
    @param openSSLcrypto: The OpenSSL L{crypto} module.

    @see: L{crypto}
    """

    def __init__(self, openSSLVersion, openSSLlib, openSSLcrypto):
        self._openSSLlib = openSSLlib
        self._openSSLcrypto = openSSLcrypto
        if openSSLVersion >= 0x10100000:
            self.configureECDHCurve = self._configureOpenSSL110
        elif openSSLVersion >= 0x10002000:
            self.configureECDHCurve = self._configureOpenSSL102
        else:
            try:
                self._ecCurve = openSSLcrypto.get_elliptic_curve(_defaultCurveName)
            except ValueError:
                # The get_elliptic_curve method raises a ValueError
                # when the curve does not exist.
                self.configureECDHCurve = self._configureOpenSSL101NoCurves
            else:
                self.configureECDHCurve = self._configureOpenSSL101

    def _configureOpenSSL110(self, ctx):
        """
        OpenSSL 1.1.0 Contexts are preconfigured with an optimal set
        of ECDH curves.  This method does nothing.

        @param ctx: L{OpenSSL.SSL.Context}
        """

    def _configureOpenSSL102(self, ctx):
        """
        Have the context automatically choose elliptic curves for
        ECDH.  Run on OpenSSL 1.0.2 and OpenSSL 1.1.0+, but only has
        an effect on OpenSSL 1.0.2.

        @param ctx: The context which .
        @type ctx: L{OpenSSL.SSL.Context}
        """
        ctxPtr = ctx._context
        try:
            self._openSSLlib.SSL_CTX_set_ecdh_auto(ctxPtr, True)
        except BaseException:
            pass

    def _configureOpenSSL101(self, ctx):
        """
        Set the default elliptic curve for ECDH on the context.  Only
        run on OpenSSL 1.0.1.

        @param ctx: The context on which to set the ECDH curve.
        @type ctx: L{OpenSSL.SSL.Context}
        """
        try:
            ctx.set_tmp_ecdh(self._ecCurve)
        except BaseException:
            pass

    def _configureOpenSSL101NoCurves(self, ctx):
        """
        No elliptic curves are available on OpenSSL 1.0.1. We can't
        set anything, so do nothing.

        @param ctx: The context on which to set the ECDH curve.
        @type ctx: L{OpenSSL.SSL.Context}
        """


class OpenSSLDiffieHellmanParameters:
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

        C{openssl dhparam -out dh_param_2048.pem -2 2048}

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
            return b""

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
