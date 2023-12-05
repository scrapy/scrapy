# -*- test-case-name: twisted.conch.test.test_transport -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
SSH key exchange handling.
"""


from hashlib import sha1, sha256, sha384, sha512

from zope.interface import Attribute, Interface, implementer

from twisted.conch import error


class _IKexAlgorithm(Interface):
    """
    An L{_IKexAlgorithm} describes a key exchange algorithm.
    """

    preference = Attribute(
        "An L{int} giving the preference of the algorithm when negotiating "
        "key exchange. Algorithms with lower precedence values are more "
        "preferred."
    )

    hashProcessor = Attribute(
        "A callable hash algorithm constructor (e.g. C{hashlib.sha256}) "
        "suitable for use with this key exchange algorithm."
    )


class _IFixedGroupKexAlgorithm(_IKexAlgorithm):
    """
    An L{_IFixedGroupKexAlgorithm} describes a key exchange algorithm with a
    fixed prime / generator group.
    """

    prime = Attribute(
        "An L{int} giving the prime number used in Diffie-Hellman key "
        "exchange, or L{None} if not applicable."
    )

    generator = Attribute(
        "An L{int} giving the generator number used in Diffie-Hellman key "
        "exchange, or L{None} if not applicable. (This is not related to "
        "Python generator functions.)"
    )


class _IEllipticCurveExchangeKexAlgorithm(_IKexAlgorithm):
    """
    An L{_IEllipticCurveExchangeKexAlgorithm} describes a key exchange algorithm
    that uses an elliptic curve exchange between the client and server.
    """


class _IGroupExchangeKexAlgorithm(_IKexAlgorithm):
    """
    An L{_IGroupExchangeKexAlgorithm} describes a key exchange algorithm
    that uses group exchange between the client and server.

    A prime / generator group should be chosen at run time based on the
    requested size. See RFC 4419.
    """


@implementer(_IEllipticCurveExchangeKexAlgorithm)
class _Curve25519SHA256:
    """
    Elliptic Curve Key Exchange using Curve25519 and SHA256. Defined in
    U{https://datatracker.ietf.org/doc/draft-ietf-curdle-ssh-curves/}.
    """

    preference = 1
    hashProcessor = sha256


@implementer(_IEllipticCurveExchangeKexAlgorithm)
class _Curve25519SHA256LibSSH:
    """
    As L{_Curve25519SHA256}, but with a pre-standardized algorithm name.
    """

    preference = 2
    hashProcessor = sha256


@implementer(_IEllipticCurveExchangeKexAlgorithm)
class _ECDH256:
    """
    Elliptic Curve Key Exchange with SHA-256 as HASH. Defined in
    RFC 5656.

    Note that C{ecdh-sha2-nistp256} takes priority over nistp384 or nistp512.
    This is the same priority from OpenSSH.

    C{ecdh-sha2-nistp256} is considered preety good cryptography.
    If you need something better consider using C{curve25519-sha256}.
    """

    preference = 3
    hashProcessor = sha256


@implementer(_IEllipticCurveExchangeKexAlgorithm)
class _ECDH384:
    """
    Elliptic Curve Key Exchange with SHA-384 as HASH. Defined in
    RFC 5656.
    """

    preference = 4
    hashProcessor = sha384


@implementer(_IEllipticCurveExchangeKexAlgorithm)
class _ECDH512:
    """
    Elliptic Curve Key Exchange with SHA-512 as HASH. Defined in
    RFC 5656.
    """

    preference = 5
    hashProcessor = sha512


@implementer(_IGroupExchangeKexAlgorithm)
class _DHGroupExchangeSHA256:
    """
    Diffie-Hellman Group and Key Exchange with SHA-256 as HASH. Defined in
    RFC 4419, 4.2.
    """

    preference = 6
    hashProcessor = sha256


@implementer(_IGroupExchangeKexAlgorithm)
class _DHGroupExchangeSHA1:
    """
    Diffie-Hellman Group and Key Exchange with SHA-1 as HASH. Defined in
    RFC 4419, 4.1.
    """

    preference = 7
    hashProcessor = sha1


@implementer(_IFixedGroupKexAlgorithm)
class _DHGroup14SHA1:
    """
    Diffie-Hellman key exchange with SHA-1 as HASH and Oakley Group 14
    (2048-bit MODP Group). Defined in RFC 4253, 8.2.
    """

    preference = 8
    hashProcessor = sha1
    # Diffie-Hellman primes from Oakley Group 14 (RFC 3526, 3).
    prime = int(
        "323170060713110073003389139264238282488179412411402391128420"
        "097514007417066343542226196894173635693471179017379097041917"
        "546058732091950288537589861856221532121754125149017745202702"
        "357960782362488842461894775876411059286460994117232454266225"
        "221932305409190376805242355191256797158701170010580558776510"
        "388618472802579760549035697325615261670813393617995413364765"
        "591603683178967290731783845896806396719009772021941686472258"
        "710314113364293195361934716365332097170774482279885885653692"
        "086452966360772502689555059283627511211740969729980684105543"
        "595848665832916421362182310789909994486524682624169720359118"
        "52507045361090559"
    )
    generator = 2


# Which ECDH hash function to use is dependent on the size.
_kexAlgorithms = {
    b"curve25519-sha256": _Curve25519SHA256(),
    b"curve25519-sha256@libssh.org": _Curve25519SHA256LibSSH(),
    b"diffie-hellman-group-exchange-sha256": _DHGroupExchangeSHA256(),
    b"diffie-hellman-group-exchange-sha1": _DHGroupExchangeSHA1(),
    b"diffie-hellman-group14-sha1": _DHGroup14SHA1(),
    b"ecdh-sha2-nistp256": _ECDH256(),
    b"ecdh-sha2-nistp384": _ECDH384(),
    b"ecdh-sha2-nistp521": _ECDH512(),
}


def getKex(kexAlgorithm):
    """
    Get a description of a named key exchange algorithm.

    @param kexAlgorithm: The key exchange algorithm name.
    @type kexAlgorithm: L{bytes}

    @return: A description of the key exchange algorithm named by
        C{kexAlgorithm}.
    @rtype: L{_IKexAlgorithm}

    @raises ConchError: if the key exchange algorithm is not found.
    """
    if kexAlgorithm not in _kexAlgorithms:
        raise error.ConchError(f"Unsupported key exchange algorithm: {kexAlgorithm}")
    return _kexAlgorithms[kexAlgorithm]


def isEllipticCurve(kexAlgorithm):
    """
    Returns C{True} if C{kexAlgorithm} is an elliptic curve.

    @param kexAlgorithm: The key exchange algorithm name.
    @type kexAlgorithm: C{str}

    @return: C{True} if C{kexAlgorithm} is an elliptic curve,
        otherwise C{False}.
    @rtype: C{bool}
    """
    return _IEllipticCurveExchangeKexAlgorithm.providedBy(getKex(kexAlgorithm))


def isFixedGroup(kexAlgorithm):
    """
    Returns C{True} if C{kexAlgorithm} has a fixed prime / generator group.

    @param kexAlgorithm: The key exchange algorithm name.
    @type kexAlgorithm: L{bytes}

    @return: C{True} if C{kexAlgorithm} has a fixed prime / generator group,
        otherwise C{False}.
    @rtype: L{bool}
    """
    return _IFixedGroupKexAlgorithm.providedBy(getKex(kexAlgorithm))


def getHashProcessor(kexAlgorithm):
    """
    Get the hash algorithm callable to use in key exchange.

    @param kexAlgorithm: The key exchange algorithm name.
    @type kexAlgorithm: L{bytes}

    @return: A callable hash algorithm constructor (e.g. C{hashlib.sha256}).
    @rtype: C{callable}
    """
    kex = getKex(kexAlgorithm)
    return kex.hashProcessor


def getDHGeneratorAndPrime(kexAlgorithm):
    """
    Get the generator and the prime to use in key exchange.

    @param kexAlgorithm: The key exchange algorithm name.
    @type kexAlgorithm: L{bytes}

    @return: A L{tuple} containing L{int} generator and L{int} prime.
    @rtype: L{tuple}
    """
    kex = getKex(kexAlgorithm)
    return kex.generator, kex.prime


def getSupportedKeyExchanges():
    """
    Get a list of supported key exchange algorithm names in order of
    preference.

    @return: A C{list} of supported key exchange algorithm names.
    @rtype: C{list} of L{bytes}
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import ec

    from twisted.conch.ssh.keys import _curveTable

    backend = default_backend()
    kexAlgorithms = _kexAlgorithms.copy()
    for keyAlgorithm in list(kexAlgorithms):
        if keyAlgorithm.startswith(b"ecdh"):
            keyAlgorithmDsa = keyAlgorithm.replace(b"ecdh", b"ecdsa")
            supported = backend.elliptic_curve_exchange_algorithm_supported(
                ec.ECDH(), _curveTable[keyAlgorithmDsa]
            )
        elif keyAlgorithm.startswith(b"curve25519-sha256"):
            supported = backend.x25519_supported()
        else:
            supported = True
        if not supported:
            kexAlgorithms.pop(keyAlgorithm)
    return sorted(
        kexAlgorithms, key=lambda kexAlgorithm: kexAlgorithms[kexAlgorithm].preference
    )
