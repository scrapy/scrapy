# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.ssh.keys}.
"""

from __future__ import absolute_import, division

try:
    import cryptography
except ImportError:
    cryptography = None
    skipCryptography = 'Cannot run without cryptography.'

try:
    import Crypto.Cipher.DES3
    import Crypto.PublicKey.RSA
    import Crypto.PublicKey.DSA
except ImportError:
    # we'll have to skip some tests without PyCypto
    Crypto = None
    skipPyCrypto = 'Cannot run without PyCrypto.'
try:
    import pyasn1
except ImportError:
    pyasn1 = None

if cryptography and pyasn1:
    from twisted.conch.ssh import keys, common, sexpy

import base64
import os

from twisted.conch.test import keydata
from twisted.python import randbytes
from twisted.trial import unittest
from twisted.python.compat import long, _PY3
from twisted.python.versions import Version
from twisted.python.filepath import FilePath



class ObjectTypeTests(unittest.TestCase):
    """
    Unit tests for the objectType method.
    """

    if cryptography is None:
        skip = skipCryptography
    if Crypto is None:
        skip = "Cannot run without PyCrypto."
    if _PY3:
        skip = "objectType is deprecated and is not being ported to Python 3."


    def getRSAKey(self):
        """
        Return a PyCrypto RSA key to support the tests.

        @return: The RSA key to support the tests.
        @rtype: C{Crypto.PublicKey.RSA}
        """
        # Use lazy import as PyCrypto will be deprecated.
        from Crypto.PublicKey import RSA

        return RSA.construct((
            keydata.RSAData['n'],
            keydata.RSAData['e'],
            keydata.RSAData['d'],
            ))


    def getDSAKey(self):
        """
        Return a PyCrypto DSA key to support the tests.

        @return: The DSA key to support the tests.
        @rtype: C{Crypto.PublicKey.DSA}
        """
        # Use lazy import as PyCrypto will be deprecated.
        from Crypto.PublicKey import DSA

        return DSA.construct((
            keydata.DSAData['y'],
            keydata.DSAData['g'],
            keydata.DSAData['p'],
            keydata.DSAData['q'],
            keydata.DSAData['x'],
            ))


    def checkDeprecation(self):
        """
        Check that we have a deprecation warning for C{objectType}.
        """
        warnings = self.flushWarnings()
        self.assertEqual(1, len(warnings))
        self.assertIs(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(
            'twisted.conch.ssh.keys.objectType was deprecated in '
            'Twisted 15.5.0',
            warnings[0]['message'])


    def test_objectType_rsa(self):
        """
        C{ssh-rsa} is the type of the RSA keys.
        """
        key = self.getRSAKey()

        self.assertEqual(keys.objectType(key), b'ssh-rsa')
        self.checkDeprecation()


    def test_objectType_dsa(self):
        """
        C{ssh-dss} is the type of the DSA keys.
        """
        key = self.getDSAKey()

        self.assertEqual(keys.objectType(key), b'ssh-dss')
        self.checkDeprecation()


    def test_objectKey_none(self):
        """
        A BadKeyError is raised when getting the type of L{None}.
        """
        self.assertRaises(keys.BadKeyError, keys.objectType, None)
        self.checkDeprecation()


    def test_deprecation(self):
        """
        It is deprecated.
        """
        key = self.getRSAKey()

        keys.objectType(key)

        self.checkDeprecation()



class KeyTests(unittest.TestCase):

    if cryptography is None:
        skip = skipCryptography
    if pyasn1 is None:
        skip = "Cannot run without PyASN1"


    def setUp(self):
        self.rsaObj = keys.Key._fromRSAComponents(
            n=keydata.RSAData['n'],
            e=keydata.RSAData['e'],
            d=keydata.RSAData['d'],
            p=keydata.RSAData['p'],
            q=keydata.RSAData['q'],
            u=keydata.RSAData['u'],
            )._keyObject
        self.dsaObj = keys.Key._fromDSAComponents(
            y=keydata.DSAData['y'],
            p=keydata.DSAData['p'],
            q=keydata.DSAData['q'],
            g=keydata.DSAData['g'],
            x=keydata.DSAData['x'],
            )._keyObject
        self.rsaSignature = (b'\x00\x00\x00\x07ssh-rsa\x00'
            b'\x00\x00`N\xac\xb4@qK\xa0(\xc3\xf2h \xd3\xdd\xee6Np\x9d_'
            b'\xb0>\xe3\x0c(L\x9d{\txUd|!\xf6m\x9c\xd3\x93\x842\x7fU'
            b'\x05\xf4\xf7\xfaD\xda\xce\x81\x8ea\x7f=Y\xed*\xb7\xba\x81'
            b'\xf2\xad\xda\xeb(\x97\x03S\x08\x81\xc7\xb1\xb7\xe6\xe3'
            b'\xcd*\xd4\xbd\xc0wt\xf7y\xcd\xf0\xb7\x7f\xfb\x1e>\xf9r'
            b'\x8c\xba')
        self.dsaSignature = (
            b'\x00\x00\x00\x07ssh-dss\x00\x00\x00(?\xc7\xeb\x86;\xd5TFA\xb4'
            b'\xdf\x0c\xc4E@4,d\xbc\t\xd9\xae\xdd[\xed-\x82nQ\x8cf\x9b\xe8\xe1'
            b'jrg\x84p<'
        )
        self.patch(randbytes, 'secureRandom', lambda x: b'\xff' * x)
        self.keyFile = self.mktemp()
        with open(self.keyFile, 'wb') as f:
            f.write(keydata.privateRSA_lsh)


    def tearDown(self):
        os.unlink(self.keyFile)


    def test__guessStringType(self):
        """
        Test that the _guessStringType method guesses string types
        correctly.
        """
        self.assertEqual(keys.Key._guessStringType(keydata.publicRSA_openssh),
                'public_openssh')
        self.assertEqual(keys.Key._guessStringType(keydata.publicDSA_openssh),
                'public_openssh')
        self.assertEqual(keys.Key._guessStringType(
            keydata.privateRSA_openssh), 'private_openssh')
        self.assertEqual(keys.Key._guessStringType(
            keydata.privateDSA_openssh), 'private_openssh')
        self.assertEqual(keys.Key._guessStringType(keydata.publicRSA_lsh),
                'public_lsh')
        self.assertEqual(keys.Key._guessStringType(keydata.publicDSA_lsh),
                'public_lsh')
        self.assertEqual(keys.Key._guessStringType(keydata.privateRSA_lsh),
                'private_lsh')
        self.assertEqual(keys.Key._guessStringType(keydata.privateDSA_lsh),
                'private_lsh')
        self.assertEqual(keys.Key._guessStringType(
            keydata.privateRSA_agentv3), 'agentv3')
        self.assertEqual(keys.Key._guessStringType(
            keydata.privateDSA_agentv3), 'agentv3')
        self.assertEqual(keys.Key._guessStringType(
            b'\x00\x00\x00\x07ssh-rsa\x00\x00\x00\x01\x01'),
            'blob')
        self.assertEqual(keys.Key._guessStringType(
            b'\x00\x00\x00\x07ssh-dss\x00\x00\x00\x01\x01'),
            'blob')
        self.assertEqual(keys.Key._guessStringType(b'not a key'),
                None)


    def _testPublicPrivateFromString(self, public, private, type, data):
        self._testPublicFromString(public, type, data)
        self._testPrivateFromString(private, type, data)


    def _testPublicFromString(self, public, type, data):
        publicKey = keys.Key.fromString(public)
        self.assertTrue(publicKey.isPublic())
        self.assertEqual(publicKey.type(), type)
        for k, v in publicKey.data().items():
            self.assertEqual(data[k], v)


    def _testPrivateFromString(self, private, type, data):
        privateKey = keys.Key.fromString(private)
        self.assertFalse(privateKey.isPublic())
        self.assertEqual(privateKey.type(), type)
        for k, v in data.items():
            self.assertEqual(privateKey.data()[k], v)


    def test_fromOpenSSH(self):
        """
        Test that keys are correctly generated from OpenSSH strings.
        """
        self._testPublicPrivateFromString(keydata.publicRSA_openssh,
                keydata.privateRSA_openssh, 'RSA', keydata.RSAData)
        self.assertEqual(keys.Key.fromString(
            keydata.privateRSA_openssh_encrypted,
            passphrase=b'encrypted'),
            keys.Key.fromString(keydata.privateRSA_openssh))
        self.assertEqual(keys.Key.fromString(
            keydata.privateRSA_openssh_alternate),
            keys.Key.fromString(keydata.privateRSA_openssh))
        self._testPublicPrivateFromString(keydata.publicDSA_openssh,
                keydata.privateDSA_openssh, 'DSA', keydata.DSAData)


    def test_fromOpenSSH_with_whitespace(self):
        """
        If key strings have trailing whitespace, it should be ignored.
        """
        # from bug #3391, since our test key data doesn't have
        # an issue with appended newlines
        privateDSAData = b"""-----BEGIN DSA PRIVATE KEY-----
