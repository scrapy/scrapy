# -*- test-case-name: twisted.conch.test.test_keys -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Handling of RSA and DSA keys.
"""

from __future__ import absolute_import, division

import binascii
import itertools
import warnings

from hashlib import md5

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, rsa, padding
try:
    from cryptography.hazmat.primitives.asymmetric.utils import (
        encode_dss_signature, decode_dss_signature)
except ImportError:
    from cryptography.hazmat.primitives.asymmetric.utils import (
        encode_rfc6979_signature as encode_dss_signature,
        decode_rfc6979_signature as decode_dss_signature)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from pyasn1.error import PyAsn1Error
from pyasn1.type import univ
from pyasn1.codec.ber import decoder as berDecoder
from pyasn1.codec.ber import encoder as berEncoder

from twisted.conch.ssh import common, sexpy
from twisted.conch.ssh.common import int_from_bytes, int_to_bytes
from twisted.python import randbytes
from twisted.python.compat import (
    iterbytes, long, izip, nativeString, _PY3,
    _b64decodebytes as decodebytes, _b64encodebytes as encodebytes)
from twisted.python.deprecate import deprecated, getDeprecationWarningString
from twisted.python.versions import Version



class BadKeyError(Exception):
    """
    Raised when a key isn't what we expected from it.

    XXX: we really need to check for bad keys
    """



class EncryptedKeyError(Exception):
    """
    Raised when an encrypted key is presented to fromString/fromFile without
    a password.
    """



class Key(object):
    """
    An object representing a key.  A key can be either a public or
    private key.  A public key can verify a signature; a private key can
    create or verify a signature.  To generate a string that can be stored
    on disk, use the toString method.  If you have a private key, but want
    the string representation of the public key, use Key.public().toString().

    @ivar keyObject: DEPRECATED. The C{Crypto.PublicKey} object
        that operations are performed with.
    """
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
        with open(filename, 'rb') as f:
            return cls.fromString(f.read(), type, passphrase)
    fromFile = classmethod(fromFile)


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
        if type is None:
            type = cls._guessStringType(data)
        if type is None:
            raise BadKeyError('cannot guess the type of %r' % (data,))
        method = getattr(cls, '_fromString_%s' % (type.upper(),), None)
        if method is None:
            raise BadKeyError('no _fromString method for %s' % (type,))
        if method.__code__.co_argcount == 2:  # No passphrase
            if passphrase:
                raise BadKeyError('key not encrypted')
            return method(data)
        else:
            return method(data, passphrase)
    fromString = classmethod(fromString)


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

        @type blob: L{bytes}
        @param blob: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type (the first string) is unknown.
        """
        keyType, rest = common.getNS(blob)
        if keyType == b'ssh-rsa':
            e, n, rest = common.getMP(rest, 2)
            return cls(
                rsa.RSAPublicNumbers(e, n).public_key(default_backend()))
        elif keyType == b'ssh-dss':
            p, q, g, y, rest = common.getMP(rest, 4)
            return cls(
                dsa.DSAPublicNumbers(
                    y=y,
                    parameter_numbers=dsa.DSAParameterNumbers(
                        p=p,
                        q=q,
                        g=g
                    )
                ).public_key(default_backend())
            )
        else:
            raise BadKeyError('unknown blob type: %s' % (keyType,))


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

        @type blob: L{bytes}
        @param blob: The key data.

        @return: A new key.
        @rtype: L{twisted.conch.ssh.keys.Key}
        @raises BadKeyError: if the key type (the first string) is unknown.
        """
        keyType, rest = common.getNS(blob)

        if keyType == b'ssh-rsa':
            n, e, d, u, p, q, rest = common.getMP(rest, 6)
            return cls._fromRSAComponents(n=n, e=e, d=d, p=p, q=q)
        elif keyType == b'ssh-dss':
            p, q, g, y, x, rest = common.getMP(rest, 5)
            return cls._fromDSAComponents(y=y, g=g, p=p, q=q, x=x)
        else:
            raise BadKeyError('unknown blob type: %s' % (keyType,))


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
        blob = decodebytes(data.split()[1])
        return cls._fromString_BLOB(blob)


    @classmethod
    def _fromString_PRIVATE_OPENSSH(cls, data, passphrase):
        """
        Return a private key object corresponding to this OpenSSH private key
        string.  If the key is encrypted, passphrase MUST be provided.
        Providing a passphrase for an unencrypted key is an error.

        The format of an OpenSSH private key string is::
            -----BEGIN <key type> PRIVATE KEY-----
            [Proc-Type: 4,ENCRYPTED
            DEK-Info: DES-EDE3-CBC,<initialization value>]
            <base64-encoded ASN.1 structure>
            ------END <key type> PRIVATE KEY------

        The ASN.1 structure of a RSA key is::
            (0, n, e, d, p, q)

        The ASN.1 structure of a DSA key is::
            (0, p, q, g, y, x)

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
        lines = data.strip().split(b'\n')
        kind = lines[0][11:14]
        if lines[1].startswith(b'Proc-Type: 4,ENCRYPTED'):
            if not passphrase:
                raise EncryptedKeyError('Passphrase must be provided '
                                        'for an encrypted key')

            # Determine cipher and initialization vector
            try:
                _, cipherIVInfo = lines[2].split(b' ', 1)
                cipher, ivdata = cipherIVInfo.rstrip().split(b',', 1)
            except ValueError:
                raise BadKeyError('invalid DEK-info %r' % (lines[2],))

            if cipher == b'AES-128-CBC':
                algorithmClass = algorithms.AES
                keySize = 16
                if len(ivdata) != 32:
                    raise BadKeyError('AES encrypted key with a bad IV')
            elif cipher == b'DES-EDE3-CBC':
                algorithmClass = algorithms.TripleDES
                keySize = 24
                if len(ivdata) != 16:
                    raise BadKeyError('DES encrypted key with a bad IV')
            else:
                raise BadKeyError('unknown encryption type %r' % (cipher,))

            # Extract keyData for decoding
            iv = bytes(bytearray([int(ivdata[i:i + 2], 16)
                                  for i in range(0, len(ivdata), 2)]))
            ba = md5(passphrase + iv[:8]).digest()
            bb = md5(ba + passphrase + iv[:8]).digest()
            decKey = (ba + bb)[:keySize]
            b64Data = decodebytes(b''.join(lines[3:-1]))

            decryptor = Cipher(
                algorithmClass(decKey),
                modes.CBC(iv),
                backend=default_backend()
            ).decryptor()
            keyData = decryptor.update(b64Data) + decryptor.finalize()

            removeLen = ord(keyData[-1:])
            keyData = keyData[:-removeLen]
        else:
            b64Data = b''.join(lines[1:-1])
            keyData = decodebytes(b64Data)

        try:
            decodedKey = berDecoder.decode(keyData)[0]
        except PyAsn1Error as e:
            raise BadKeyError(
                'Failed to decode key (Bad Passphrase?): %s' % (e,))

        if kind == b'RSA':
            if len(decodedKey) == 2:  # Alternate RSA key
                decodedKey = decodedKey[0]
            if len(decodedKey) < 6:
                raise BadKeyError('RSA key failed to decode properly')

            n, e, d, p, q, dmp1, dmq1, iqmp = [
                long(value) for value in decodedKey[1:9]
            ]
            if p > q:  # Make p smaller than q
                p, q = q, p
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
        elif kind == b'DSA':
            p, q, g, y, x = [long(value) for value in decodedKey[1: 6]]
            if len(decodedKey) < 6:
                raise BadKeyError('DSA key failed to decode properly')
            return cls(
                dsa.DSAPrivateNumbers(
                    x=x,
                    public_numbers=dsa.DSAPublicNumbers(
                        y=y,
                        parameter_numbers=dsa.DSAParameterNumbers(
                            p=p,
                            q=q,
                            g=g
                        )
                    )
                ).private_key(backend=default_backend())
            )
        else:
            raise BadKeyError("unknown key type %s" % (kind,))


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
        assert sexp[0] == b'public-key'
        kd = {}
        for name, data in sexp[1][1:]:
            kd[name] = common.getMP(common.NS(data))[0]
        if sexp[1][0] == b'dsa':
            return cls._fromDSAComponents(
                y=kd[b'y'], g=kd[b'g'], p=kd[b'p'], q=kd[b'q'])

        elif sexp[1][0] == b'rsa-pkcs1-sha1':
            return cls._fromRSAComponents(n=kd[b'n'], e=kd[b'e'])
        else:
            raise BadKeyError('unknown lsh key type %s' % (sexp[1][0],))


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
        assert sexp[0] == b'private-key'
        kd = {}
        for name, data in sexp[1][1:]:
            kd[name] = common.getMP(common.NS(data))[0]
        if sexp[1][0] == b'dsa':
            assert len(kd) == 5, len(kd)
            return cls._fromDSAComponents(
                y=kd[b'y'], g=kd[b'g'], p=kd[b'p'], q=kd[b'q'], x=kd[b'x'])
        elif sexp[1][0] == b'rsa-pkcs1':
            assert len(kd) == 8, len(kd)
            if kd[b'p'] > kd[b'q']:  # Make p smaller than q
                kd[b'p'], kd[b'q'] = kd[b'q'], kd[b'p']
            return cls._fromRSAComponents(
                n=kd[b'n'], e=kd[b'e'], d=kd[b'd'], p=kd[b'p'], q=kd[b'q'])

        else:
            raise BadKeyError('unknown lsh key type %s' % (sexp[1][0],))


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
        if keyType == b'ssh-dss':
            p, data = common.getMP(data)
            q, data = common.getMP(data)
            g, data = common.getMP(data)
            y, data = common.getMP(data)
            x, data = common.getMP(data)
            return cls._fromDSAComponents(y=y, g=g, p=p, q=q, x=x)
        elif keyType == b'ssh-rsa':
            e, data = common.getMP(data)
            d, data = common.getMP(data)
            n, data = common.getMP(data)
            u, data = common.getMP(data)
            p, data = common.getMP(data)
            q, data = common.getMP(data)
            return cls._fromRSAComponents(n=n, e=e, d=d, p=p, q=q, u=u)
        else:
            raise BadKeyError("unknown key type %s" % (keyType,))


    def _guessStringType(cls, data):
        """
        Guess the type of key in data.  The types map to _fromString_*
        methods.

        @type data: L{bytes}
        @param data: The key data.
        """
        if data.startswith(b'ssh-'):
            return 'public_openssh'
        elif data.startswith(b'-----BEGIN'):
            return 'private_openssh'
        elif data.startswith(b'{'):
            return 'public_lsh'
        elif data.startswith(b'('):
            return 'private_lsh'
        elif data.startswith(b'\x00\x00\x00\x07ssh-'):
            ignored, rest = common.getNS(data)
            count = 0
            while rest:
                count += 1
                ignored, rest = common.getMP(rest)
            if count > 4:
                return 'agentv3'
            else:
                return 'blob'
    _guessStringType = classmethod(_guessStringType)


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
            y=y, parameter_numbers=dsa.DSAParameterNumbers(p=p, q=q, g=g))
        if x is None:
            # We have public components.
            keyObject = publicNumbers.public_key(default_backend())
        else:
            privateNumbers = dsa.DSAPrivateNumbers(
                x=x, public_numbers=publicNumbers)
            keyObject = privateNumbers.private_key(default_backend())

        return cls(keyObject)


    def __init__(self, keyObject):
        """
        Initialize with a private or public
        C{cryptography.hazmat.primitives.asymmetric} key.

        @param keyObject: Low level key.
        @type keyObject: C{cryptography.hazmat.primitives.asymmetric} key.
        """
        # Avoid importing PyCrypto if at all possible
        if keyObject.__class__.__module__.startswith('Crypto.PublicKey'):
            warningString = getDeprecationWarningString(
                Key,
                Version("Twisted", 16, 0, 0),
                replacement='passing a cryptography key object')
            warnings.warn(warningString, DeprecationWarning, stacklevel=2)
            self.keyObject = keyObject
        else:
            self._keyObject = keyObject


    def __eq__(self, other):
        """
        Return True if other represents an object with the same key.
        """
        if type(self) == type(other):
            return self.type() == other.type() and self.data() == other.data()
        else:
            return NotImplemented


    def __ne__(self, other):
        """
        Return True if other represents anything other than this key.
        """
        result = self.__eq__(other)
        if result == NotImplemented:
            return result
        return not result


    def __repr__(self):
        """
        Return a pretty representation of this object.
        """
        lines = [
            '<%s %s (%s bits)' % (
                nativeString(self.type()),
                self.isPublic() and 'Public Key' or 'Private Key',
                self._keyObject.key_size)]
        for k, v in sorted(self.data().items()):
            if _PY3 and isinstance(k, bytes):
                k = k.decode('ascii')
            lines.append('attr %s:' % (k,))
            by = common.MP(v)[4:]
            while by:
                m = by[:15]
                by = by[15:]
                o = ''
                for c in iterbytes(m):
                    o = o + '%02x:' % (ord(c),)
                if len(m) < 15:
                    o = o[:-1]
                lines.append('\t' + o)
        lines[-1] = lines[-1] + '>'
        return '\n'.join(lines)


    @property
    @deprecated(Version('Twisted', 16, 0, 0))
    def keyObject(self):
        """
        A C{Crypto.PublicKey} object similar to this key.

        As PyCrypto is no longer used for the underlying operations, this
        property should be avoided.
        """
        # Lazy import to have PyCrypto as a soft dependency.
        from Crypto.PublicKey import DSA, RSA

        keyObject = None
        keyType = self.type()
        keyData = self.data()
        isPublic = self.isPublic()

        if keyType == 'RSA':
            if isPublic:
                keyObject = RSA.construct((
                    keyData['n'],
                    long(keyData['e']),
                    ))
            else:
                keyObject = RSA.construct((
                    keyData['n'],
                    long(keyData['e']),
                    keyData['d'],
                    keyData['p'],
                    keyData['q'],
                    keyData['u'],
                    ))
        elif keyType == 'DSA':
            if isPublic:
                keyObject = DSA.construct((
                    keyData['y'],
                    keyData['g'],
                    keyData['p'],
                    keyData['q'],
                    ))
            else:
                keyObject = DSA.construct((
                    keyData['y'],
                    keyData['g'],
                    keyData['p'],
                    keyData['q'],
                    keyData['x'],
                    ))
        else:
            raise BadKeyError('Unsupported key type.')

        return keyObject


    @keyObject.setter
    @deprecated(Version('Twisted', 16, 0, 0))
    def keyObject(self, value):
        # Lazy import to have PyCrypto as a soft dependency.
        from Crypto.PublicKey import DSA, RSA

        if isinstance(value, RSA._RSAobj):
            rawKey = value.key
            if rawKey.has_private():
                newKey = self._fromRSAComponents(
                    e=rawKey.e,
                    n=rawKey.n,
                    p=rawKey.p,
                    q=rawKey.q,
                    d=rawKey.d,
                    u=rawKey.u,
                    )
            else:
                newKey = self._fromRSAComponents(e=rawKey.e, n=rawKey.n)
        elif isinstance(value, DSA._DSAobj):
            rawKey = value.key
            if rawKey.has_private():
                newKey = self._fromDSAComponents(
                    y=rawKey.y,
                    p=rawKey.p,
                    q=rawKey.q,
                    g=rawKey.g,
                    x=rawKey.x,
                    )
            else:
                newKey = self._fromDSAComponents(
                    y=rawKey.y,
                    p=rawKey.p,
                    q=rawKey.q,
                    g=rawKey.g,
                    )
        else:
            raise BadKeyError('PyCrypto key type not supported.')

        self._keyObject = newKey._keyObject


    def isPublic(self):
        """
        Check if this instance is a public key.

        @return: C{True} if this is a public key.
        """
        return isinstance(
            self._keyObject, (rsa.RSAPublicKey, dsa.DSAPublicKey))


    def public(self):
        """
        Returns a version of this key containing only the public key data.
        If this is a public key, this may or may not be the same object
        as self.

        @rtype: L{Key}
        @return: A public key.
        """
        return Key(self._keyObject.public_key())


    def fingerprint(self):
        """
        Get the user presentation of the fingerprint of this L{Key}.  As
        described by U{RFC 4716 section
        4<http://tools.ietf.org/html/rfc4716#section-4>}::

            The fingerprint of a public key consists of the output of the MD5
            message-digest algorithm [RFC1321].  The input to the algorithm is
            the public key data as specified by [RFC4253].  (...)  The output
            of the (MD5) algorithm is presented to the user as a sequence of 16
            octets printed as hexadecimal with lowercase letters and separated
            by colons.

        @since: 8.2

        @return: the user presentation of this L{Key}'s fingerprint, as a
        string.

        @rtype: L{str}
        """
        return nativeString(
            b':'.join([binascii.hexlify(x)
                       for x in iterbytes(md5(self.blob()).digest())]))


    def type(self):
        """
        Return the type of the object we wrap.  Currently this can only be
        'RSA' or 'DSA'.

        @rtype: L{str}
        """
        if isinstance(
                self._keyObject, (rsa.RSAPublicKey, rsa.RSAPrivateKey)):
            return 'RSA'
        elif isinstance(
                self._keyObject, (dsa.DSAPublicKey, dsa.DSAPrivateKey)):
            return 'DSA'
        else:
            raise RuntimeError(
                'unknown type of object: %r' % (self._keyObject,))


    def sshType(self):
        """
        Get the type of the object we wrap as defined in the SSH protocol,
        defined in RFC 4253, Section 6.6. Currently this can only be b'ssh-rsa'
        or b'ssh-dss'.

        @return: The key type format.
        @rtype: L{bytes}
        """
        return {'RSA': b'ssh-rsa', 'DSA': b'ssh-dss'}[self.type()]


    def size(self):
        """
        Return the size of the object we wrap.

        @return: The size of the key.
        @rtype: L{int}
        """
        if self._keyObject is None:
            return 0
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
        else:
            raise RuntimeError("Unexpected key type: %s" % (self._keyObject,))


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

        @rtype: L{bytes}
        """
        type = self.type()
        data = self.data()
        if type == 'RSA':
            return (common.NS(b'ssh-rsa') + common.MP(data['e']) +
                    common.MP(data['n']))
        elif type == 'DSA':
            return (common.NS(b'ssh-dss') + common.MP(data['p']) +
                    common.MP(data['q']) + common.MP(data['g']) +
                    common.MP(data['y']))
        else:
            raise BadKeyError("unknown key type %s" % (type,))


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
        """
        type = self.type()
        data = self.data()
        if type == 'RSA':
            return (common.NS(b'ssh-rsa') + common.MP(data['n']) +
                    common.MP(data['e']) + common.MP(data['d']) +
                    common.MP(data['u']) + common.MP(data['p']) +
                    common.MP(data['q']))
        elif type == 'DSA':
            return (common.NS(b'ssh-dss') + common.MP(data['p']) +
                    common.MP(data['q']) + common.MP(data['g']) +
                    common.MP(data['y']) + common.MP(data['x']))
        else:
            raise BadKeyError("unknown key type %s" % (type,))


    def toString(self, type, extra=None):
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
            encrypt with.
        @type extra: L{bytes} or L{None}

        @rtype: L{bytes}
        """
        method = getattr(self, '_toString_%s' % (type.upper(),), None)
        if method is None:
            raise BadKeyError('unknown key type: %s' % (type,))
        if method.__code__.co_argcount == 2:
            return method(extra)
        else:
            return method()


    def _toString_OPENSSH(self, extra):
        """
        Return a public or private OpenSSH string.  See
        _fromString_PUBLIC_OPENSSH and _fromString_PRIVATE_OPENSSH for the
        string formats.  If extra is present, it represents a comment for a
        public key, or a passphrase for a private key.

        @param extra: Comment for a public key or passphrase for a
            private key
        @type extra: L{bytes}

        @rtype: L{bytes}
        """
        data = self.data()
        if self.isPublic():
            b64Data = encodebytes(self.blob()).replace(b'\n', b'')
            if not extra:
                extra = b''
            return (self.sshType() + b' ' + b64Data + b' ' + extra).strip()
        else:
            lines = [b''.join((b'-----BEGIN ', self.type().encode('ascii'),
                               b' PRIVATE KEY-----'))]
            if self.type() == 'RSA':
                p, q = data['p'], data['q']
                objData = (0, data['n'], data['e'], data['d'], q, p,
                           data['d'] % (q - 1), data['d'] % (p - 1),
                           data['u'])
            else:
                objData = (0, data['p'], data['q'], data['g'], data['y'],
                           data['x'])
            asn1Sequence = univ.Sequence()
            for index, value in izip(itertools.count(), objData):
                asn1Sequence.setComponentByPosition(index, univ.Integer(value))
            asn1Data = berEncoder.encode(asn1Sequence)
            if extra:
                iv = randbytes.secureRandom(8)
                hexiv = ''.join(['%02X' % (ord(x),) for x in iterbytes(iv)])
                hexiv = hexiv.encode('ascii')
                lines.append(b'Proc-Type: 4,ENCRYPTED')
                lines.append(b'DEK-Info: DES-EDE3-CBC,' + hexiv + b'\n')
                ba = md5(extra + iv).digest()
                bb = md5(ba + extra + iv).digest()
                encKey = (ba + bb)[:24]
                padLen = 8 - (len(asn1Data) % 8)
                asn1Data += (chr(padLen) * padLen).encode('ascii')

                encryptor = Cipher(
                    algorithms.TripleDES(encKey),
                    modes.CBC(iv),
                    backend=default_backend()
                ).encryptor()

                asn1Data = encryptor.update(asn1Data) + encryptor.finalize()

            b64Data = encodebytes(asn1Data).replace(b'\n', b'')
            lines += [b64Data[i:i + 64] for i in range(0, len(b64Data), 64)]
            lines.append(b''.join((b'-----END ', self.type().encode('ascii'),
                                   b' PRIVATE KEY-----')))
            return b'\n'.join(lines)


    def _toString_LSH(self):
        """
        Return a public or private LSH key.  See _fromString_PUBLIC_LSH and
        _fromString_PRIVATE_LSH for the key formats.

        @rtype: L{bytes}
        """
        data = self.data()
        type = self.type()
        if self.isPublic():
            if type == 'RSA':
                keyData = sexpy.pack([[b'public-key',
                                       [b'rsa-pkcs1-sha1',
                                        [b'n', common.MP(data['n'])[4:]],
                                        [b'e', common.MP(data['e'])[4:]]]]])
            elif type == 'DSA':
                keyData = sexpy.pack([[b'public-key',
                                       [b'dsa',
                                        [b'p', common.MP(data['p'])[4:]],
                                        [b'q', common.MP(data['q'])[4:]],
                                        [b'g', common.MP(data['g'])[4:]],
                                        [b'y', common.MP(data['y'])[4:]]]]])
            else:
                raise BadKeyError("unknown key type %s" % (type,))
            return (b'{' + encodebytes(keyData).replace(b'\n', b'') +
                    b'}')
        else:
            if type == 'RSA':
                p, q = data['p'], data['q']
                return sexpy.pack([[b'private-key',
                                    [b'rsa-pkcs1',
                                     [b'n', common.MP(data['n'])[4:]],
                                     [b'e', common.MP(data['e'])[4:]],
                                     [b'd', common.MP(data['d'])[4:]],
                                     [b'p', common.MP(q)[4:]],
                                     [b'q', common.MP(p)[4:]],
                                     [b'a', common.MP(
                                         data['d'] % (q - 1))[4:]],
                                     [b'b', common.MP(
                                         data['d'] % (p - 1))[4:]],
                                     [b'c', common.MP(data['u'])[4:]]]]])
            elif type == 'DSA':
                return sexpy.pack([[b'private-key',
                                    [b'dsa',
                                     [b'p', common.MP(data['p'])[4:]],
                                     [b'q', common.MP(data['q'])[4:]],
                                     [b'g', common.MP(data['g'])[4:]],
                                     [b'y', common.MP(data['y'])[4:]],
                                     [b'x', common.MP(data['x'])[4:]]]]])
            else:
                raise BadKeyError("unknown key type %s'" % (type,))


    def _toString_AGENTV3(self):
        """
        Return a private Secure Shell Agent v3 key.  See
        _fromString_AGENTV3 for the key format.

        @rtype: L{bytes}
        """
        data = self.data()
        if not self.isPublic():
            if self.type() == 'RSA':
                values = (data['e'], data['d'], data['n'], data['u'],
                          data['p'], data['q'])
            elif self.type() == 'DSA':
                values = (data['p'], data['q'], data['g'], data['y'],
                          data['x'])
            return common.NS(self.sshType()) + b''.join(map(common.MP, values))


    def sign(self, data):
        """
        Sign some data with this key.

        SECSH-TRANS RFC 4253 Section 6.6.

        @type data: L{bytes}
        @param data: The data to sign.

        @rtype: L{bytes}
        @return: A signature for the given data.
        """
        if self.type() == 'RSA':
            signer = self._keyObject.signer(
                padding.PKCS1v15(), hashes.SHA1())
            signer.update(data)
            ret = common.NS(signer.finalize())

        elif self.type() == 'DSA':
            signer = self._keyObject.signer(hashes.SHA1())
            signer.update(data)
            signature = signer.finalize()
            (r, s) = decode_dss_signature(signature)
            # SSH insists that the DSS signature blob be two 160-bit integers
            # concatenated together. The sig[0], [1] numbers from obj.sign
            # are just numbers, and could be any length from 0 to 160 bits.
            # Make sure they are padded out to 160 bits (20 bytes each)
            ret = common.NS(int_to_bytes(r, 20) + int_to_bytes(s, 20))

        else:
            raise BadKeyError("unknown key type %s" % (self.type(),))
        return common.NS(self.sshType()) + ret


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
            signatureType, signature = b'ssh-dss', common.NS(signature)
        else:
            signatureType, signature = common.getNS(signature)
        if signatureType != self.sshType():
            return False
        if self.type() == 'RSA':
            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()
            verifier = k.verifier(
                common.getNS(signature)[0],
                padding.PKCS1v15(),
                hashes.SHA1(),
            )
        elif self.type() == 'DSA':
            concatenatedSignature = common.getNS(signature)[0]
            r = int_from_bytes(concatenatedSignature[:20], 'big')
            s = int_from_bytes(concatenatedSignature[20:], 'big')
            signature = encode_dss_signature(r, s)
            k = self._keyObject
            if not self.isPublic():
                k = k.public_key()
            verifier = k.verifier(
                signature, hashes.SHA1())
        else:
            raise BadKeyError("unknown key type %s" % (self.type(),))

        verifier.update(data)
        try:
            verifier.verify()
        except InvalidSignature:
            return False
        else:
            return True



@deprecated(Version("Twisted", 15, 5, 0))
def objectType(obj):
    """
    DEPRECATED. Return the SSH key type corresponding to a
    C{Crypto.PublicKey.pubkey.pubkey} object.

    @param obj: Key for which the type is returned.
    @type obj: C{Crypto.PublicKey.pubkey.pubkey}

    @return: Return the SSH key type corresponding to a PyCrypto object.
    @rtype: L{str}
    """
    keyDataMapping = {
        ('n', 'e', 'd', 'p', 'q'): b'ssh-rsa',
        ('n', 'e', 'd', 'p', 'q', 'u'): b'ssh-rsa',
        ('y', 'g', 'p', 'q', 'x'): b'ssh-dss'
    }
    try:
        return keyDataMapping[tuple(obj.keydata)]
    except (KeyError, AttributeError):
        raise BadKeyError("invalid key object", obj)



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
            public_exponent=65537,
            key_size=keySize,
            backend=default_backend()
        )

        pem = privateKey.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        location.setContent(pem)

    # By this point (save any hilarious race conditions) we should have a
    # working PEM file. Load it!
    # (Future archaeological readers: I chose not to short circuit above,
    # because then there's two exit paths to this code!)
    with location.open("rb") as keyFile:
        privateKey = serialization.load_pem_private_key(
            keyFile.read(),
            password=None,
            backend=default_backend()
        )
        return Key(privateKey)



if _PY3:
    # The objectType function is deprecated and not being ported to Python 3.
    del objectType
