# -*- test-case-name: twisted.conch.test.test_transport -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
SSH key exchange handling.
"""

from __future__ import absolute_import, division

from hashlib import sha1, sha256

from zope.interface import Attribute, implementer, Interface

from twisted.conch import error
from twisted.python.compat import long


class _IKexAlgorithm(Interface):
    """
    An L{_IKexAlgorithm} describes a key exchange algorithm.
    """

    preference = Attribute(
        "An L{int} giving the preference of the algorithm when negotiating "
        "key exchange. Algorithms with lower precedence values are more "
        "preferred.")

    hashProcessor = Attribute(
        "A callable hash algorithm constructor (e.g. C{hashlib.sha256}) "
        "suitable for use with this key exchange algorithm.")



class _IFixedGroupKexAlgorithm(_IKexAlgorithm):
    """
    An L{_IFixedGroupKexAlgorithm} describes a key exchange algorithm with a
    fixed prime / generator group.
    """

    prime = Attribute(
        "A L{long} giving the prime number used in Diffie-Hellman key "
        "exchange, or L{None} if not applicable.")

    generator = Attribute(
        "A L{long} giving the generator number used in Diffie-Hellman key "
        "exchange, or L{None} if not applicable. (This is not related to "
        "Python generator functions.)")



class _IGroupExchangeKexAlgorithm(_IKexAlgorithm):
    """
    An L{_IGroupExchangeKexAlgorithm} describes a key exchange algorithm
    that uses group exchange between the client and server.

    A prime / generator group should be chosen at run time based on the
    requested size. See RFC 4419.
    """



@implementer(_IGroupExchangeKexAlgorithm)
class _DHGroupExchangeSHA256(object):
    """
    Diffie-Hellman Group and Key Exchange with SHA-256 as HASH. Defined in
    RFC 4419, 4.2.
    """

    preference = 1
    hashProcessor = sha256



@implementer(_IGroupExchangeKexAlgorithm)
class _DHGroupExchangeSHA1(object):
    """
    Diffie-Hellman Group and Key Exchange with SHA-1 as HASH. Defined in
    RFC 4419, 4.1.
    """

    preference = 2
    hashProcessor = sha1



@implementer(_IFixedGroupKexAlgorithm)
class _DHGroup1SHA1(object):
    """
    Diffie-Hellman key exchange with SHA-1 as HASH, and Oakley Group 2
    (1024-bit MODP Group). Defined in RFC 4253, 8.1.
    """

    preference = 3
    hashProcessor = sha1
    # Diffie-Hellman primes from Oakley Group 2 (RFC 2409, 6.2).
    prime = long('17976931348623159077083915679378745319786029604875601170644'
        '44236841971802161585193689478337958649255415021805654859805036464405'
        '48199239100050792877003355816639229553136239076508735759914822574862'
        '57500742530207744771258955095793777842444242661733472762929938766870'
        '9205606050270810842907692932019128194467627007')
    generator = 2



@implementer(_IFixedGroupKexAlgorithm)
class _DHGroup14SHA1(object):
    """
    Diffie-Hellman key exchange with SHA-1 as HASH and Oakley Group 14
    (2048-bit MODP Group). Defined in RFC 4253, 8.2.
    """

    preference = 4
    hashProcessor = sha1
    # Diffie-Hellman primes from Oakley Group 14 (RFC 3526, 3).
    prime = long('32317006071311007300338913926423828248817941241140239112842'
        '00975140074170663435422261968941736356934711790173790970419175460587'
        '32091950288537589861856221532121754125149017745202702357960782362488'
        '84246189477587641105928646099411723245426622522193230540919037680524'
        '23551912567971587011700105805587765103886184728025797605490356973256'
        '15261670813393617995413364765591603683178967290731783845896806396719'
        '00977202194168647225871031411336429319536193471636533209717077448227'
        '98858856536920864529663607725026895550592836275112117409697299806841'
        '05543595848665832916421362182310789909994486524682624169720359118525'
        '07045361090559')
    generator = 2



_kexAlgorithms = {
    b"diffie-hellman-group-exchange-sha256": _DHGroupExchangeSHA256(),
    b"diffie-hellman-group-exchange-sha1": _DHGroupExchangeSHA1(),
    b"diffie-hellman-group1-sha1": _DHGroup1SHA1(),
    b"diffie-hellman-group14-sha1": _DHGroup14SHA1(),
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
        raise error.ConchError(
            "Unsupported key exchange algorithm: %s" % (kexAlgorithm,))
    return _kexAlgorithms[kexAlgorithm]



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

    @return: A L{tuple} containing L{long} generator and L{long} prime.
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
    return sorted(
        _kexAlgorithms,
        key = lambda kexAlgorithm: _kexAlgorithms[kexAlgorithm].preference)