MIIBuwIBAAKBgQDylESNuc61jq2yatCzZbenlr9llG+p9LhIpOLUbXhhHcwC6hrh
EZIdCKqTO0USLrGoP5uS9UHAUoeN62Z0KXXWTwOWGEQn/syyPzNJtnBorHpNUT9D
Qzwl1yUa53NNgEctpo4NoEFOx8PuU6iFLyvgHCjNn2MsuGuzkZm7sI9ZpQIVAJiR
9dPc08KLdpJyRxz8T74b4FQRAoGAGBc4Z5Y6R/HZi7AYM/iNOM8su6hrk8ypkBwR
a3Dbhzk97fuV3SF1SDrcQu4zF7c4CtH609N5nfZs2SUjLLGPWln83Ysb8qhh55Em
AcHXuROrHS/sDsnqu8FQp86MaudrqMExCOYyVPE7jaBWW+/JWFbKCxmgOCSdViUJ
esJpBFsCgYEA7+jtVvSt9yrwsS/YU1QGP5wRAiDYB+T5cK4HytzAqJKRdC5qS4zf
C7R0eKcDHHLMYO39aPnCwXjscisnInEhYGNblTDyPyiyNxAOXuC8x7luTmwzMbNJ
/ow0IqSj0VF72VJN9uSoPpFd4lLT0zN8v42RWja0M8ohWNf+YNJluPgCFE0PT4Vm
SUrCyZXsNh6VXwjs3gKQ
-----END DSA PRIVATE KEY-----"""
        self.assertEqual(keys.Key.fromString(privateDSAData),
                         keys.Key.fromString(privateDSAData + b'\n'))


    def test_fromNewerOpenSSH(self):
        """
        Newer versions of OpenSSH generate encrypted keys which have a longer
        IV than the older versions.  These newer keys are also loaded.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh_encrypted_aes,
                                  passphrase=b'testxp')
        self.assertEqual(key.type(), 'RSA')
        key2 = keys.Key.fromString(
            keydata.privateRSA_openssh_encrypted_aes + b'\n',
            passphrase=b'testxp')
        self.assertEqual(key, key2)


    def test_fromLSHPublicUnsupportedType(self):
        """
        C{BadKeyError} exception is raised when public key has an unknown
        type.
        """
        sexp = sexpy.pack([[b'public-key', [b'bad-key', [b'p', b'2']]]])

        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString, data=b'{' + base64.encodestring(sexp) + b'}',
            )


    def test_fromLSHPrivateUnsupportedType(self):
        """
        C{BadKeyError} exception is raised when private key has an unknown
        type.
        """
        sexp = sexpy.pack([[b'private-key', [b'bad-key', [b'p', b'2']]]])

        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString, sexp,
            )


    def test_fromLSHRSA(self):
        """
        RSA public and private keys can be generated from a LSH strings.
        """
        self._testPublicPrivateFromString(
            keydata.publicRSA_lsh,
            keydata.privateRSA_lsh,
            'RSA',
            keydata.RSAData,
            )


    def test_fromLSHDSA(self):
        """
        DSA public and private key can be generated from LSHs.
        """
        self._testPublicPrivateFromString(
            keydata.publicDSA_lsh,
            keydata.privateDSA_lsh,
            'DSA',
            keydata.DSAData,
            )


    def test_fromAgentv3(self):
        """
        Test that keys are correctly generated from Agent v3 strings.
        """
        self._testPrivateFromString(keydata.privateRSA_agentv3, 'RSA',
                keydata.RSAData)
        self._testPrivateFromString(keydata.privateDSA_agentv3, 'DSA',
                keydata.DSAData)
        self.assertRaises(keys.BadKeyError, keys.Key.fromString,
                b'\x00\x00\x00\x07ssh-foo'+ b'\x00\x00\x00\x01\x01'*5)


    def test_fromStringErrors(self):
        """
        keys.Key.fromString should raise BadKeyError when the key is invalid.
        """
        self.assertRaises(keys.BadKeyError, keys.Key.fromString, b'')
        # no key data with a bad key type
        self.assertRaises(keys.BadKeyError, keys.Key.fromString, b'',
                'bad_type')
        # trying to decrypt a key which doesn't support encryption
        self.assertRaises(keys.BadKeyError, keys.Key.fromString,
                keydata.publicRSA_lsh, passphrase = b'unencrypted')
        # trying to decrypt a key with the wrong passphrase
        self.assertRaises(keys.EncryptedKeyError, keys.Key.fromString,
                keys.Key(self.rsaObj).toString('openssh', b'encrypted'))
        # key with no key data
        self.assertRaises(keys.BadKeyError, keys.Key.fromString,
                b'-----BEGIN RSA KEY-----\nwA==\n')
        # key with invalid DEK Info
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromString,
            b"""-----BEGIN ENCRYPTED RSA KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: weird type

4Ed/a9OgJWHJsne7yOGWeWMzHYKsxuP9w1v0aYcp+puS75wvhHLiUnNwxz0KDi6n
T3YkKLBsoCWS68ApR2J9yeQ6R+EyS+UQDrO9nwqo3DB5BT3Ggt8S1wE7vjNLQD0H
g/SJnlqwsECNhh8aAx+Ag0m3ZKOZiRD5mCkcDQsZET7URSmFytDKOjhFn3u6ZFVB
sXrfpYc6TJtOQlHd/52JB6aAbjt6afSv955Z7enIi+5yEJ5y7oYQTaE5zrFMP7N5
9LbfJFlKXxEddy/DErRLxEjmC+t4svHesoJKc2jjjyNPiOoGGF3kJXea62vsjdNV
gMK5Eged3TBVIk2dv8rtJUvyFeCUtjQ1UJZIebScRR47KrbsIpCmU8I4/uHWm5hW
0mOwvdx1L/mqx/BHqVU9Dw2COhOdLbFxlFI92chkovkmNk4P48ziyVnpm7ME22sE
vfCMsyirdqB1mrL4CSM7FXONv+CgfBfeYVkYW8RfJac9U1L/O+JNn7yee414O/rS
hRYw4UdWnH6Gg6niklVKWNY0ZwUZC8zgm2iqy8YCYuneS37jC+OEKP+/s6HSKuqk
2bzcl3/TcZXNSM815hnFRpz0anuyAsvwPNRyvxG2/DacJHL1f6luV4B0o6W410yf
qXQx01DLo7nuyhJqoH3UGCyyXB+/QUs0mbG2PAEn3f5dVs31JMdbt+PrxURXXjKk
4cexpUcIpqqlfpIRe3RD0sDVbH4OXsGhi2kiTfPZu7mgyFxKopRbn1KwU1qKinfY
EU9O4PoTak/tPT+5jFNhaP+HrURoi/pU8EAUNSktl7xAkHYwkN/9Cm7DeBghgf3n
8+tyCGYDsB5utPD0/Xe9yx0Qhc/kMm4xIyQDyA937dk3mUvLC9vulnAP8I+Izim0
fZ182+D1bWwykoD0997mUHG/AUChWR01V1OLwRyPv2wUtiS8VNG76Y2aqKlgqP1P
V+IvIEqR4ERvSBVFzXNF8Y6j/sVxo8+aZw+d0L1Ns/R55deErGg3B8i/2EqGd3r+
0jps9BqFHHWW87n3VyEB3jWCMj8Vi2EJIfa/7pSaViFIQn8LiBLf+zxG5LTOToK5
xkN42fReDcqi3UNfKNGnv4dsplyTR2hyx65lsj4bRKDGLKOuB1y7iB0AGb0LtcAI
dcsVlcCeUquDXtqKvRnwfIMg+ZunyjqHBhj3qgRgbXbT6zjaSdNnih569aTg0Vup
VykzZ7+n/KVcGLmvX0NesdoI7TKbq4TnEIOynuG5Sf+2GpARO5bjcWKSZeN/Ybgk
gccf8Cqf6XWqiwlWd0B7BR3SymeHIaSymC45wmbgdstrbk7Ppa2Tp9AZku8M2Y7c
8mY9b+onK075/ypiwBm4L4GRNTFLnoNQJXx0OSl4FNRWsn6ztbD+jZhu8Seu10Jw
SEJVJ+gmTKdRLYORJKyqhDet6g7kAxs4EoJ25WsOnX5nNr00rit+NkMPA7xbJT+7
CfI51GQLw7pUPeO2WNt6yZO/YkzZrqvTj5FEwybkUyBv7L0gkqu9wjfDdUw0fVHE
xEm4DxjEoaIp8dW/JOzXQ2EF+WaSOgdYsw3Ac+rnnjnNptCdOEDGP6QBkt+oXj4P
-----END RSA PRIVATE KEY-----""", passphrase='encrypted')
        # key with invalid encryption type
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromString,
            b"""-----BEGIN ENCRYPTED RSA KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: FOO-123-BAR,01234567

4Ed/a9OgJWHJsne7yOGWeWMzHYKsxuP9w1v0aYcp+puS75wvhHLiUnNwxz0KDi6n
T3YkKLBsoCWS68ApR2J9yeQ6R+EyS+UQDrO9nwqo3DB5BT3Ggt8S1wE7vjNLQD0H
g/SJnlqwsECNhh8aAx+Ag0m3ZKOZiRD5mCkcDQsZET7URSmFytDKOjhFn3u6ZFVB
sXrfpYc6TJtOQlHd/52JB6aAbjt6afSv955Z7enIi+5yEJ5y7oYQTaE5zrFMP7N5
9LbfJFlKXxEddy/DErRLxEjmC+t4svHesoJKc2jjjyNPiOoGGF3kJXea62vsjdNV
gMK5Eged3TBVIk2dv8rtJUvyFeCUtjQ1UJZIebScRR47KrbsIpCmU8I4/uHWm5hW
0mOwvdx1L/mqx/BHqVU9Dw2COhOdLbFxlFI92chkovkmNk4P48ziyVnpm7ME22sE
vfCMsyirdqB1mrL4CSM7FXONv+CgfBfeYVkYW8RfJac9U1L/O+JNn7yee414O/rS
hRYw4UdWnH6Gg6niklVKWNY0ZwUZC8zgm2iqy8YCYuneS37jC+OEKP+/s6HSKuqk
2bzcl3/TcZXNSM815hnFRpz0anuyAsvwPNRyvxG2/DacJHL1f6luV4B0o6W410yf
qXQx01DLo7nuyhJqoH3UGCyyXB+/QUs0mbG2PAEn3f5dVs31JMdbt+PrxURXXjKk
4cexpUcIpqqlfpIRe3RD0sDVbH4OXsGhi2kiTfPZu7mgyFxKopRbn1KwU1qKinfY
EU9O4PoTak/tPT+5jFNhaP+HrURoi/pU8EAUNSktl7xAkHYwkN/9Cm7DeBghgf3n
8+tyCGYDsB5utPD0/Xe9yx0Qhc/kMm4xIyQDyA937dk3mUvLC9vulnAP8I+Izim0
fZ182+D1bWwykoD0997mUHG/AUChWR01V1OLwRyPv2wUtiS8VNG76Y2aqKlgqP1P
V+IvIEqR4ERvSBVFzXNF8Y6j/sVxo8+aZw+d0L1Ns/R55deErGg3B8i/2EqGd3r+
0jps9BqFHHWW87n3VyEB3jWCMj8Vi2EJIfa/7pSaViFIQn8LiBLf+zxG5LTOToK5
xkN42fReDcqi3UNfKNGnv4dsplyTR2hyx65lsj4bRKDGLKOuB1y7iB0AGb0LtcAI
dcsVlcCeUquDXtqKvRnwfIMg+ZunyjqHBhj3qgRgbXbT6zjaSdNnih569aTg0Vup
VykzZ7+n/KVcGLmvX0NesdoI7TKbq4TnEIOynuG5Sf+2GpARO5bjcWKSZeN/Ybgk
gccf8Cqf6XWqiwlWd0B7BR3SymeHIaSymC45wmbgdstrbk7Ppa2Tp9AZku8M2Y7c
8mY9b+onK075/ypiwBm4L4GRNTFLnoNQJXx0OSl4FNRWsn6ztbD+jZhu8Seu10Jw
SEJVJ+gmTKdRLYORJKyqhDet6g7kAxs4EoJ25WsOnX5nNr00rit+NkMPA7xbJT+7
CfI51GQLw7pUPeO2WNt6yZO/YkzZrqvTj5FEwybkUyBv7L0gkqu9wjfDdUw0fVHE
xEm4DxjEoaIp8dW/JOzXQ2EF+WaSOgdYsw3Ac+rnnjnNptCdOEDGP6QBkt+oXj4P
-----END RSA PRIVATE KEY-----""", passphrase='encrypted')
        # key with bad IV (AES)
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromString,
            b"""-----BEGIN ENCRYPTED RSA KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: AES-128-CBC,01234

4Ed/a9OgJWHJsne7yOGWeWMzHYKsxuP9w1v0aYcp+puS75wvhHLiUnNwxz0KDi6n
T3YkKLBsoCWS68ApR2J9yeQ6R+EyS+UQDrO9nwqo3DB5BT3Ggt8S1wE7vjNLQD0H
g/SJnlqwsECNhh8aAx+Ag0m3ZKOZiRD5mCkcDQsZET7URSmFytDKOjhFn3u6ZFVB
sXrfpYc6TJtOQlHd/52JB6aAbjt6afSv955Z7enIi+5yEJ5y7oYQTaE5zrFMP7N5
9LbfJFlKXxEddy/DErRLxEjmC+t4svHesoJKc2jjjyNPiOoGGF3kJXea62vsjdNV
gMK5Eged3TBVIk2dv8rtJUvyFeCUtjQ1UJZIebScRR47KrbsIpCmU8I4/uHWm5hW
0mOwvdx1L/mqx/BHqVU9Dw2COhOdLbFxlFI92chkovkmNk4P48ziyVnpm7ME22sE
vfCMsyirdqB1mrL4CSM7FXONv+CgfBfeYVkYW8RfJac9U1L/O+JNn7yee414O/rS
hRYw4UdWnH6Gg6niklVKWNY0ZwUZC8zgm2iqy8YCYuneS37jC+OEKP+/s6HSKuqk
2bzcl3/TcZXNSM815hnFRpz0anuyAsvwPNRyvxG2/DacJHL1f6luV4B0o6W410yf
qXQx01DLo7nuyhJqoH3UGCyyXB+/QUs0mbG2PAEn3f5dVs31JMdbt+PrxURXXjKk
4cexpUcIpqqlfpIRe3RD0sDVbH4OXsGhi2kiTfPZu7mgyFxKopRbn1KwU1qKinfY
EU9O4PoTak/tPT+5jFNhaP+HrURoi/pU8EAUNSktl7xAkHYwkN/9Cm7DeBghgf3n
8+tyCGYDsB5utPD0/Xe9yx0Qhc/kMm4xIyQDyA937dk3mUvLC9vulnAP8I+Izim0
fZ182+D1bWwykoD0997mUHG/AUChWR01V1OLwRyPv2wUtiS8VNG76Y2aqKlgqP1P
V+IvIEqR4ERvSBVFzXNF8Y6j/sVxo8+aZw+d0L1Ns/R55deErGg3B8i/2EqGd3r+
0jps9BqFHHWW87n3VyEB3jWCMj8Vi2EJIfa/7pSaViFIQn8LiBLf+zxG5LTOToK5
xkN42fReDcqi3UNfKNGnv4dsplyTR2hyx65lsj4bRKDGLKOuB1y7iB0AGb0LtcAI
dcsVlcCeUquDXtqKvRnwfIMg+ZunyjqHBhj3qgRgbXbT6zjaSdNnih569aTg0Vup
VykzZ7+n/KVcGLmvX0NesdoI7TKbq4TnEIOynuG5Sf+2GpARO5bjcWKSZeN/Ybgk
gccf8Cqf6XWqiwlWd0B7BR3SymeHIaSymC45wmbgdstrbk7Ppa2Tp9AZku8M2Y7c
8mY9b+onK075/ypiwBm4L4GRNTFLnoNQJXx0OSl4FNRWsn6ztbD+jZhu8Seu10Jw
SEJVJ+gmTKdRLYORJKyqhDet6g7kAxs4EoJ25WsOnX5nNr00rit+NkMPA7xbJT+7
CfI51GQLw7pUPeO2WNt6yZO/YkzZrqvTj5FEwybkUyBv7L0gkqu9wjfDdUw0fVHE
xEm4DxjEoaIp8dW/JOzXQ2EF+WaSOgdYsw3Ac+rnnjnNptCdOEDGP6QBkt+oXj4P
-----END RSA PRIVATE KEY-----""", passphrase='encrypted')
        # key with bad IV (DES3)
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromString,
            b"""-----BEGIN ENCRYPTED RSA KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: DES-EDE3-CBC,01234

4Ed/a9OgJWHJsne7yOGWeWMzHYKsxuP9w1v0aYcp+puS75wvhHLiUnNwxz0KDi6n
T3YkKLBsoCWS68ApR2J9yeQ6R+EyS+UQDrO9nwqo3DB5BT3Ggt8S1wE7vjNLQD0H
g/SJnlqwsECNhh8aAx+Ag0m3ZKOZiRD5mCkcDQsZET7URSmFytDKOjhFn3u6ZFVB
sXrfpYc6TJtOQlHd/52JB6aAbjt6afSv955Z7enIi+5yEJ5y7oYQTaE5zrFMP7N5
9LbfJFlKXxEddy/DErRLxEjmC+t4svHesoJKc2jjjyNPiOoGGF3kJXea62vsjdNV
gMK5Eged3TBVIk2dv8rtJUvyFeCUtjQ1UJZIebScRR47KrbsIpCmU8I4/uHWm5hW
0mOwvdx1L/mqx/BHqVU9Dw2COhOdLbFxlFI92chkovkmNk4P48ziyVnpm7ME22sE
vfCMsyirdqB1mrL4CSM7FXONv+CgfBfeYVkYW8RfJac9U1L/O+JNn7yee414O/rS
hRYw4UdWnH6Gg6niklVKWNY0ZwUZC8zgm2iqy8YCYuneS37jC+OEKP+/s6HSKuqk
2bzcl3/TcZXNSM815hnFRpz0anuyAsvwPNRyvxG2/DacJHL1f6luV4B0o6W410yf
qXQx01DLo7nuyhJqoH3UGCyyXB+/QUs0mbG2PAEn3f5dVs31JMdbt+PrxURXXjKk
4cexpUcIpqqlfpIRe3RD0sDVbH4OXsGhi2kiTfPZu7mgyFxKopRbn1KwU1qKinfY
EU9O4PoTak/tPT+5jFNhaP+HrURoi/pU8EAUNSktl7xAkHYwkN/9Cm7DeBghgf3n
8+tyCGYDsB5utPD0/Xe9yx0Qhc/kMm4xIyQDyA937dk3mUvLC9vulnAP8I+Izim0
fZ182+D1bWwykoD0997mUHG/AUChWR01V1OLwRyPv2wUtiS8VNG76Y2aqKlgqP1P
V+IvIEqR4ERvSBVFzXNF8Y6j/sVxo8+aZw+d0L1Ns/R55deErGg3B8i/2EqGd3r+
0jps9BqFHHWW87n3VyEB3jWCMj8Vi2EJIfa/7pSaViFIQn8LiBLf+zxG5LTOToK5
xkN42fReDcqi3UNfKNGnv4dsplyTR2hyx65lsj4bRKDGLKOuB1y7iB0AGb0LtcAI
dcsVlcCeUquDXtqKvRnwfIMg+ZunyjqHBhj3qgRgbXbT6zjaSdNnih569aTg0Vup
VykzZ7+n/KVcGLmvX0NesdoI7TKbq4TnEIOynuG5Sf+2GpARO5bjcWKSZeN/Ybgk
gccf8Cqf6XWqiwlWd0B7BR3SymeHIaSymC45wmbgdstrbk7Ppa2Tp9AZku8M2Y7c
8mY9b+onK075/ypiwBm4L4GRNTFLnoNQJXx0OSl4FNRWsn6ztbD+jZhu8Seu10Jw
SEJVJ+gmTKdRLYORJKyqhDet6g7kAxs4EoJ25WsOnX5nNr00rit+NkMPA7xbJT+7
CfI51GQLw7pUPeO2WNt6yZO/YkzZrqvTj5FEwybkUyBv7L0gkqu9wjfDdUw0fVHE
xEm4DxjEoaIp8dW/JOzXQ2EF+WaSOgdYsw3Ac+rnnjnNptCdOEDGP6QBkt+oXj4P
-----END RSA PRIVATE KEY-----""", passphrase='encrypted')


    def test_fromFile(self):
        """
        Test that fromFile works correctly.
        """
        self.assertEqual(keys.Key.fromFile(self.keyFile),
                keys.Key.fromString(keydata.privateRSA_lsh))
        self.assertRaises(keys.BadKeyError, keys.Key.fromFile,
                self.keyFile, 'bad_type')
        self.assertRaises(keys.BadKeyError, keys.Key.fromFile,
                self.keyFile, passphrase='unencrypted')


    def test_init(self):
        """
        Test that the PublicKey object is initialized correctly.
        """
        obj = keys.Key._fromRSAComponents(n=long(5), e=long(3))._keyObject
        key = keys.Key(obj)
        self.assertEqual(key._keyObject, obj)


    def test_equal(self):
        """
        Test that Key objects are compared correctly.
        """
        rsa1 = keys.Key(self.rsaObj)
        rsa2 = keys.Key(self.rsaObj)
        rsa3 = keys.Key(
            keys.Key._fromRSAComponents(n=long(5), e=long(3))._keyObject)
        dsa = keys.Key(self.dsaObj)
        self.assertTrue(rsa1 == rsa2)
        self.assertFalse(rsa1 == rsa3)
        self.assertFalse(rsa1 == dsa)
        self.assertFalse(rsa1 == object)
        self.assertFalse(rsa1 == None)


    def test_notEqual(self):
        """
        Test that Key objects are not-compared correctly.
        """
        rsa1 = keys.Key(self.rsaObj)
        rsa2 = keys.Key(self.rsaObj)
        rsa3 = keys.Key(
            keys.Key._fromRSAComponents(n=long(5), e=long(3))._keyObject)
        dsa = keys.Key(self.dsaObj)
        self.assertFalse(rsa1 != rsa2)
        self.assertTrue(rsa1 != rsa3)
        self.assertTrue(rsa1 != dsa)
        self.assertTrue(rsa1 != object)
        self.assertTrue(rsa1 != None)


    def test_type(self):
        """
        Test that the type method returns the correct type for an object.
        """
        self.assertEqual(keys.Key(self.rsaObj).type(), 'RSA')
        self.assertEqual(keys.Key(self.rsaObj).sshType(), b'ssh-rsa')
        self.assertEqual(keys.Key(self.dsaObj).type(), 'DSA')
        self.assertEqual(keys.Key(self.dsaObj).sshType(), b'ssh-dss')
        self.assertRaises(RuntimeError, keys.Key(None).type)
        self.assertRaises(RuntimeError, keys.Key(None).sshType)
        self.assertRaises(RuntimeError, keys.Key(self).type)
        self.assertRaises(RuntimeError, keys.Key(self).sshType)

    def test_fromBlobUnsupportedType(self):
        """
        A C{BadKeyError} error is raised whey the blob has an unsupported
        key type.
        """
        badBlob = common.NS(b'ssh-bad')

        self.assertRaises(keys.BadKeyError,
                keys.Key.fromString, badBlob)

    def test_fromBlobRSA(self):
        """
        A public RSA key is correctly generated from a public key blob.
        """
        rsaPublicData = {
            'n': keydata.RSAData['n'],
            'e': keydata.RSAData['e'],
            }
        rsaBlob = (
            common.NS(b'ssh-rsa') +
            common.MP(rsaPublicData['e']) +
            common.MP(rsaPublicData['n'])
            )

        rsaKey = keys.Key.fromString(rsaBlob)

        self.assertTrue(rsaKey.isPublic())
        self.assertEqual(rsaPublicData, rsaKey.data())


    def test_fromBlobDSA(self):
        """
        A public DSA key is correctly generated from a public key blob.
        """
        dsaPublicData = {
            'p': keydata.DSAData['p'],
            'q': keydata.DSAData['q'],
            'g': keydata.DSAData['g'],
            'y': keydata.DSAData['y'],
            }
        dsaBlob = (
            common.NS(b'ssh-dss') +
            common.MP(dsaPublicData['p']) +
            common.MP(dsaPublicData['q']) +
            common.MP(dsaPublicData['g']) +
            common.MP(dsaPublicData['y'])
            )

        dsaKey = keys.Key.fromString(dsaBlob)

        self.assertTrue(dsaKey.isPublic())
        self.assertEqual(dsaPublicData, dsaKey.data())

    def test_fromPrivateBlobUnsupportedType(self):
        """
        C{BadKeyError} is raised when loading a private blob with an
        unsupported type.
        """
        badBlob = common.NS(b'ssh-bad')

        self.assertRaises(
            keys.BadKeyError, keys.Key._fromString_PRIVATE_BLOB, badBlob)


    def test_fromPrivateBlobRSA(self):
        """
        A private RSA key is correctly generated from a private key blob.
        """
        rsaBlob = (
            common.NS(b'ssh-rsa') +
            common.MP(keydata.RSAData['n']) +
            common.MP(keydata.RSAData['e']) +
            common.MP(keydata.RSAData['d']) +
            common.MP(keydata.RSAData['u']) +
            common.MP(keydata.RSAData['p']) +
            common.MP(keydata.RSAData['q'])
            )

        rsaKey = keys.Key._fromString_PRIVATE_BLOB(rsaBlob)

        self.assertFalse(rsaKey.isPublic())
        self.assertEqual(keydata.RSAData, rsaKey.data())


    def test_fromPrivateBlobDSA(self):
        """
        A private DSA key is correctly generated from a private key blob.
        """
        dsaBlob = (
            common.NS(b'ssh-dss') +
            common.MP(keydata.DSAData['p']) +
            common.MP(keydata.DSAData['q']) +
            common.MP(keydata.DSAData['g']) +
            common.MP(keydata.DSAData['y']) +
            common.MP(keydata.DSAData['x'])
            )

        dsaKey = keys.Key._fromString_PRIVATE_BLOB(dsaBlob)

        self.assertFalse(dsaKey.isPublic())
        self.assertEqual(keydata.DSAData, dsaKey.data())


    def test_blobRSA(self):
        """
        Return the over-the-wire SSH format of the RSA public key.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).blob(),
            common.NS(b'ssh-rsa') +
            common.MP(self.rsaObj.private_numbers().public_numbers.e) +
            common.MP(self.rsaObj.private_numbers().public_numbers.n)
            )


    def test_blobDSA(self):
        """
        Return the over-the-wire SSH format of the DSA public key.
        """
        publicNumbers = self.dsaObj.private_numbers().public_numbers

        self.assertEqual(
            keys.Key(self.dsaObj).blob(),
            common.NS(b'ssh-dss') +
            common.MP(publicNumbers.parameter_numbers.p) +
            common.MP(publicNumbers.parameter_numbers.q) +
            common.MP(publicNumbers.parameter_numbers.g) +
            common.MP(publicNumbers.y)
            )


    def test_blobNoKey(self):
        """
        C{RuntimeError} is raised when the blob is requested for a Key
        which is not wrapping anything.
        """
        badKey = keys.Key(None)

        self.assertRaises(RuntimeError, badKey.blob)


    def test_privateBlobRSA(self):
        """
        L{keys.Key.privateBlob} returns the SSH protocol-level format of an
        RSA private key.
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        numbers = self.rsaObj.private_numbers()
        u = rsa.rsa_crt_iqmp(numbers.q, numbers.p)
        self.assertEqual(
            keys.Key(self.rsaObj).privateBlob(),
            common.NS(b'ssh-rsa') +
            common.MP(self.rsaObj.private_numbers().public_numbers.n) +
            common.MP(self.rsaObj.private_numbers().public_numbers.e) +
            common.MP(self.rsaObj.private_numbers().d) +
            common.MP(u) +
            common.MP(self.rsaObj.private_numbers().p) +
            common.MP(self.rsaObj.private_numbers().q)
            )


    def test_privateBlobDSA(self):
        """
        L{keys.Key.privateBlob} returns the SSH protocol-level format of a DSA
        private key.
        """
        publicNumbers = self.dsaObj.private_numbers().public_numbers

        self.assertEqual(
            keys.Key(self.dsaObj).privateBlob(),
            common.NS(b'ssh-dss') +
            common.MP(publicNumbers.parameter_numbers.p) +
            common.MP(publicNumbers.parameter_numbers.q) +
            common.MP(publicNumbers.parameter_numbers.g) +
            common.MP(publicNumbers.y) +
            common.MP(self.dsaObj.private_numbers().x)
            )


    def test_privateBlobNoKeyObject(self):
        """
        Raises L{RuntimeError} if the underlying key object does not exists.
        """
        badKey = keys.Key(None)

        self.assertRaises(RuntimeError, badKey.privateBlob)


    def test_toOpenSSHRSA(self):
        """
        L{keys.Key.toString} serializes an RSA key in OpenSSH format.
        """
        key = keys.Key.fromString(keydata.privateRSA_agentv3)
        self.assertEqual(key.toString('openssh'), keydata.privateRSA_openssh)
        self.assertEqual(key.toString('openssh', b'encrypted'),
                keydata.privateRSA_openssh_encrypted)
        self.assertEqual(key.public().toString('openssh'),
                keydata.publicRSA_openssh[:-8]) # no comment
        self.assertEqual(key.public().toString('openssh', b'comment'),
                keydata.publicRSA_openssh)


    def test_toOpenSSHDSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in OpenSSH format.
        """
        key = keys.Key.fromString(keydata.privateDSA_lsh)
        self.assertEqual(key.toString('openssh'), keydata.privateDSA_openssh)
        self.assertEqual(key.public().toString('openssh', b'comment'),
                keydata.publicDSA_openssh)
        self.assertEqual(key.public().toString('openssh'),
                keydata.publicDSA_openssh[:-8]) # no comment


    def test_toLSHRSA(self):
        """
        L{keys.Key.toString} serializes an RSA key in LSH format.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertEqual(key.toString('lsh'), keydata.privateRSA_lsh)
        self.assertEqual(key.public().toString('lsh'),
                keydata.publicRSA_lsh)


    def test_toLSHDSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in LSH format.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        self.assertEqual(key.toString('lsh'), keydata.privateDSA_lsh)
        self.assertEqual(key.public().toString('lsh'),
                keydata.publicDSA_lsh)


    def test_toAgentv3RSA(self):
        """
        L{keys.Key.toString} serializes an RSA key in Agent v3 format.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertEqual(key.toString('agentv3'), keydata.privateRSA_agentv3)


    def test_toAgentv3DSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in Agent v3 format.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        self.assertEqual(key.toString('agentv3'), keydata.privateDSA_agentv3)


    def test_toStringErrors(self):
        """
        L{keys.Key.toString} raises L{keys.BadKeyError} when passed an invalid
        format type.
        """
        self.assertRaises(keys.BadKeyError, keys.Key(self.rsaObj).toString,
                'bad_type')


    def test_signAndVerifyRSA(self):
        """
        Signed data can be verified using RSA.
        """
        data = b'some-data'
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        signature = key.sign(data)
        self.assertTrue(key.public().verify(signature, data))


    def test_signAndVerifyDSA(self):
        """
        Signed data can be verified using DSA.
        """
        data = b'some-data'
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        signature = key.sign(data)
        self.assertTrue(key.public().verify(signature, data))


    def test_verifyRSA(self):
        """
        A known-good RSA signature verifies successfully.
        """
        key = keys.Key.fromString(keydata.publicRSA_openssh)
        self.assertTrue(key.verify(self.rsaSignature, b''))
        self.assertFalse(key.verify(self.rsaSignature, b'a'))
        self.assertFalse(key.verify(self.dsaSignature, b''))


    def test_verifyDSA(self):
        """
        A known-good DSA signature verifies successfully.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        self.assertTrue(key.verify(self.dsaSignature, b''))
        self.assertFalse(key.verify(self.dsaSignature, b'a'))
        self.assertFalse(key.verify(self.rsaSignature, b''))


    def test_verifyDSANoPrefix(self):
        """
        Some commercial SSH servers send DSA keys as 2 20-byte numbers;
        they are still verified as valid keys.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        self.assertTrue(key.verify(self.dsaSignature[-40:], b''))


    def test_reprPrivateRSA(self):
        """
        The repr of a L{keys.Key} contains all of the RSA components for an RSA
        private key.
        """
        self.assertEqual(repr(keys.Key(self.rsaObj)),
"""<RSA Private Key (768 bits)
attr d:
\t6e:1f:b5:55:97:eb:ed:67:ed:2b:99:6e:ec:c1:ed:
\ta8:4d:52:d6:f3:d6:65:06:04:df:e5:54:9f:cc:89:
\t00:3c:9b:67:87:ec:65:a0:ab:cd:6f:65:90:8a:97:
\t90:4d:c6:21:8f:a8:8d:d8:59:86:43:b5:81:b1:b4:
\td7:5f:2c:22:0a:61:c1:25:8a:47:12:b4:9a:f8:7a:
\t11:1c:4a:a8:8b:75:c4:91:09:3b:be:04:ca:45:d9:
\t57:8a:0d:27:cb:23
attr e:
\t23
attr n:
\t00:af:32:71:f0:e6:0e:9c:99:b3:7f:8b:5f:04:4b:
\tcb:8b:c0:d5:3e:b2:77:fd:cf:64:d8:8f:c0:cf:ae:
\t1f:c6:31:df:f6:29:b2:44:96:e2:c6:d4:21:94:7f:
\t65:7c:d8:d4:23:1f:b8:2e:6a:c9:1f:94:0d:46:c1:
\t69:a2:b7:07:0c:a3:93:c1:34:d8:2e:1e:4a:99:1a:
\t6c:96:46:07:46:2b:dc:25:29:1b:87:f0:be:05:1d:
\tee:b4:34:b9:e7:99:95
attr p:
\t00:cb:4a:4b:d0:40:47:e8:45:52:f7:c7:af:0c:20:
\t6d:43:0d:b6:39:94:f9:da:a5:e5:03:06:76:83:24:
\teb:88:a1:55:a2:a8:de:12:3b:77:49:92:8a:a9:71:
\td2:02:93:ff
attr q:
\t00:dc:9f:6b:d9:98:21:56:11:8d:e9:5f:03:9d:0a:
\td3:93:6e:13:77:41:3c:85:4f:00:70:fd:05:54:ff:
\tbc:3d:09:bf:83:f6:97:7f:64:10:91:04:fe:a2:67:
\t47:54:42:6b
attr u:
\t00:b4:73:97:4b:50:10:a3:17:b3:a8:47:f1:3a:14:
\t76:52:d1:38:2a:cf:12:14:34:c1:a8:54:4c:29:35:
\t80:a0:38:b8:f0:fa:4c:c4:c2:85:ab:db:87:82:ba:
\tdc:eb:db:2a>""")


    def test_reprPublicRSA(self):
        """
        The repr of a L{keys.Key} contains all of the RSA components for an RSA
        public key.
        """
        self.assertEqual(repr(keys.Key(self.rsaObj).public()),
"""<RSA Public Key (768 bits)
attr e:
\t23
attr n:
\t00:af:32:71:f0:e6:0e:9c:99:b3:7f:8b:5f:04:4b:
\tcb:8b:c0:d5:3e:b2:77:fd:cf:64:d8:8f:c0:cf:ae:
\t1f:c6:31:df:f6:29:b2:44:96:e2:c6:d4:21:94:7f:
\t65:7c:d8:d4:23:1f:b8:2e:6a:c9:1f:94:0d:46:c1:
\t69:a2:b7:07:0c:a3:93:c1:34:d8:2e:1e:4a:99:1a:
\t6c:96:46:07:46:2b:dc:25:29:1b:87:f0:be:05:1d:
\tee:b4:34:b9:e7:99:95>""")



class KeyKeyObjectTests(unittest.TestCase):
    """
    The L{keys.Key.keyObject} property provides deprecated access to a PyCrypto
    key instance of the corresponding type.
    """
    if cryptography is None:
        skip = skipCryptography

    if Crypto is None:
        skip = skipPyCrypto


    def test_deprecation(self):
        """
        Accessing the L{keys.Key.keyObject} property emits a deprecation
        warning.
        """
        keys.Key.fromString(keydata.publicRSA_openssh).keyObject

        [warning] = self.flushWarnings([KeyKeyObjectTests.test_deprecation])
        self.assertIs(warning['category'], DeprecationWarning)


    def test_keyObjectGetRSAPublic(self):
        """
        The PyCrypto key instance for an RSA public key has the same components
        as the internal key.
        """
        key = keys.Key.fromString(keydata.publicRSA_openssh)

        result = key.keyObject

        self.assertIsInstance(result, Crypto.PublicKey.RSA._RSAobj)
        self.assertEqual(keydata.RSAData['e'], result.key.e)
        self.assertEqual(keydata.RSAData['n'], result.key.n)


    def test_keyObjectGetRSAPrivate(self):
        """
        The PyCrypto key instance for an RSA private key has the same
        components as the internal key.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)

        result = key.keyObject

        self.assertIsInstance(result, Crypto.PublicKey.RSA._RSAobj)
        self.assertEqual(keydata.RSAData['e'], result.key.e)
        self.assertEqual(keydata.RSAData['n'], result.key.n)
        self.assertEqual(keydata.RSAData['d'], result.key.d)
        self.assertEqual(keydata.RSAData['p'], result.key.p)
        self.assertEqual(keydata.RSAData['q'], result.key.q)
        self.assertEqual(keydata.RSAData['u'], result.key.u)


    def test_keyObjectGetDSAPublic(self):
        """
        The PyCrypto key instance for a DSA public key has the same components
        as the internal key.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)

        result = key.keyObject

        self.assertIsInstance(result, Crypto.PublicKey.DSA._DSAobj)
        self.assertEqual(keydata.DSAData['y'], result.key.y)
        self.assertEqual(keydata.DSAData['g'], result.key.g)
        self.assertEqual(keydata.DSAData['p'], result.key.p)
        self.assertEqual(keydata.DSAData['q'], result.key.q)


    def test_keyObjectGetDSAPrivate(self):
        """
        The PyCrypto key instance for a DSA private key has the same components
        as the internal key.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)

        result = key.keyObject

        self.assertIsInstance(result, Crypto.PublicKey.DSA._DSAobj)
        self.assertEqual(keydata.DSAData['y'], result.key.y)
        self.assertEqual(keydata.DSAData['g'], result.key.g)
        self.assertEqual(keydata.DSAData['p'], result.key.p)
        self.assertEqual(keydata.DSAData['q'], result.key.q)
        self.assertEqual(keydata.DSAData['x'], result.key.x)


    def test_keyObjectSetRSAPublic(self):
        """
        Setting the L{keys.Key.keyObject} property to a PyCrypto public RSA key
        instance updates the internal key.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        newPyCryptoKey = Crypto.PublicKey.RSA.construct((
            keydata.RSAData['n'],
            keydata.RSAData['e'],
            ))
        self.assertEqual('DSA', key.type())

        key.keyObject = newPyCryptoKey
        [warning] = self.flushWarnings([
            KeyKeyObjectTests.test_keyObjectSetRSAPublic])
        self.assertIs(warning['category'], DeprecationWarning)

        self.assertEqual('RSA', key.type())
        self.assertEqual({
            'n': keydata.RSAData['n'],
            'e': keydata.RSAData['e'],
            },
            key.data())


    def test_keyObjectSetRSAPrivate(self):
        """
        Setting the L{keys.Key.keyObject} property to a PyCrypto private RSA
        key instance updates the internal key.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        newPyCryptoKey = Crypto.PublicKey.RSA.construct((
            keydata.RSAData['n'],
            keydata.RSAData['e'],
            keydata.RSAData['d'],
            keydata.RSAData['p'],
            keydata.RSAData['q'],
            keydata.RSAData['u'],
            ))
        self.assertEqual('DSA', key.type())

        key.keyObject = newPyCryptoKey

        self.assertEqual('RSA', key.type())
        self.assertEqual({
            'n': keydata.RSAData['n'],
            'e': keydata.RSAData['e'],
            'd': keydata.RSAData['d'],
            'p': keydata.RSAData['p'],
            'q': keydata.RSAData['q'],
            'u': keydata.RSAData['u'],
            },
            key.data())


    def test_keyObjectSetDSAPublic(self):
        """
        Setting the L{keys.Key.keyObject} property to a PyCrypto public DSA key
        instance updates the internal key.
        """
        key = keys.Key.fromString(keydata.publicRSA_openssh)
        newPyCryptoKey = Crypto.PublicKey.DSA.construct((
            keydata.DSAData['y'],
            keydata.DSAData['g'],
            keydata.DSAData['p'],
            keydata.DSAData['q'],
            ))
        self.assertEqual('RSA', key.type())

        key.keyObject = newPyCryptoKey

        self.assertEqual('DSA', key.type())
        self.assertEqual({
            'y': keydata.DSAData['y'],
            'g': keydata.DSAData['g'],
            'p': keydata.DSAData['p'],
            'q': keydata.DSAData['q'],
            },
            key.data())


    def test_keyObjectSetDSAPrivate(self):
        """
        Setting the L{keys.Key.keyObject} property to a PyCrypto private DSA
        key instance updates the internal key.
        """
        key = keys.Key.fromString(keydata.publicRSA_openssh)
        newPyCryptoKey = Crypto.PublicKey.DSA.construct((
            keydata.DSAData['y'],
            keydata.DSAData['g'],
            keydata.DSAData['p'],
            keydata.DSAData['q'],
            keydata.DSAData['x'],
            ))
        self.assertEqual('RSA', key.type())

        key.keyObject = newPyCryptoKey

        self.assertEqual('DSA', key.type())
        self.assertEqual({
            'y': keydata.DSAData['y'],
            'g': keydata.DSAData['g'],
            'p': keydata.DSAData['p'],
            'q': keydata.DSAData['q'],
            'x': keydata.DSAData['x'],
            },
            key.data())


    def test_constructorPyCrypto(self):
        """
        Passing a PyCrypto key object to L{keys.Key} is deprecated.
        """
        pycryptoKey = Crypto.PublicKey.RSA.construct((
            keydata.RSAData['n'],
            keydata.RSAData['e']))
        key = self.callDeprecated(
            (Version('Twisted', 16, 0, 0),
             'passing a cryptography key object'),
            keys.Key,
            pycryptoKey)
        self.assertEqual('RSA', key.type())
        self.assertEqual({
            'n': keydata.RSAData['n'],
            'e': keydata.RSAData['e'],
            },
            key.data())



