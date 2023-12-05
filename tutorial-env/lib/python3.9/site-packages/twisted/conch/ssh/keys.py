# -*- test-case-name: twisted.conch.test.test_keys -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Handling of RSA, DSA, ECDSA, and Ed25519 keys.
"""


import binascii
import itertools
import struct
import unicodedata
import warnings
from base64 import b64encode, decodebytes, encodebytes
from hashlib import md5, sha256
from typing import Optional, Type

import bcrypt
from cryptography import utils
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_ssh_public_key,
)
from pyasn1.codec.ber import (  # type: ignore[import]
    decoder as berDecoder,
    encoder as berEncoder,
)
from pyasn1.error import PyAsn1Error  # type: ignore[import]
from pyasn1.type import univ  # type: ignore[import]

from twisted.conch.ssh import common, sexpy
from twisted.conch.ssh.common import int_to_bytes
from twisted.python import randbytes
from twisted.python.compat import iterbytes, nativeString
from twisted.python.constants import NamedConstant, Names
from twisted.python.deprecate import _mutuallyExclusiveArguments

try:

    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
        encode_dss_signature,
    )
except ImportError:
    from cryptography.hazmat.primitives.asymmetric.utils import (  # type: ignore[no-redef,attr-defined]
        decode_rfc6979_signature as decode_dss_signature,
        encode_rfc6979_signature as encode_dss_signature,
    )


# Curve lookup table
_curveTable = {
    b"ecdsa-sha2-nistp256": ec.SECP256R1(),
    b"ecdsa-sha2-nistp384": ec.SECP384R1(),
    b"ecdsa-sha2-nistp521": ec.SECP521R1(),
}

_secToNist = {
    b"secp256r1": b"nistp256",
    b"secp384r1": b"nistp384",
    b"secp521r1": b"nistp521",
}


Ed25519PublicKey: Optional[Type[ed25519.Ed25519PublicKey]]
Ed25519PrivateKey: Optional[Type[ed25519.Ed25519PrivateKey]]

if default_backend().ed25519_supported():
    Ed25519PublicKey = ed25519.Ed25519PublicKey
    Ed25519PrivateKey = ed25519.Ed25519PrivateKey
else:  # pragma: no cover
    try:
        from twisted.conch.ssh._keys_pynacl import Ed25519PrivateKey, Ed25519PublicKey
    except ImportError:
        Ed25519PublicKey = None
        Ed25519PrivateKey = None


class BadKeyError(Exception):
    """
    Raised when a key isn't what we expected from it.

    XXX: we really need to check for bad keys
    """


class BadSignatureAlgorithmError(Exception):
    """
    Raised when a public key signature algorithm name isn't defined for this
    public key format.
    """


class EncryptedKeyError(Exception):
    """
    Raised when an encrypted key is presented to fromString/fromFile without
    a password.
    """


class BadFingerPrintFormat(Exception):
    """
    Raises when unsupported fingerprint formats are presented to fingerprint.
    """


class FingerprintFormats(Names):
    """
    Constants representing the supported formats of key fingerprints.

    @cvar MD5_HEX: Named constant representing fingerprint format generated
        using md5[RFC1321] algorithm in hexadecimal encoding.
    @type MD5_HEX: L{twisted.python.constants.NamedConstant}

    @cvar SHA256_BASE64: Named constant representing fingerprint format
        generated using sha256[RFC4634] algorithm in base64 encoding
    @type SHA256_BASE64: L{twisted.python.constants.NamedConstant}
    """

    MD5_HEX = NamedConstant()
    SHA256_BASE64 = NamedConstant()


class PassphraseNormalizationError(Exception):
    """
    Raised when a passphrase contains Unicode characters that cannot be
    normalized using the available Unicode character database.
    """


def _normalizePassphrase(passphrase):
    """
    Normalize a passphrase, which may be Unicode.

    If the passphrase is Unicode, this follows the requirements of U{NIST
    800-63B, section
    5.1.1.2<https://pages.nist.gov/800-63-3/sp800-63b.html#memsecretver>}
    for Unicode characters in memorized secrets: it applies the
    Normalization Process for Stabilized Strings using NFKC normalization.
    The passphrase is then encoded using UTF-8.

    @type passphrase: L{bytes} or L{unicode} or L{None}
    @param passphrase: The passphrase to normalize.

    @return: The normalized passphrase, if any.
    @rtype: L{bytes} or L{None}
    @raises PassphraseNormalizationError: if the passphrase is Unicode and
    cannot be normalized using the available Unicode character database.
    """
    if isinstance(passphrase, str):
        # The Normalization Process for Stabilized Strings requires aborting
        # with an error if the string contains any unassigned code point.
        if any(unicodedata.category(c) == "Cn" for c in passphrase):
            # Perhaps not very helpful, but we don't want to leak any other
            # information about the passphrase.
            raise PassphraseNormalizationError()
        return unicodedata.normalize("NFKC", passphrase).encode("UTF-8")
    else:
        return passphrase


class Key:
    """
    An object representing a key.  A key can be either a public or
    private key.  A public key can verify a signature; a private key can
    create or verify a signature.  To generate a string that can be stored
    on disk, use the toString method.  If you have a private key, but want
    the string representation of the public key, use Key.public().toString().
    """

    @classmethod
    def fromFile(cls, filename, type=None, passphrase=None):
        """
        Load a key from a file.

        @param filename: The path to load key data from.

        @type type: L{str} or L{None}
        @param type: A string describing the format the key data is in, or
        L{None} to attempt detection of the type.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase the key is encrypted with, or L{None}
        if there is no encryption.

        @rtype: L{Key}
        @return: The loaded key.
        """
        with open(filename, "rb") as f:
            return cls.fromString(f.read(), type, passphrase)

    @classmethod
    def fromString(cls, data, type=None, passphrase=None):
        """
        Return a Key object corresponding to the string data.
        type is optionally the type of string, matching a _fromString_*
        method.  Otherwise, the _guessStringType() classmethod will be used
        to guess a type.  If the key is encrypted, passphrase is used as
        the decryption key.

        @type data: L{bytes}
        @param data: The key data.

        @type type: L{str} or L{None}
        @param type: A string describing the format the key data is in, or
        L{None} to attempt detection of the type.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase the key is encrypted with, or L{None}
        if there is no encryption.

        @rtype: L{Key}
        @return: The loaded key.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        passphrase = _normalizePassphrase(passphrase)
        if type is None:
            type = cls._guessStringType(data)
        if type is None:
            raise BadKeyError(f"cannot guess the type of {data!r}")
        method = getattr(cls, f"_fromString_{type.upper()}", None)
        if method is None:
            raise BadKeyError(f"no _fromString method for {type}")
        if method.__code__.co_argcount == 2:  # No passphrase
            if passphrase:
                raise BadKeyError("key not encrypted")
            return method(data)
        else:
            return method(data, passphrase)

    @classmethod
    def _fromString_BLOB(cls, blob):
        """
        Return a public key object corresponding to this public key blob.
        The format of a RSA public key blob is::
            string 'ssh-rsa'
            integer e
            integer n

        The format of a DSA public key blob is::
            string 'ssh-dss'
            integer p
            integer q
            integer g
            integer y

        The format of ECDSA-SHA2-* public key blob is::
            string 'ecdsa-sha2-[identifier]'
            integer x
            integer y

            identifier is the standard NIST curve name.

        The format of an Ed25519 public key blob is::
            string 'ssh-ed25519'
            string a

        @type blob: L{bytes}
        @param blob: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type (the first string) is unknown.
        """
        keyType, rest = common.getNS(blob)
        if keyType == b"ssh-rsa":
            e, n, rest = common.getMP(rest, 2)
            return cls(rsa.RSAPublicNumbers(e, n).public_key(default_backend()))
        elif keyType == b"ssh-dss":
            p, q, g, y, rest = common.getMP(rest, 4)
            return cls(
                dsa.DSAPublicNumbers(
                    y=y, parameter_numbers=dsa.DSAParameterNumbers(p=p, q=q, g=g)
                ).public_key(default_backend())
            )
        elif keyType in _curveTable:
            return cls(
                ec.EllipticCurvePublicKey.from_encoded_point(
                    _curveTable[keyType], common.getNS(rest, 2)[1]
                )
            )
        elif keyType == b"ssh-ed25519":
            a, rest = common.getNS(rest)
            return cls._fromEd25519Components(a)
        else:
            raise BadKeyError(f"unknown blob type: {keyType}")

    @classmethod
    def _fromString_PRIVATE_BLOB(cls, blob):
        """
        Return a private key object corresponding to this private key blob.
        The blob formats are as follows:

        RSA keys::
            string 'ssh-rsa'
            integer n
            integer e
            integer d
            integer u
            integer p
            integer q

        DSA keys::
            string 'ssh-dss'
            integer p
            integer q
            integer g
            integer y
            integer x

        EC keys::
            string 'ecdsa-sha2-[identifier]'
            string identifier
            string q
            integer privateValue

            identifier is the standard NIST curve name.

        Ed25519 keys::
            string 'ssh-ed25519'
            string a
            string k || a


        @type blob: L{bytes}
        @param blob: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if
            * the key type (the first string) is unknown
            * the curve name of an ECDSA key does not match the key type
        """
        keyType, rest = common.getNS(blob)

        if keyType == b"ssh-rsa":
            n, e, d, u, p, q, rest = common.getMP(rest, 6)
            return cls._fromRSAComponents(n=n, e=e, d=d, p=p, q=q)
        elif keyType == b"ssh-dss":
            p, q, g, y, x, rest = common.getMP(rest, 5)
            return cls._fromDSAComponents(y=y, g=g, p=p, q=q, x=x)
        elif keyType in _curveTable:
            curve = _curveTable[keyType]
            curveName, q, rest = common.getNS(rest, 2)
            if curveName != _secToNist[curve.name.encode("ascii")]:
                raise BadKeyError(
                    "ECDSA curve name %r does not match key "
                    "type %r" % (curveName, keyType)
                )
            privateValue, rest = common.getMP(rest)
            return cls._fromECEncodedPoint(
                encodedPoint=q, curve=keyType, privateValue=privateValue
            )
        elif keyType == b"ssh-ed25519":
            # OpenSSH's format repeats the public key bytes for some reason.
            # We're only interested in the private key here anyway.
            a, combined, rest = common.getNS(rest, 2)
            k = combined[:32]
            return cls._fromEd25519Components(a, k=k)
        else:
            raise BadKeyError(f"unknown blob type: {keyType}")

    @classmethod
    def _fromString_PUBLIC_OPENSSH(cls, data):
        """
        Return a public key object corresponding to this OpenSSH public key
        string.  The format of an OpenSSH public key string is::
            <key type> <base64-encoded public key blob>

        @type data: L{bytes}
        @param data: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the blob type is unknown.
        """
        # ECDSA keys don't need base64 decoding which is required
        # for RSA or DSA key.
        if data.startswith(b"ecdsa-sha2"):
            return cls(load_ssh_public_key(data, default_backend()))
        blob = decodebytes(data.split()[1])
        return cls._fromString_BLOB(blob)

    @classmethod
    def _fromPrivateOpenSSH_v1(cls, data, passphrase):
        """
        Return a private key object corresponding to this OpenSSH private key
        string, in the "openssh-key-v1" format introduced in OpenSSH 6.5.

        The format of an openssh-key-v1 private key string is::
            -----BEGIN OPENSSH PRIVATE KEY-----
            <base64-encoded SSH protocol string>
            -----END OPENSSH PRIVATE KEY-----

        The SSH protocol string is as described in
        U{PROTOCOL.key<https://cvsweb.openbsd.org/cgi-bin/cvsweb/src/usr.bin/ssh/PROTOCOL.key>}.

        @type data: L{bytes}
        @param data: The key data.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase the key is encrypted with, or L{None}
        if it is not encrypted.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if
            * a passphrase is provided for an unencrypted key
            * the SSH protocol encoding is incorrect
        @raises EncryptedKeyError: if
            * a passphrase is not provided for an encrypted key
        """
        lines = data.strip().splitlines()
        keyList = decodebytes(b"".join(lines[1:-1]))
        if not keyList.startswith(b"openssh-key-v1\0"):
            raise BadKeyError("unknown OpenSSH private key format")
        keyList = keyList[len(b"openssh-key-v1\0") :]
        cipher, kdf, kdfOptions, rest = common.getNS(keyList, 3)
        n = struct.unpack("!L", rest[:4])[0]
        if n != 1:
            raise BadKeyError(
                "only OpenSSH private key files containing "
                "a single key are supported"
            )
        # Ignore public key
        _, encPrivKeyList, _ = common.getNS(rest[4:], 2)
        if cipher != b"none":
            if not passphrase:
                raise EncryptedKeyError(
                    "Passphrase must be provided " "for an encrypted key"
                )
            # Determine cipher
            if cipher in (b"aes128-ctr", b"aes192-ctr", b"aes256-ctr"):
                algorithmClass = algorithms.AES
                blockSize = 16
                keySize = int(cipher[3:6]) // 8
                ivSize = blockSize
            else:
                raise BadKeyError(f"unknown encryption type {cipher!r}")
            if kdf == b"bcrypt":
                salt, rest = common.getNS(kdfOptions)
                rounds = struct.unpack("!L", rest[:4])[0]
                decKey = bcrypt.kdf(
                    passphrase,
                    salt,
                    keySize + ivSize,
                    rounds,
                    # We can only use the number of rounds that OpenSSH used.
                    ignore_few_rounds=True,
                )
            else:
                raise BadKeyError(f"unknown KDF type {kdf!r}")
            if (len(encPrivKeyList) % blockSize) != 0:
                raise BadKeyError("bad padding")
            decryptor = Cipher(
                algorithmClass(decKey[:keySize]),
                modes.CTR(decKey[keySize : keySize + ivSize]),
                backend=default_backend(),
            ).decryptor()
            privKeyList = decryptor.update(encPrivKeyList) + decryptor.finalize()
        else:
            if kdf != b"none":
                raise BadKeyError(
                    "private key specifies KDF %r but no " "cipher" % (kdf,)
                )
            privKeyList = encPrivKeyList
        check1 = struct.unpack("!L", privKeyList[:4])[0]
        check2 = struct.unpack("!L", privKeyList[4:8])[0]
        if check1 != check2:
            raise BadKeyError("check values do not match: %d != %d" % (check1, check2))
        return cls._fromString_PRIVATE_BLOB(privKeyList[8:])

    @classmethod
    def _fromPrivateOpenSSH_PEM(cls, data, passphrase):
        """
        Return a private key object corresponding to this OpenSSH private key
        string, in the old PEM-based format.

        The format of a PEM-based OpenSSH private key string is::
            -----BEGIN <key type> PRIVATE KEY-----
            [Proc-Type: 4,ENCRYPTED
            DEK-Info: DES-EDE3-CBC,<initialization value>]
            <base64-encoded ASN.1 structure>
            ------END <key type> PRIVATE KEY------

        The ASN.1 structure of a RSA key is::
            (0, n, e, d, p, q)

        The ASN.1 structure of a DSA key is::
            (0, p, q, g, y, x)

        The ASN.1 structure of a ECDSA key is::
            (ECParameters, OID, NULL)

        @type data: L{bytes}
        @param data: The key data.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase the key is encrypted with, or L{None}
        if it is not encrypted.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if
            * a passphrase is provided for an unencrypted key
            * the ASN.1 encoding is incorrect
        @raises EncryptedKeyError: if
            * a passphrase is not provided for an encrypted key
        """
        lines = data.strip().splitlines()
        kind = lines[0][11:-17]
        if lines[1].startswith(b"Proc-Type: 4,ENCRYPTED"):
            if not passphrase:
                raise EncryptedKeyError(
                    "Passphrase must be provided " "for an encrypted key"
                )

            # Determine cipher and initialization vector
            try:
                _, cipherIVInfo = lines[2].split(b" ", 1)
                cipher, ivdata = cipherIVInfo.rstrip().split(b",", 1)
            except ValueError:
                raise BadKeyError(f"invalid DEK-info {lines[2]!r}")

            if cipher in (b"AES-128-CBC", b"AES-256-CBC"):
                algorithmClass = algorithms.AES
                keySize = int(cipher.split(b"-")[1]) // 8
                if len(ivdata) != 32:
                    raise BadKeyError("AES encrypted key with a bad IV")
            elif cipher == b"DES-EDE3-CBC":
                algorithmClass = algorithms.TripleDES
                keySize = 24
                if len(ivdata) != 16:
                    raise BadKeyError("DES encrypted key with a bad IV")
            else:
                raise BadKeyError(f"unknown encryption type {cipher!r}")

            # Extract keyData for decoding
            iv = bytes(
                bytearray(int(ivdata[i : i + 2], 16) for i in range(0, len(ivdata), 2))
            )
            ba = md5(passphrase + iv[:8]).digest()
            bb = md5(ba + passphrase + iv[:8]).digest()
            decKey = (ba + bb)[:keySize]
            b64Data = decodebytes(b"".join(lines[3:-1]))

            decryptor = Cipher(
                algorithmClass(decKey), modes.CBC(iv), backend=default_backend()
            ).decryptor()
            keyData = decryptor.update(b64Data) + decryptor.finalize()

            removeLen = ord(keyData[-1:])
            keyData = keyData[:-removeLen]
        else:
            b64Data = b"".join(lines[1:-1])
            keyData = decodebytes(b64Data)

        try:
            decodedKey = berDecoder.decode(keyData)[0]
        except PyAsn1Error as asn1Error:
            raise BadKeyError(f"Failed to decode key (Bad Passphrase?): {asn1Error}")

        if kind == b"EC":
            return cls(load_pem_private_key(data, passphrase, default_backend()))

        if kind == b"RSA":
            if len(decodedKey) == 2:  # Alternate RSA key
                decodedKey = decodedKey[0]
            if len(decodedKey) < 6:
                raise BadKeyError("RSA key failed to decode properly")

            n, e, d, p, q, dmp1, dmq1, iqmp = (int(value) for value in decodedKey[1:9])
            return cls(
                rsa.RSAPrivateNumbers(
                    p=p,
                    q=q,
                    d=d,
                    dmp1=dmp1,
                    dmq1=dmq1,
                    iqmp=iqmp,
                    public_numbers=rsa.RSAPublicNumbers(e=e, n=n),
                ).private_key(default_backend())
            )
        elif kind == b"DSA":
            p, q, g, y, x = (int(value) for value in decodedKey[1:6])
            if len(decodedKey) < 6:
                raise BadKeyError("DSA key failed to decode properly")
            return cls(
                dsa.DSAPrivateNumbers(
                    x=x,
                    public_numbers=dsa.DSAPublicNumbers(
                        y=y, parameter_numbers=dsa.DSAParameterNumbers(p=p, q=q, g=g)
                    ),
                ).private_key(backend=default_backend())
            )
        else:
            raise BadKeyError(f"unknown key type {kind}")

    @classmethod
    def _fromString_PRIVATE_OPENSSH(cls, data, passphrase):
        """
        Return a private key object corresponding to this OpenSSH private key
        string.  If the key is encrypted, passphrase MUST be provided.
        Providing a passphrase for an unencrypted key is an error.

        @type data: L{bytes}
        @param data: The key data.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase the key is encrypted with, or L{None}
        if it is not encrypted.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if
            * a passphrase is provided for an unencrypted key
            * the encoding is incorrect
        @raises EncryptedKeyError: if
            * a passphrase is not provided for an encrypted key
        """
        if data.strip().splitlines()[0][11:-17] == b"OPENSSH":
            # New-format (openssh-key-v1) key
            return cls._fromPrivateOpenSSH_v1(data, passphrase)
        else:
            # Old-format (PEM) key
            return cls._fromPrivateOpenSSH_PEM(data, passphrase)

    @classmethod
    def _fromString_PUBLIC_LSH(cls, data):
        """
        Return a public key corresponding to this LSH public key string.
        The LSH public key string format is::
            <s-expression: ('public-key', (<key type>, (<name, <value>)+))>

        The names for a RSA (key type 'rsa-pkcs1-sha1') key are: n, e.
        The names for a DSA (key type 'dsa') key are: y, g, p, q.

        @type data: L{bytes}
        @param data: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type is unknown
        """
        sexp = sexpy.parse(decodebytes(data[1:-1]))
        assert sexp[0] == b"public-key"
        kd = {}
        for name, data in sexp[1][1:]:
            kd[name] = common.getMP(common.NS(data))[0]
        if sexp[1][0] == b"dsa":
            return cls._fromDSAComponents(
                y=kd[b"y"], g=kd[b"g"], p=kd[b"p"], q=kd[b"q"]
            )

        elif sexp[1][0] == b"rsa-pkcs1-sha1":
            return cls._fromRSAComponents(n=kd[b"n"], e=kd[b"e"])
        else:
            raise BadKeyError(f"unknown lsh key type {sexp[1][0]}")

    @classmethod
    def _fromString_PRIVATE_LSH(cls, data):
        """
        Return a private key corresponding to this LSH private key string.
        The LSH private key string format is::
            <s-expression: ('private-key', (<key type>, (<name>, <value>)+))>

        The names for a RSA (key type 'rsa-pkcs1-sha1') key are: n, e, d, p, q.
        The names for a DSA (key type 'dsa') key are: y, g, p, q, x.

        @type data: L{bytes}
        @param data: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type is unknown
        """
        sexp = sexpy.parse(data)
        assert sexp[0] == b"private-key"
        kd = {}
        for name, data in sexp[1][1:]:
            kd[name] = common.getMP(common.NS(data))[0]
        if sexp[1][0] == b"dsa":
            assert len(kd) == 5, len(kd)
            return cls._fromDSAComponents(
                y=kd[b"y"], g=kd[b"g"], p=kd[b"p"], q=kd[b"q"], x=kd[b"x"]
            )
        elif sexp[1][0] == b"rsa-pkcs1":
            assert len(kd) == 8, len(kd)
            if kd[b"p"] > kd[b"q"]:  # Make p smaller than q
                kd[b"p"], kd[b"q"] = kd[b"q"], kd[b"p"]
            return cls._fromRSAComponents(
                n=kd[b"n"], e=kd[b"e"], d=kd[b"d"], p=kd[b"p"], q=kd[b"q"]
            )

        else:
            raise BadKeyError(f"unknown lsh key type {sexp[1][0]}")

    @classmethod
    def _fromString_AGENTV3(cls, data):
        """
        Return a private key object corresponsing to the Secure Shell Key
        Agent v3 format.

        The SSH Key Agent v3 format for a RSA key is::
            string 'ssh-rsa'
            integer e
            integer d
            integer n
            integer u
            integer p
            integer q

        The SSH Key Agent v3 format for a DSA key is::
            string 'ssh-dss'
            integer p
            integer q
            integer g
            integer y
            integer x

        @type data: L{bytes}
        @param data: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type (the first string) is unknown
        """
        keyType, data = common.getNS(data)
        if keyType == b"ssh-dss":
            p, data = common.getMP(data)
            q, data = common.getMP(data)
            g, data = common.getMP(data)
            y, data = common.getMP(data)
            x, data = common.getMP(data)
            return cls._fromDSAComponents(y=y, g=g, p=p, q=q, x=x)
        elif keyType == b"ssh-rsa":
            e, data = common.getMP(data)
            d, data = common.getMP(data)
            n, data = common.getMP(data)
            u, data = common.getMP(data)
            p, data = common.getMP(data)
            q, data = common.getMP(data)
            return cls._fromRSAComponents(n=n, e=e, d=d, p=p, q=q, u=u)
        else:
            raise BadKeyError(f"unknown key type {keyType}")

    @classmethod
    def _guessStringType(cls, data):
        """
        Guess the type of key in data.  The types map to _fromString_*
        methods.

        @type data: L{bytes}
        @param data: The key data.
        """
        if data.startswith(b"ssh-") or data.startswith(b"ecdsa-sha2-"):
            return "public_openssh"
        elif data.startswith(b"-----BEGIN"):
            return "private_openssh"
        elif data.startswith(b"{"):
            return "public_lsh"
        elif data.startswith(b"("):
            return "private_lsh"
        elif (
            data.startswith(b"\x00\x00\x00\x07ssh-")
            or data.startswith(b"\x00\x00\x00\x13ecdsa-")
            or data.startswith(b"\x00\x00\x00\x0bssh-ed25519")
        ):
            ignored, rest = common.getNS(data)
            count = 0
            while rest:
                count += 1
                ignored, rest = common.getMP(rest)
            if count > 4:
                return "agentv3"
            else:
                return "blob"

    @classmethod
    def _fromRSAComponents(cls, n, e, d=None, p=None, q=None, u=None):
        """
        Build a key from RSA numerical components.

        @type n: L{int}
        @param n: The 'n' RSA variable.

        @type e: L{int}
        @param e: The 'e' RSA variable.

        @type d: L{int} or L{None}
        @param d: The 'd' RSA variable (optional for a public key).

        @type p: L{int} or L{None}
        @param p: The 'p' RSA variable (optional for a public key).

        @type q: L{int} or L{None}
        @param q: The 'q' RSA variable (optional for a public key).

        @type u: L{int} or L{None}
        @param u: The 'u' RSA variable. Ignored, as its value is determined by
        p and q.

        @rtype: L{Key}
        @return: An RSA key constructed from the values as given.
        """
        publicNumbers = rsa.RSAPublicNumbers(e=e, n=n)
        if d is None:
            # We have public components.
            keyObject = publicNumbers.public_key(default_backend())
        else:
            privateNumbers = rsa.RSAPrivateNumbers(
                p=p,
                q=q,
                d=d,
                dmp1=rsa.rsa_crt_dmp1(d, p),
                dmq1=rsa.rsa_crt_dmq1(d, q),
                iqmp=rsa.rsa_crt_iqmp(p, q),
                public_numbers=publicNumbers,
            )
            keyObject = privateNumbers.private_key(default_backend())

        return cls(keyObject)

    @classmethod
    def _fromDSAComponents(cls, y, p, q, g, x=None):
        """
        Build a key from DSA numerical components.

        @type y: L{int}
        @param y: The 'y' DSA variable.

        @type p: L{int}
        @param p: The 'p' DSA variable.

        @type q: L{int}
        @param q: The 'q' DSA variable.

        @type g: L{int}
        @param g: The 'g' DSA variable.

        @type x: L{int} or L{None}
        @param x: The 'x' DSA variable (optional for a public key)

        @rtype: L{Key}
        @return: A DSA key constructed from the values as given.
        """
        publicNumbers = dsa.DSAPublicNumbers(
            y=y, parameter_numbers=dsa.DSAParameterNumbers(p=p, q=q, g=g)
        )
        if x is None:
            # We have public components.
            keyObject = publicNumbers.public_key(default_backend())
        else:
            privateNumbers = dsa.DSAPrivateNumbers(x=x, public_numbers=publicNumbers)
            keyObject = privateNumbers.private_key(default_backend())

        return cls(keyObject)

    @classmethod
    def _fromECComponents(cls, x, y, curve, privateValue=None):
        """
        Build a key from EC components.

        @param x: The affine x component of the public point used for verifying.
        @type x: L{int}

        @param y: The affine y component of the public point used for verifying.
        @type y: L{int}

        @param curve: NIST name of elliptic curve.
        @type curve: L{bytes}

        @param privateValue: The private value.
        @type privateValue: L{int}
        """

        publicNumbers = ec.EllipticCurvePublicNumbers(
            x=x, y=y, curve=_curveTable[curve]
        )
        if privateValue is None:
            # We have public components.
            keyObject = publicNumbers.public_key(default_backend())
        else:
            privateNumbers = ec.EllipticCurvePrivateNumbers(
                private_value=privateValue, public_numbers=publicNumbers
            )
            keyObject = privateNumbers.private_key(default_backend())

        return cls(keyObject)

    @classmethod
    def _fromECEncodedPoint(cls, encodedPoint, curve, privateValue=None):
        """
        Build a key from an EC encoded point.

        @param encodedPoint: The public point encoded as in SEC 1 v2.0
        section 2.3.3.
        @type encodedPoint: L{bytes}

        @param curve: NIST name of elliptic curve.
        @type curve: L{bytes}

        @param privateValue: The private value.
        @type privateValue: L{int}
        """

        if privateValue is None:
            # We have public components.
            keyObject = ec.EllipticCurvePublicKey.from_encoded_point(
                _curveTable[curve], encodedPoint
            )
        else:
            keyObject = ec.derive_private_key(
                privateValue, _curveTable[curve], default_backend()
            )

        return cls(keyObject)

    @classmethod
    def _fromEd25519Components(cls, a, k=None):
        """Build a key from Ed25519 components.

        @param a: The Ed25519 public key, as defined in RFC 8032 section
            5.1.5.
        @type a: L{bytes}

        @param k: The Ed25519 private key, as defined in RFC 8032 section
            5.1.5.
        @type k: L{bytes}
        """

        if Ed25519PublicKey is None or Ed25519PrivateKey is None:
            raise BadKeyError("Ed25519 keys not supported on this system")

        if k is None:
            keyObject = Ed25519PublicKey.from_public_bytes(a)
        else:
            keyObject = Ed25519PrivateKey.from_private_bytes(k)

        return cls(keyObject)

    def __init__(self, keyObject):
        """
        Initialize with a private or public
        C{cryptography.hazmat.primitives.asymmetric} key.

        @param keyObject: Low level key.
        @type keyObject: C{cryptography.hazmat.primitives.asymmetric} key.
        """
        self._keyObject = keyObject

    def __eq__(self, other: object) -> bool:
        """
        Return True if other represents an object with the same key.
        """
        if isinstance(other, Key):
            return self.type() == other.type() and self.data() == other.data()
        else:
            return NotImplemented

    def __repr__(self) -> str:
        """
        Return a pretty representation of this object.
        """
        if self.type() == "EC":
            data = self.data()
            name = data["curve"].decode("utf-8")

            if self.isPublic():
                out = f"<Elliptic Curve Public Key ({name[-3:]} bits)"
            else:
                out = f"<Elliptic Curve Private Key ({name[-3:]} bits)"

            for k, v in sorted(data.items()):
                if k == "curve":
                    out += f"\ncurve:\n\t{name}"
                else:
                    out += f"\n{k}:\n\t{v}"

            return out + ">\n"
        else:
            lines = [
                "<%s %s (%s bits)"
                % (
                    nativeString(self.type()),
                    self.isPublic() and "Public Key" or "Private Key",
                    self.size(),
                )
            ]
            for k, v in sorted(self.data().items()):
                lines.append(f"attr {k}:")
                by = v if self.type() == "Ed25519" else common.MP(v)[4:]
                while by:
                    m = by[:15]
                    by = by[15:]
                    o = ""
                    for c in iterbytes(m):
                        o = o + f"{ord(c):02x}:"
                    if len(m) < 15:
                        o = o[:-1]
                    lines.append("\t" + o)
            lines[-1] = lines[-1] + ">"
            return "\n".join(lines)

    def isPublic(self):
        """
        Check if this instance is a public key.

        @return: C{True} if this is a public key.
        """
        return isinstance(
            self._keyObject,
            (
                rsa.RSAPublicKey,
                dsa.DSAPublicKey,
                ec.EllipticCurvePublicKey,
                ed25519.Ed25519PublicKey,
            ),
        )

    def public(self):
        """
        Returns a version of this key containing only the public key data.
        If this is a public key, this may or may not be the same object
        as self.

        @rtype: L{Key}
        @return: A public key.
        """
        if self.isPublic():
            return self
        else:
            return Key(self._keyObject.public_key())

    def fingerprint(self, format=FingerprintFormats.MD5_HEX):
        """
        The fingerprint of a public key consists of the output of the
        message-digest algorithm in the specified format.
        Supported formats include L{FingerprintFormats.MD5_HEX} and
        L{FingerprintFormats.SHA256_BASE64}

        The input to the algorithm is the public key data as specified by [RFC4253].

        The output of sha256[RFC4634] algorithm is presented to the
        user in the form of base64 encoded sha256 hashes.
        Example: C{US5jTUa0kgX5ZxdqaGF0yGRu8EgKXHNmoT8jHKo1StM=}

        The output of the MD5[RFC1321](default) algorithm is presented to the user as
        a sequence of 16 octets printed as hexadecimal with lowercase letters
        and separated by colons.
        Example: C{c1:b1:30:29:d7:b8:de:6c:97:77:10:d7:46:41:63:87}

        @param format: Format for fingerprint generation. Consists
            hash function and representation format.
            Default is L{FingerprintFormats.MD5_HEX}

        @since: 8.2

        @return: the user presentation of this L{Key}'s fingerprint, as a
        string.

        @rtype: L{str}
        """
        if format is FingerprintFormats.SHA256_BASE64:
            return nativeString(b64encode(sha256(self.blob()).digest()))
        elif format is FingerprintFormats.MD5_HEX:
            return nativeString(
                b":".join(
                    [binascii.hexlify(x) for x in iterbytes(md5(self.blob()).digest())]
                )
            )
        else:
            raise BadFingerPrintFormat(f"Unsupported fingerprint format: {format}")

    def type(self):
        """
        Return the type of the object we wrap.  Currently this can only be
        'RSA', 'DSA', 'EC', or 'Ed25519'.

        @rtype: L{str}
        @raises RuntimeError: If the object type is unknown.
        """
        if isinstance(self._keyObject, (rsa.RSAPublicKey, rsa.RSAPrivateKey)):
            return "RSA"
        elif isinstance(self._keyObject, (dsa.DSAPublicKey, dsa.DSAPrivateKey)):
            return "DSA"
        elif isinstance(
            self._keyObject, (ec.EllipticCurvePublicKey, ec.EllipticCurvePrivateKey)
        ):
            return "EC"
        elif isinstance(
            self._keyObject, (ed25519.Ed25519PublicKey, ed25519.Ed25519PrivateKey)
        ):
            return "Ed25519"
        else:
            raise RuntimeError(f"unknown type of object: {self._keyObject!r}")

    def sshType(self):
        """
        Get the type of the object we wrap as defined in the SSH protocol,
        defined in RFC 4253, Section 6.6 and RFC 8332, section 4 (this is a
        public key format name, not a public key algorithm name). Currently
        this can only be b'ssh-rsa', b'ssh-dss', b'ecdsa-sha2-[identifier]'
        or b'ssh-ed25519'.

        identifier is the standard NIST curve name

        @return: The key type format.
        @rtype: L{bytes}
        """
        if self.type() == "EC":
            return (
                b"ecdsa-sha2-" + _secToNist[self._keyObject.curve.name.encode("ascii")]
            )
        else:
            return {
                "RSA": b"ssh-rsa",
                "DSA": b"ssh-dss",
                "Ed25519": b"ssh-ed25519",
            }[self.type()]

    def supportedSignatureAlgorithms(self):
        """
        Get the public key signature algorithms supported by this key.

        @return: A list of supported public key signature algorithm names.
        @rtype: L{list} of L{bytes}
        """
        if self.type() == "RSA":
            return [b"rsa-sha2-512", b"rsa-sha2-256", b"ssh-rsa"]
        else:
            return [self.sshType()]

    def _getHashAlgorithm(self, signatureType):
        """
        Return a hash algorithm for this key type given an SSH signature
        algorithm name, or L{None} if no such hash algorithm is defined for
        this key type.
        """
        if self.type() == "EC":
            # Hash algorithm depends on key size
            if signatureType == self.sshType():
                keySize = self.size()
                if keySize <= 256:
                    return hashes.SHA256()
                elif keySize <= 384:
                    return hashes.SHA384()
                else:
                    return hashes.SHA512()
            else:
                return None
        else:
            return {
                ("RSA", b"ssh-rsa"): hashes.SHA1(),
                ("RSA", b"rsa-sha2-256"): hashes.SHA256(),
                ("RSA", b"rsa-sha2-512"): hashes.SHA512(),
                ("DSA", b"ssh-dss"): hashes.SHA1(),
                ("Ed25519", b"ssh-ed25519"): hashes.SHA512(),
            }.get((self.type(), signatureType))

    def size(self):
        """
        Return the size of the object we wrap.

        @return: The size of the key.
        @rtype: L{int}
        """
        if self._keyObject is None:
            return 0
        elif self.type() == "EC":
            return self._keyObject.curve.key_size
        elif self.type() == "Ed25519":
            return 256
        return self._keyObject.key_size

    def data(self):
        """
        Return the values of the public key as a dictionary.

        @rtype: L{dict}
        """
        if isinstance(self._keyObject, rsa.RSAPublicKey):
            numbers = self._keyObject.public_numbers()
            return {
                "n": numbers.n,
                "e": numbers.e,
            }
        elif isinstance(self._keyObject, rsa.RSAPrivateKey):
            numbers = self._keyObject.private_numbers()
            return {
                "n": numbers.public_numbers.n,
                "e": numbers.public_numbers.e,
                "d": numbers.d,
                "p": numbers.p,
                "q": numbers.q,
                # Use a trick: iqmp is q^-1 % p, u is p^-1 % q
                "u": rsa.rsa_crt_iqmp(numbers.q, numbers.p),
            }
        elif isinstance(self._keyObject, dsa.DSAPublicKey):
            numbers = self._keyObject.public_numbers()
            return {
                "y": numbers.y,
                "g": numbers.parameter_numbers.g,
                "p": numbers.parameter_numbers.p,
                "q": numbers.parameter_numbers.q,
            }
        elif isinstance(self._keyObject, dsa.DSAPrivateKey):
            numbers = self._keyObject.private_numbers()
            return {
                "x": numbers.x,
                "y": numbers.public_numbers.y,
                "g": numbers.public_numbers.parameter_numbers.g,
                "p": numbers.public_numbers.parameter_numbers.p,
                "q": numbers.public_numbers.parameter_numbers.q,
            }
        elif isinstance(self._keyObject, ec.EllipticCurvePublicKey):
            numbers = self._keyObject.public_numbers()
            return {
                "x": numbers.x,
                "y": numbers.y,
                "curve": self.sshType(),
            }
        elif isinstance(self._keyObject, ec.EllipticCurvePrivateKey):
            numbers = self._keyObject.private_numbers()
            return {
                "x": numbers.public_numbers.x,
                "y": numbers.public_numbers.y,
                "privateValue": numbers.private_value,
                "curve": self.sshType(),
            }
        elif isinstance(self._keyObject, ed25519.Ed25519PublicKey):
            return {
                "a": self._keyObject.public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                ),
            }
        elif isinstance(self._keyObject, ed25519.Ed25519PrivateKey):
            return {
                "a": self._keyObject.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                ),
                "k": self._keyObject.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                ),
            }

        else:
            raise RuntimeError(f"Unexpected key type: {self._keyObject}")

    def blob(self):
        """
        Return the public key blob for this key. The blob is the
        over-the-wire format for public keys.

        SECSH-TRANS RFC 4253 Section 6.6.

        RSA keys::
            string 'ssh-rsa'
            integer e
            integer n

        DSA keys::
            string 'ssh-dss'
            integer p
            integer q
            integer g
            integer y

        EC keys::
            string 'ecdsa-sha2-[identifier]'
            integer x
            integer y

            identifier is the standard NIST curve name

        Ed25519 keys::
            string 'ssh-ed25519'
            string a

        @rtype: L{bytes}
        """
        type = self.type()
        data = self.data()
        if type == "RSA":
            return common.NS(b"ssh-rsa") + common.MP(data["e"]) + common.MP(data["n"])
        elif type == "DSA":
            return (
                common.NS(b"ssh-dss")
                + common.MP(data["p"])
                + common.MP(data["q"])
                + common.MP(data["g"])
                + common.MP(data["y"])
            )
        elif type == "EC":
            byteLength = (self._keyObject.curve.key_size + 7) // 8
            return (
                common.NS(data["curve"])
                + common.NS(data["curve"][-8:])
                + common.NS(
                    b"\x04"
                    + utils.int_to_bytes(data["x"], byteLength)
                    + utils.int_to_bytes(data["y"], byteLength)
                )
            )
        elif type == "Ed25519":
            return common.NS(b"ssh-ed25519") + common.NS(data["a"])
        else:
            raise BadKeyError(f"unknown key type: {type}")

    def privateBlob(self):
        """
        Return the private key blob for this key. The blob is the
        over-the-wire format for private keys:

        Specification in OpenSSH PROTOCOL.agent

        RSA keys::

            string 'ssh-rsa'
            integer n
            integer e
            integer d
            integer u
            integer p
            integer q

        DSA keys::

            string 'ssh-dss'
            integer p
            integer q
            integer g
            integer y
            integer x

        EC keys::

            string 'ecdsa-sha2-[identifier]'
            integer x
            integer y
            integer privateValue

            identifier is the NIST standard curve name.

        Ed25519 keys::

            string 'ssh-ed25519'
            string a
            string k || a
        """
        type = self.type()
        data = self.data()
        if type == "RSA":
            iqmp = rsa.rsa_crt_iqmp(data["p"], data["q"])
            return (
                common.NS(b"ssh-rsa")
                + common.MP(data["n"])
                + common.MP(data["e"])
                + common.MP(data["d"])
                + common.MP(iqmp)
                + common.MP(data["p"])
                + common.MP(data["q"])
            )
        elif type == "DSA":
            return (
                common.NS(b"ssh-dss")
                + common.MP(data["p"])
                + common.MP(data["q"])
                + common.MP(data["g"])
                + common.MP(data["y"])
                + common.MP(data["x"])
            )
        elif type == "EC":
            encPub = self._keyObject.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
            return (
                common.NS(data["curve"])
                + common.NS(data["curve"][-8:])
                + common.NS(encPub)
                + common.MP(data["privateValue"])
            )
        elif type == "Ed25519":
            return (
                common.NS(b"ssh-ed25519")
                + common.NS(data["a"])
                + common.NS(data["k"] + data["a"])
            )
        else:
            raise BadKeyError(f"unknown key type: {type}")

    @_mutuallyExclusiveArguments(
        [
            ["extra", "comment"],
            ["extra", "passphrase"],
        ]
    )
    def toString(self, type, extra=None, subtype=None, comment=None, passphrase=None):
        """
        Create a string representation of this key.  If the key is a private
        key and you want the representation of its public key, use
        C{key.public().toString()}.  type maps to a _toString_* method.

        @param type: The type of string to emit.  Currently supported values
            are C{'OPENSSH'}, C{'LSH'}, and C{'AGENTV3'}.
        @type type: L{str}

        @param extra: Any extra data supported by the selected format which
            is not part of the key itself.  For public OpenSSH keys, this is
            a comment.  For private OpenSSH keys, this is a passphrase to
            encrypt with.  (Deprecated since Twisted 20.3.0; use C{comment}
            or C{passphrase} as appropriate instead.)
        @type extra: L{bytes} or L{unicode} or L{None}

        @param subtype: A subtype of the requested C{type} to emit.  Only
            supported for private OpenSSH keys, for which the currently
            supported subtypes are C{'PEM'} and C{'v1'}.  If not given, an
            appropriate default is used.
        @type subtype: L{str} or L{None}

        @param comment: A comment to include with the key.  Only supported
            for OpenSSH keys.

            Present since Twisted 20.3.0.

        @type comment: L{bytes} or L{unicode} or L{None}

        @param passphrase: A passphrase to encrypt the key with.  Only
            supported for private OpenSSH keys.

            Present since Twisted 20.3.0.

        @type passphrase: L{bytes} or L{unicode} or L{None}

        @rtype: L{bytes}
        """
        if extra is not None:
            # Compatibility with old parameter format.
            warnings.warn(
                "The 'extra' argument to "
                "twisted.conch.ssh.keys.Key.toString was deprecated in "
                "Twisted 20.3.0; use 'comment' or 'passphrase' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            if self.isPublic():
                comment = extra
            else:
                passphrase = extra
        if isinstance(comment, str):
            comment = comment.encode("utf-8")
        passphrase = _normalizePassphrase(passphrase)
        method = getattr(self, f"_toString_{type.upper()}", None)
        if method is None:
            raise BadKeyError(f"unknown key type: {type}")
        return method(subtype=subtype, comment=comment, passphrase=passphrase)

    def _toPublicOpenSSH(self, comment=None):
        """
        Return a public OpenSSH key string.

        See _fromString_PUBLIC_OPENSSH for the string format.

        @type comment: L{bytes} or L{None}
        @param comment: A comment to include with the key, or L{None} to
        omit the comment.
        """
        if self.type() == "EC":
            if not comment:
                comment = b""
            return (
                self._keyObject.public_bytes(
                    serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
                )
                + b" "
                + comment
            ).strip()

        b64Data = encodebytes(self.blob()).replace(b"\n", b"")
        if not comment:
            comment = b""
        return (self.sshType() + b" " + b64Data + b" " + comment).strip()

    def _toPrivateOpenSSH_v1(self, comment=None, passphrase=None):
        """
        Return a private OpenSSH key string, in the "openssh-key-v1" format
        introduced in OpenSSH 6.5.

        See _fromPrivateOpenSSH_v1 for the string format.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase to encrypt the key with, or L{None}
        if it is not encrypted.
        """
        if passphrase:
            # For now we just hardcode the cipher to the one used by
            # OpenSSH.  We could make this configurable later if it's
            # needed.
            cipher = algorithms.AES
            cipherName = b"aes256-ctr"
            kdfName = b"bcrypt"
            blockSize = cipher.block_size // 8
            keySize = 32
            ivSize = blockSize
            salt = randbytes.secureRandom(ivSize)
            rounds = 100
            kdfOptions = common.NS(salt) + struct.pack("!L", rounds)
        else:
            cipherName = b"none"
            kdfName = b"none"
            blockSize = 8
            kdfOptions = b""
        check = randbytes.secureRandom(4)
        privKeyList = check + check + self.privateBlob() + common.NS(comment or b"")
        padByte = 0
        while len(privKeyList) % blockSize:
            padByte += 1
            privKeyList += bytes((padByte & 0xFF,))
        if passphrase:
            encKey = bcrypt.kdf(passphrase, salt, keySize + ivSize, 100)
            encryptor = Cipher(
                cipher(encKey[:keySize]),
                modes.CTR(encKey[keySize : keySize + ivSize]),
                backend=default_backend(),
            ).encryptor()
            encPrivKeyList = encryptor.update(privKeyList) + encryptor.finalize()
        else:
            encPrivKeyList = privKeyList
        blob = (
            b"openssh-key-v1\0"
            + common.NS(cipherName)
            + common.NS(kdfName)
            + common.NS(kdfOptions)
            + struct.pack("!L", 1)
            + common.NS(self.blob())
            + common.NS(encPrivKeyList)
        )
        b64Data = encodebytes(blob).replace(b"\n", b"")
        lines = (
            [b"-----BEGIN OPENSSH PRIVATE KEY-----"]
            + [b64Data[i : i + 64] for i in range(0, len(b64Data), 64)]
            + [b"-----END OPENSSH PRIVATE KEY-----"]
        )
        return b"\n".join(lines) + b"\n"

    def _toPrivateOpenSSH_PEM(self, passphrase=None):
        """
        Return a private OpenSSH key string, in the old PEM-based format.

        See _fromPrivateOpenSSH_PEM for the string format.

        @type passphrase: L{bytes} or L{None}
        @param passphrase: The passphrase to encrypt the key with, or L{None}
        if it is not encrypted.
        """
        if self.type() == "EC":
            # EC keys has complex ASN.1 structure hence we do this this way.
            if not passphrase:
                # unencrypted private key
                encryptor = serialization.NoEncryption()
            else:
                encryptor = serialization.BestAvailableEncryption(passphrase)

            return self._keyObject.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                encryptor,
            )
        elif self.type() == "Ed25519":
            raise ValueError(
                "cannot serialize Ed25519 key to OpenSSH PEM format; use v1 " "instead"
            )

        data = self.data()
        lines = [
            b"".join(
                (b"-----BEGIN ", self.type().encode("ascii"), b" PRIVATE KEY-----")
            )
        ]
        if self.type() == "RSA":
            p, q = data["p"], data["q"]
            iqmp = rsa.rsa_crt_iqmp(p, q)
            objData = (
                0,
                data["n"],
                data["e"],
                data["d"],
                p,
                q,
                data["d"] % (p - 1),
                data["d"] % (q - 1),
                iqmp,
            )
        else:
            objData = (0, data["p"], data["q"], data["g"], data["y"], data["x"])
        asn1Sequence = univ.Sequence()
        for index, value in zip(itertools.count(), objData):
            asn1Sequence.setComponentByPosition(index, univ.Integer(value))
        asn1Data = berEncoder.encode(asn1Sequence)
        if passphrase:
            iv = randbytes.secureRandom(8)
            hexiv = "".join([f"{ord(x):02X}" for x in iterbytes(iv)])
            hexiv = hexiv.encode("ascii")
            lines.append(b"Proc-Type: 4,ENCRYPTED")
            lines.append(b"DEK-Info: DES-EDE3-CBC," + hexiv + b"\n")
            ba = md5(passphrase + iv).digest()
            bb = md5(ba + passphrase + iv).digest()
            encKey = (ba + bb)[:24]
            padLen = 8 - (len(asn1Data) % 8)
            asn1Data += bytes((padLen,)) * padLen

            encryptor = Cipher(
                algorithms.TripleDES(encKey), modes.CBC(iv), backend=default_backend()
            ).encryptor()

            asn1Data = encryptor.update(asn1Data) + encryptor.finalize()

        b64Data = encodebytes(asn1Data).replace(b"\n", b"")
        lines += [b64Data[i : i + 64] for i in range(0, len(b64Data), 64)]
        lines.append(
            b"".join((b"-----END ", self.type().encode("ascii"), b" PRIVATE KEY-----"))
        )
        return b"\n".join(lines)

    def _toString_OPENSSH(self, subtype=None, comment=None, passphrase=None):
        """
        Return a public or private OpenSSH string.  See
        L{_fromString_PUBLIC_OPENSSH} and L{_fromPrivateOpenSSH_PEM} for the
        string formats.

        @param subtype: A subtype to emit.  Only supported for private keys,
            for which the currently supported subtypes are C{'PEM'} and C{'v1'}.
            If not given, an appropriate default is used.
        @type subtype: L{str} or L{None}

        @param comment: Comment for a public key.
        @type comment: L{bytes}

        @param passphrase: Passphrase for a private key.
        @type passphrase: L{bytes}

        @rtype: L{bytes}
        """
        if self.isPublic():
            return self._toPublicOpenSSH(comment=comment)
        # No pre-v1 format is defined for Ed25519 keys.
        elif subtype == "v1" or (subtype is None and self.type() == "Ed25519"):
            return self._toPrivateOpenSSH_v1(comment=comment, passphrase=passphrase)
        elif subtype is None or subtype == "PEM":
            return self._toPrivateOpenSSH_PEM(passphrase=passphrase)
        else:
            raise ValueError(f"unknown subtype {subtype}")

    def _toString_LSH(self, **kwargs):
        """
        Return a public or private LSH key.  See _fromString_PUBLIC_LSH and
        _fromString_PRIVATE_LSH for the key formats.

        @rtype: L{bytes}
        """
        data = self.data()
        type = self.type()
        if self.isPublic():
            if type == "RSA":
                keyData = sexpy.pack(
                    [
                        [
                            b"public-key",
                            [
                                b"rsa-pkcs1-sha1",
                                [b"n", common.MP(data["n"])[4:]],
                                [b"e", common.MP(data["e"])[4:]],
                            ],
                        ]
                    ]
                )
            elif type == "DSA":
                keyData = sexpy.pack(
                    [
                        [
                            b"public-key",
                            [
                                b"dsa",
                                [b"p", common.MP(data["p"])[4:]],
                                [b"q", common.MP(data["q"])[4:]],
                                [b"g", common.MP(data["g"])[4:]],
                                [b"y", common.MP(data["y"])[4:]],
                            ],
                        ]
                    ]
                )
            else:
                raise BadKeyError(f"unknown key type {type}")
            return b"{" + encodebytes(keyData).replace(b"\n", b"") + b"}"
        else:
            if type == "RSA":
                p, q = data["p"], data["q"]
                iqmp = rsa.rsa_crt_iqmp(p, q)
                return sexpy.pack(
                    [
                        [
                            b"private-key",
                            [
                                b"rsa-pkcs1",
                                [b"n", common.MP(data["n"])[4:]],
                                [b"e", common.MP(data["e"])[4:]],
                                [b"d", common.MP(data["d"])[4:]],
                                [b"p", common.MP(q)[4:]],
                                [b"q", common.MP(p)[4:]],
                                [b"a", common.MP(data["d"] % (q - 1))[4:]],
                                [b"b", common.MP(data["d"] % (p - 1))[4:]],
                                [b"c", common.MP(iqmp)[4:]],
                            ],
                        ]
                    ]
                )
            elif type == "DSA":
                return sexpy.pack(
                    [
                        [
                            b"private-key",
                            [
                                b"dsa",
                                [b"p", common.MP(data["p"])[4:]],
                                [b"q", common.MP(data["q"])[4:]],
                                [b"g", common.MP(data["g"])[4:]],
                                [b"y", common.MP(data["y"])[4:]],
                                [b"x", common.MP(data["x"])[4:]],
                            ],
                        ]
                    ]
                )
            else:
                raise BadKeyError(f"unknown key type {type}'")

    def _toString_AGENTV3(self, **kwargs):
        """
        Return a private Secure Shell Agent v3 key.  See
        _fromString_AGENTV3 for the key format.

        @rtype: L{bytes}
        """
        data = self.data()
        if not self.isPublic():
            if self.type() == "RSA":
                values = (
                    data["e"],
                    data["d"],
                    data["n"],
                    data["u"],
                    data["p"],
                    data["q"],
                )
            elif self.type() == "DSA":
                values = (data["p"], data["q"], data["g"], data["y"], data["x"])
            return common.NS(self.sshType()) + b"".join(map(common.MP, values))

    def sign(self, data, signatureType=None):
        """
        Sign some data with this key.

        SECSH-TRANS RFC 4253 Section 6.6.

        @type data: L{bytes}
        @param data: The data to sign.

        @type signatureType: L{bytes}
        @param signatureType: The SSH public key algorithm name to sign this
        data with, or L{None} to use a reasonable default for the key.

        @rtype: L{bytes}
        @return: A signature for the given data.
        """
        keyType = self.type()
        if signatureType is None:
            # Use the SSH public key type name by default, since for all
            # current key types this can also be used as a public key
            # algorithm name.  (This exists for compatibility; new code
            # should explicitly specify a public key algorithm name.)
            signatureType = self.sshType()

        hashAlgorithm = self._getHashAlgorithm(signatureType)
        if hashAlgorithm is None:
            raise BadSignatureAlgorithmError(
                f"public key signature algorithm {signatureType} is not "
                f"defined for {keyType} keys"
            )

        if keyType == "RSA":
            sig = self._keyObject.sign(data, padding.PKCS1v15(), hashAlgorithm)
            ret = common.NS(sig)

        elif keyType == "DSA":
            sig = self._keyObject.sign(data, hashAlgorithm)
            (r, s) = decode_dss_signature(sig)
            # SSH insists that the DSS signature blob be two 160-bit integers
            # concatenated together. The sig[0], [1] numbers from obj.sign
            # are just numbers, and could be any length from 0 to 160 bits.
            # Make sure they are padded out to 160 bits (20 bytes each)
            ret = common.NS(int_to_bytes(r, 20) + int_to_bytes(s, 20))

        elif keyType == "EC":  # Pragma: no branch
            signature = self._keyObject.sign(data, ec.ECDSA(hashAlgorithm))
            (r, s) = decode_dss_signature(signature)

            rb = int_to_bytes(r)
            sb = int_to_bytes(s)

            # Int_to_bytes returns rb[0] as a str in python2
            # and an as int in python3
            if type(rb[0]) is str:
                rcomp = ord(rb[0])
            else:
                rcomp = rb[0]

            # If the MSB is set, prepend a null byte for correct formatting.
            if rcomp & 0x80:
                rb = b"\x00" + rb

            if type(sb[0]) is str:
                scomp = ord(sb[0])
            else:
                scomp = sb[0]

            if scomp & 0x80:
                sb = b"\x00" + sb

            ret = common.NS(common.NS(rb) + common.NS(sb))

        elif keyType == "Ed25519":
            ret = common.NS(self._keyObject.sign(data))
        return common.NS(signatureType) + ret

    def verify(self, signature, data):
        """
        Verify a signature using this key.

        @type signature: L{bytes}
        @param signature: The signature to verify.

        @type data: L{bytes}
        @param data: The signed data.

        @rtype: L{bool}
        @return: C{True} if the signature is valid.
        """
        if len(signature) == 40:
            # DSA key with no padding
            signatureType, signature = b"ssh-dss", common.NS(signature)
        else:
            signatureType, signature = common.getNS(signature)

        hashAlgorithm = self._getHashAlgorithm(signatureType)
        if hashAlgorithm is None:
            return False

        keyType = self.type()
        if keyType == "RSA":
            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()
            args = (
                common.getNS(signature)[0],
                data,
                padding.PKCS1v15(),
                hashAlgorithm,
            )
        elif keyType == "DSA":
            concatenatedSignature = common.getNS(signature)[0]
            r = int.from_bytes(concatenatedSignature[:20], "big")
            s = int.from_bytes(concatenatedSignature[20:], "big")
            signature = encode_dss_signature(r, s)
            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()
            args = (signature, data, hashAlgorithm)

        elif keyType == "EC":  # Pragma: no branch
            concatenatedSignature = common.getNS(signature)[0]
            rstr, sstr, rest = common.getNS(concatenatedSignature, 2)
            r = int.from_bytes(rstr, "big")
            s = int.from_bytes(sstr, "big")
            signature = encode_dss_signature(r, s)

            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()

            args = (signature, data, ec.ECDSA(hashAlgorithm))

        elif keyType == "Ed25519":
            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()
            args = (common.getNS(signature)[0], data)

        try:
            k.verify(*args)
        except InvalidSignature:
            return False
        else:
            return True


def _getPersistentRSAKey(location, keySize=4096):
    """
    This function returns a persistent L{Key}.

    The key is loaded from a PEM file in C{location}. If it does not exist, a
    key with the key size of C{keySize} is generated and saved.

    @param location: Where the key is stored.
    @type location: L{twisted.python.filepath.FilePath}

    @param keySize: The size of the key, if it needs to be generated.
    @type keySize: L{int}

    @returns: A persistent key.
    @rtype: L{Key}
    """
    location.parent().makedirs(ignoreExistingDirectory=True)

    # If it doesn't exist, we want to generate a new key and save it
    if not location.exists():
        privateKey = rsa.generate_private_key(
            public_exponent=65537, key_size=keySize, backend=default_backend()
        )

        pem = privateKey.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        location.setContent(pem)

    # By this point (save any hilarious race conditions) we should have a
    # working PEM file. Load it!
    # (Future archaeological readers: I chose not to short circuit above,
    # because then there's two exit paths to this code!)
    with location.open("rb") as keyFile:
        privateKey = serialization.load_pem_private_key(
            keyFile.read(), password=None, backend=default_backend()
        )
        return Key(privateKey)