class PersistentRSAKeyTests(unittest.TestCase):
    """
    Tests for L{keys._getPersistentRSAKey}.
    """

    if cryptography is None:
        skip = skipCryptography


    def test_providedArguments(self):
        """
        L{keys._getPersistentRSAKey} will put the key in
        C{directory}/C{filename}, with the key length of C{keySize}.
        """
        tempDir = FilePath(self.mktemp())
        keyFile = tempDir.child("mykey.pem")

        key = keys._getPersistentRSAKey(keyFile, keySize=512)
        self.assertEqual(key.size(), 512)
        self.assertTrue(keyFile.exists())


    def test_noRegeneration(self):
        """
        L{keys._getPersistentRSAKey} will not regenerate the key if the key
        already exists.
        """
        tempDir = FilePath(self.mktemp())
        keyFile = tempDir.child("mykey.pem")

        key = keys._getPersistentRSAKey(keyFile, keySize=512)
        self.assertEqual(key.size(), 512)
        self.assertTrue(keyFile.exists())
        keyContent = keyFile.getContent()

        # Set the key size to 1024 bits. Since it exists already, it will find
        # the 512 bit key, and not generate a 1024 bit key.
        key = keys._getPersistentRSAKey(keyFile, keySize=1024)
        self.assertEqual(key.size(), 512)
        self.assertEqual(keyFile.getContent(), keyContent)
