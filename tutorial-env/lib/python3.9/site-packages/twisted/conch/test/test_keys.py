# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.ssh.keys}.
"""


import base64
import os
from textwrap import dedent

from twisted.conch.test import keydata
from twisted.python import randbytes
from twisted.python.filepath import FilePath
from twisted.python.reflect import requireModule
from twisted.trial import unittest

cryptography = requireModule("cryptography")
if cryptography is None:
    skipCryptography = "Cannot run without cryptography."

pyasn1 = requireModule("pyasn1")
_keys_pynacl = requireModule("twisted.conch.ssh._keys_pynacl")


if cryptography and pyasn1:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    from twisted.conch.ssh import common, keys, sexpy

    ED25519_SUPPORTED = (
        default_backend().ed25519_supported() or _keys_pynacl is not None
    )
else:
    ED25519_SUPPORTED = False


def skipWithoutEd25519(f):
    if not ED25519_SUPPORTED:
        f.skip = "ed25519 not supported on this system"
    return f


class KeyTests(unittest.TestCase):

    if cryptography is None:
        skip = skipCryptography
    if pyasn1 is None:
        skip = "Cannot run without PyASN1"

    def setUp(self):
        self.rsaObj = keys.Key._fromRSAComponents(
            n=keydata.RSAData["n"],
            e=keydata.RSAData["e"],
            d=keydata.RSAData["d"],
            p=keydata.RSAData["p"],
            q=keydata.RSAData["q"],
            u=keydata.RSAData["u"],
        )._keyObject
        self.dsaObj = keys.Key._fromDSAComponents(
            y=keydata.DSAData["y"],
            p=keydata.DSAData["p"],
            q=keydata.DSAData["q"],
            g=keydata.DSAData["g"],
            x=keydata.DSAData["x"],
        )._keyObject
        self.ecObj = keys.Key._fromECComponents(
            x=keydata.ECDatanistp256["x"],
            y=keydata.ECDatanistp256["y"],
            privateValue=keydata.ECDatanistp256["privateValue"],
            curve=keydata.ECDatanistp256["curve"],
        )._keyObject
        self.ecObj384 = keys.Key._fromECComponents(
            x=keydata.ECDatanistp384["x"],
            y=keydata.ECDatanistp384["y"],
            privateValue=keydata.ECDatanistp384["privateValue"],
            curve=keydata.ECDatanistp384["curve"],
        )._keyObject
        self.ecObj521 = keys.Key._fromECComponents(
            x=keydata.ECDatanistp521["x"],
            y=keydata.ECDatanistp521["y"],
            privateValue=keydata.ECDatanistp521["privateValue"],
            curve=keydata.ECDatanistp521["curve"],
        )._keyObject
        if ED25519_SUPPORTED:
            self.ed25519Obj = keys.Key._fromEd25519Components(
                a=keydata.Ed25519Data["a"], k=keydata.Ed25519Data["k"]
            )._keyObject
        self.rsaSignature = (
            b"\x00\x00\x00\x07ssh-rsa\x00\x00\x01\x00~Y\xa3\xd7\xfdW\xc6pu@"
            b"\xd81\xa1S\xf3O\xdaE\xf4/\x1ex\x1d\xf1\x9a\xe1G3\xd9\xd6U\x1f"
            b"\x8c\xd9\x1b\x8b\x90\x0e\x8a\xc1\x91\xd8\x0cd\xc9\x0c\xe7\xb2"
            b"\xc9,'=\x15\x1cQg\xe7x\xb5j\xdbI\xc0\xde\xafb\xd7@\xcar\x0b"
            b"\xce\xa3zM\x151q5\xde\xfa\x0c{wjKN\x88\xcbC\xe5\x89\xc3\xf9i"
            b"\x96\x91\xdb\xca}\xdbR\x1a\x13T\xf9\x0cDJH\x0b\x06\xcfl\xf3"
            b"\x13[\x82\xa2\x9d\x93\xfd\x8e\xce|\xfb^n\xd4\xed\xe2\xd1\x8a"
            b"\xb7aY\x9bB\x8f\xa4\xc7\xbe7\xb5\x0b9j\xa4.\x87\x13\xf7\xf0"
            b"\xda\xd7\xd2\xf9\x1f9p\xfd?\x18\x0f\xf2N\x9b\xcf/\x1e)\n>A\x19"
            b"\xc2\xb5j\xf9UW\xd4\xae\x87B\xe6\x99t\xa2y\x90\x98\xa2\xaaf\xcb"
            b"\x86\xe5k\xe3\xce\xe0u\x1c\xeb\x93\x1aN\x88\xc9\x93Y\xc3.V\xb1L"
            b"44`C\xc7\xa66\xaf\xfa\x7f\x04Y\x92\xfa\xa4\x1a\x18%\x19\xd5 4^"
            b"\xb9rY\xba \x01\xf9.\x89%H\xbe\x1c\x83A\x96"
        )
        self.dsaSignature = (
            b"\x00\x00\x00\x07ssh-dss\x00\x00\x00(?\xc7\xeb\x86;\xd5TFA\xb4"
            b"\xdf\x0c\xc4E@4,d\xbc\t\xd9\xae\xdd[\xed-\x82nQ\x8cf\x9b\xe8\xe1"
            b"jrg\x84p<"
        )
        self.patch(randbytes, "secureRandom", lambda x: b"\xff" * x)
        self.keyFile = self.mktemp()
        with open(self.keyFile, "wb") as f:
            f.write(keydata.privateRSA_lsh)

    def tearDown(self):
        os.unlink(self.keyFile)

    def test_size(self):
        """
        The L{keys.Key.size} method returns the size of key object in bits.
        """
        self.assertEqual(keys.Key(self.rsaObj).size(), 2048)
        self.assertEqual(keys.Key(self.dsaObj).size(), 1024)
        self.assertEqual(keys.Key(self.ecObj).size(), 256)
        self.assertEqual(keys.Key(self.ecObj384).size(), 384)
        self.assertEqual(keys.Key(self.ecObj521).size(), 521)
        if ED25519_SUPPORTED:
            self.assertEqual(keys.Key(self.ed25519Obj).size(), 256)

    def test__guessStringType(self):
        """
        Test that the _guessStringType method guesses string types
        correctly.
        """
        self.assertEqual(
            keys.Key._guessStringType(keydata.publicRSA_openssh), "public_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.publicDSA_openssh), "public_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.publicECDSA_openssh), "public_openssh"
        )
        if ED25519_SUPPORTED:
            self.assertEqual(
                keys.Key._guessStringType(keydata.publicEd25519_openssh),
                "public_openssh",
            )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateRSA_openssh), "private_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateRSA_openssh_new), "private_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateDSA_openssh), "private_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateDSA_openssh_new), "private_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateECDSA_openssh), "private_openssh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateECDSA_openssh_new),
            "private_openssh",
        )
        if ED25519_SUPPORTED:
            self.assertEqual(
                keys.Key._guessStringType(keydata.privateEd25519_openssh_new),
                "private_openssh",
            )
        self.assertEqual(keys.Key._guessStringType(keydata.publicRSA_lsh), "public_lsh")
        self.assertEqual(keys.Key._guessStringType(keydata.publicDSA_lsh), "public_lsh")
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateRSA_lsh), "private_lsh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateDSA_lsh), "private_lsh"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateRSA_agentv3), "agentv3"
        )
        self.assertEqual(
            keys.Key._guessStringType(keydata.privateDSA_agentv3), "agentv3"
        )
        self.assertEqual(
            keys.Key._guessStringType(b"\x00\x00\x00\x07ssh-rsa\x00\x00\x00\x01\x01"),
            "blob",
        )
        self.assertEqual(
            keys.Key._guessStringType(b"\x00\x00\x00\x07ssh-dss\x00\x00\x00\x01\x01"),
            "blob",
        )
        self.assertEqual(keys.Key._guessStringType(b"not a key"), None)

    def test_public(self):
        """
        The L{keys.Key.public} method returns a public key for both
        public and private keys.
        """
        # NB: This assumes that the private and public keys correspond
        # to each other.
        privateRSAKey = keys.Key.fromString(keydata.privateRSA_openssh)
        publicRSAKey = keys.Key.fromString(keydata.publicRSA_openssh)
        self.assertEqual(privateRSAKey.public(), publicRSAKey.public())

        privateDSAKey = keys.Key.fromString(keydata.privateDSA_openssh)
        publicDSAKey = keys.Key.fromString(keydata.publicDSA_openssh)
        self.assertEqual(privateDSAKey.public(), publicDSAKey.public())

        privateECDSAKey = keys.Key.fromString(keydata.privateECDSA_openssh)
        publicECDSAKey = keys.Key.fromString(keydata.publicECDSA_openssh)
        self.assertEqual(privateECDSAKey.public(), publicECDSAKey.public())

        if ED25519_SUPPORTED:
            privateEd25519Key = keys.Key.fromString(keydata.privateEd25519_openssh_new)
            publicEd25519Key = keys.Key.fromString(keydata.publicEd25519_openssh)
            self.assertEqual(privateEd25519Key.public(), publicEd25519Key.public())

    def test_isPublic(self):
        """
        The L{keys.Key.isPublic} method returns True for public keys
        otherwise False.
        """
        rsaKey = keys.Key.fromString(keydata.privateRSA_openssh)
        dsaKey = keys.Key.fromString(keydata.privateDSA_openssh)
        ecdsaKey = keys.Key.fromString(keydata.privateECDSA_openssh)
        self.assertTrue(rsaKey.public().isPublic())
        self.assertFalse(rsaKey.isPublic())
        self.assertTrue(dsaKey.public().isPublic())
        self.assertFalse(dsaKey.isPublic())
        self.assertTrue(ecdsaKey.public().isPublic())
        self.assertFalse(ecdsaKey.isPublic())

        if ED25519_SUPPORTED:
            ed25519Key = keys.Key.fromString(keydata.privateEd25519_openssh_new)
            self.assertTrue(ed25519Key.public().isPublic())
            self.assertFalse(ed25519Key.isPublic())

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
        self._testPublicPrivateFromString(
            keydata.publicECDSA_openssh,
            keydata.privateECDSA_openssh,
            "EC",
            keydata.ECDatanistp256,
        )
        self._testPublicPrivateFromString(
            keydata.publicRSA_openssh,
            keydata.privateRSA_openssh,
            "RSA",
            keydata.RSAData,
        )
        self.assertEqual(
            keys.Key.fromString(
                keydata.privateRSA_openssh_encrypted, passphrase=b"encrypted"
            ),
            keys.Key.fromString(keydata.privateRSA_openssh),
        )
        self.assertEqual(
            keys.Key.fromString(keydata.privateRSA_openssh_alternate),
            keys.Key.fromString(keydata.privateRSA_openssh),
        )
        self._testPublicPrivateFromString(
            keydata.publicDSA_openssh,
            keydata.privateDSA_openssh,
            "DSA",
            keydata.DSAData,
        )

        if ED25519_SUPPORTED:
            self._testPublicPrivateFromString(
                keydata.publicEd25519_openssh,
                keydata.privateEd25519_openssh_new,
                "Ed25519",
                keydata.Ed25519Data,
            )

    def test_fromOpenSSHErrors(self):
        """
        Tests for invalid key types.
        """
        badKey = b"""-----BEGIN FOO PRIVATE KEY-----
MIGkAgEBBDAtAi7I8j73WCX20qUM5hhHwHuFzYWYYILs2Sh8UZ+awNkARZ/Fu2LU
LLl5RtOQpbWgBwYFK4EEACKhZANiAATU17sA9P5FRwSknKcFsjjsk0+E3CeXPYX0
Tk/M0HK3PpWQWgrO8JdRHP9eFE9O/23P8BumwFt7F/AvPlCzVd35VfraFT0o4cCW
G0RqpQ+np31aKmeJshkcYALEchnU+tQ=
-----END EC PRIVATE KEY-----"""
        self.assertRaises(
            keys.BadKeyError, keys.Key._fromString_PRIVATE_OPENSSH, badKey, None
        )

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
        self.assertEqual(
            keys.Key.fromString(privateDSAData),
            keys.Key.fromString(privateDSAData + b"\n"),
        )

    def test_fromNewerOpenSSH(self):
        """
        Newer versions of OpenSSH generate encrypted keys which have a longer
        IV than the older versions.  These newer keys are also loaded.
        """
        key = keys.Key.fromString(
            keydata.privateRSA_openssh_encrypted_aes, passphrase=b"testxp"
        )
        self.assertEqual(key.type(), "RSA")
        key2 = keys.Key.fromString(
            keydata.privateRSA_openssh_encrypted_aes + b"\n", passphrase=b"testxp"
        )
        self.assertEqual(key, key2)

    def test_fromOpenSSH_v1_format(self):
        """
        OpenSSH 6.5 introduced a newer "openssh-key-v1" private key format
        (made the default in OpenSSH 7.8).  Loading keys in this format
        produces identical results to loading the same keys in the old
        PEM-based format.
        """
        for old, new in (
            (keydata.privateRSA_openssh, keydata.privateRSA_openssh_new),
            (keydata.privateDSA_openssh, keydata.privateDSA_openssh_new),
            (keydata.privateECDSA_openssh, keydata.privateECDSA_openssh_new),
            (keydata.privateECDSA_openssh384, keydata.privateECDSA_openssh384_new),
            (keydata.privateECDSA_openssh521, keydata.privateECDSA_openssh521_new),
        ):
            self.assertEqual(keys.Key.fromString(new), keys.Key.fromString(old))
        self.assertEqual(
            keys.Key.fromString(
                keydata.privateRSA_openssh_encrypted_new, passphrase=b"encrypted"
            ),
            keys.Key.fromString(
                keydata.privateRSA_openssh_encrypted, passphrase=b"encrypted"
            ),
        )

    def test_fromOpenSSH_windows_line_endings(self):
        """
        Test that keys are correctly generated from OpenSSH strings with
        Windows line endings.
        """
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
        self.assertEqual(
            keys.Key.fromString(privateDSAData),
            keys.Key.fromString(privateDSAData.replace(b"\n", b"\r\n")),
        )

    def test_fromLSHPublicUnsupportedType(self):
        """
        C{BadKeyError} exception is raised when public key has an unknown
        type.
        """
        sexp = sexpy.pack([[b"public-key", [b"bad-key", [b"p", b"2"]]]])

        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
            data=b"{" + base64.b64encode(sexp) + b"}",
        )

    def test_fromLSHPrivateUnsupportedType(self):
        """
        C{BadKeyError} exception is raised when private key has an unknown
        type.
        """
        sexp = sexpy.pack([[b"private-key", [b"bad-key", [b"p", b"2"]]]])

        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
            sexp,
        )

    def test_fromLSHRSA(self):
        """
        RSA public and private keys can be generated from a LSH strings.
        """
        self._testPublicPrivateFromString(
            keydata.publicRSA_lsh,
            keydata.privateRSA_lsh,
            "RSA",
            keydata.RSAData,
        )

    def test_fromLSHDSA(self):
        """
        DSA public and private key can be generated from LSHs.
        """
        self._testPublicPrivateFromString(
            keydata.publicDSA_lsh,
            keydata.privateDSA_lsh,
            "DSA",
            keydata.DSAData,
        )

    def test_fromAgentv3(self):
        """
        Test that keys are correctly generated from Agent v3 strings.
        """
        self._testPrivateFromString(keydata.privateRSA_agentv3, "RSA", keydata.RSAData)
        self._testPrivateFromString(keydata.privateDSA_agentv3, "DSA", keydata.DSAData)
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
            b"\x00\x00\x00\x07ssh-foo" + b"\x00\x00\x00\x01\x01" * 5,
        )

    def test_fromStringNormalizesUnicodePassphrase(self):
        """
        L{keys.Key.fromString} applies Normalization Form KC to Unicode
        passphrases.
        """
        key = keys.Key(self.rsaObj)
        key_data = key.toString("openssh", passphrase="verschl\u00FCsselt".encode())
        self.assertEqual(
            keys.Key.fromString(key_data, passphrase="verschlu\u0308sselt"), key
        )
        # U+FFFF is a "noncharacter" and guaranteed to have General_Category
        # Cn (Unassigned).
        self.assertRaises(
            keys.PassphraseNormalizationError,
            keys.Key.fromString,
            key_data,
            passphrase="unassigned \uFFFF",
        )

    def test_fromStringErrors(self):
        """
        keys.Key.fromString should raise BadKeyError when the key is invalid.
        """
        self.assertRaises(keys.BadKeyError, keys.Key.fromString, b"")
        # no key data with a bad key type
        self.assertRaises(keys.BadKeyError, keys.Key.fromString, b"", "bad_type")
        # trying to decrypt a key which doesn't support encryption
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
            keydata.publicRSA_lsh,
            passphrase=b"unencrypted",
        )
        # trying to decrypt a key with the wrong passphrase
        self.assertRaises(
            keys.EncryptedKeyError,
            keys.Key.fromString,
            keys.Key(self.rsaObj).toString("openssh", passphrase=b"encrypted"),
        )
        # key with no key data
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromString, b"-----BEGIN RSA KEY-----\nwA==\n"
        )
        # key with invalid DEK Info
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
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
-----END RSA PRIVATE KEY-----""",
            passphrase="encrypted",
        )
        # key with invalid encryption type
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
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
-----END RSA PRIVATE KEY-----""",
            passphrase="encrypted",
        )
        # key with bad IV (AES)
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
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
-----END RSA PRIVATE KEY-----""",
            passphrase="encrypted",
        )
        # key with bad IV (DES3)
        self.assertRaises(
            keys.BadKeyError,
            keys.Key.fromString,
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
-----END RSA PRIVATE KEY-----""",
            passphrase="encrypted",
        )

    def test_fromFile(self):
        """
        Test that fromFile works correctly.
        """
        self.assertEqual(
            keys.Key.fromFile(self.keyFile), keys.Key.fromString(keydata.privateRSA_lsh)
        )
        self.assertRaises(keys.BadKeyError, keys.Key.fromFile, self.keyFile, "bad_type")
        self.assertRaises(
            keys.BadKeyError, keys.Key.fromFile, self.keyFile, passphrase="unencrypted"
        )

    def test_init(self):
        """
        Test that the PublicKey object is initialized correctly.
        """
        obj = keys.Key._fromRSAComponents(n=5, e=3)._keyObject
        key = keys.Key(obj)
        self.assertEqual(key._keyObject, obj)

    def test_equal(self):
        """
        Test that Key objects are compared correctly.
        """
        rsa1 = keys.Key(self.rsaObj)
        rsa2 = keys.Key(self.rsaObj)
        rsa3 = keys.Key(keys.Key._fromRSAComponents(n=5, e=3)._keyObject)
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
        rsa3 = keys.Key(keys.Key._fromRSAComponents(n=5, e=3)._keyObject)
        dsa = keys.Key(self.dsaObj)
        self.assertFalse(rsa1 != rsa2)
        self.assertTrue(rsa1 != rsa3)
        self.assertTrue(rsa1 != dsa)
        self.assertTrue(rsa1 != object)
        self.assertTrue(rsa1 != None)

    def test_dataError(self):
        """
        The L{keys.Key.data} method raises RuntimeError for bad keys.
        """
        badKey = keys.Key(b"")
        self.assertRaises(RuntimeError, badKey.data)

    def test_fingerprintdefault(self):
        """
        Test that the fingerprint method returns fingerprint in
        L{FingerprintFormats.MD5-HEX} format by default.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).fingerprint(),
            "85:25:04:32:58:55:96:9f:57:ee:fb:a8:1a:ea:69:da",
        )
        self.assertEqual(
            keys.Key(self.dsaObj).fingerprint(),
            "63:15:b3:0e:e6:4f:50:de:91:48:3d:01:6b:b3:13:c1",
        )

    def test_fingerprint_md5_hex(self):
        """
        fingerprint method generates key fingerprint in
        L{FingerprintFormats.MD5-HEX} format if explicitly specified.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).fingerprint(keys.FingerprintFormats.MD5_HEX),
            "85:25:04:32:58:55:96:9f:57:ee:fb:a8:1a:ea:69:da",
        )
        self.assertEqual(
            keys.Key(self.dsaObj).fingerprint(keys.FingerprintFormats.MD5_HEX),
            "63:15:b3:0e:e6:4f:50:de:91:48:3d:01:6b:b3:13:c1",
        )

    def test_fingerprintsha256(self):
        """
        fingerprint method generates key fingerprint in
        L{FingerprintFormats.SHA256-BASE64} format if explicitly specified.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).fingerprint(keys.FingerprintFormats.SHA256_BASE64),
            "FBTCOoknq0mHy+kpfnY9tDdcAJuWtCpuQMaV3EsvbUI=",
        )
        self.assertEqual(
            keys.Key(self.dsaObj).fingerprint(keys.FingerprintFormats.SHA256_BASE64),
            "Wz5o2YbKyxOEcJn1au/UaALSVruUzfz0vaLI1xiIGyY=",
        )

    def test_fingerprintBadFormat(self):
        """
        A C{BadFingerPrintFormat} error is raised when unsupported
        formats are requested.
        """
        with self.assertRaises(keys.BadFingerPrintFormat) as em:
            keys.Key(self.rsaObj).fingerprint("sha256-base")
        self.assertEqual(
            "Unsupported fingerprint format: sha256-base", em.exception.args[0]
        )

    def test_type(self):
        """
        Test that the type method returns the correct type for an object.
        """
        self.assertEqual(keys.Key(self.rsaObj).type(), "RSA")
        self.assertEqual(keys.Key(self.rsaObj).sshType(), b"ssh-rsa")
        self.assertEqual(keys.Key(self.dsaObj).type(), "DSA")
        self.assertEqual(keys.Key(self.dsaObj).sshType(), b"ssh-dss")
        self.assertEqual(keys.Key(self.ecObj).type(), "EC")
        self.assertEqual(
            keys.Key(self.ecObj).sshType(), keydata.ECDatanistp256["curve"]
        )
        if ED25519_SUPPORTED:
            self.assertEqual(keys.Key(self.ed25519Obj).type(), "Ed25519")
            self.assertEqual(keys.Key(self.ed25519Obj).sshType(), b"ssh-ed25519")
        self.assertRaises(RuntimeError, keys.Key(None).type)
        self.assertRaises(RuntimeError, keys.Key(None).sshType)
        self.assertRaises(RuntimeError, keys.Key(self).type)
        self.assertRaises(RuntimeError, keys.Key(self).sshType)

    def test_supportedSignatureAlgorithms(self):
        """
        L{keys.Key.supportedSignatureAlgorithms} returns the appropriate
        public key signature algorithms for each key type.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).supportedSignatureAlgorithms(),
            [b"rsa-sha2-512", b"rsa-sha2-256", b"ssh-rsa"],
        )
        self.assertEqual(
            keys.Key(self.dsaObj).supportedSignatureAlgorithms(), [b"ssh-dss"]
        )
        self.assertEqual(
            keys.Key(self.ecObj).supportedSignatureAlgorithms(),
            [b"ecdsa-sha2-nistp256"],
        )
        if ED25519_SUPPORTED:
            self.assertEqual(
                keys.Key(self.ed25519Obj).supportedSignatureAlgorithms(),
                [b"ssh-ed25519"],
            )
        self.assertRaises(RuntimeError, keys.Key(None).supportedSignatureAlgorithms)
        self.assertRaises(RuntimeError, keys.Key(self).supportedSignatureAlgorithms)

    def test_fromBlobUnsupportedType(self):
        """
        A C{BadKeyError} error is raised whey the blob has an unsupported
        key type.
        """
        badBlob = common.NS(b"ssh-bad")

        self.assertRaises(keys.BadKeyError, keys.Key.fromString, badBlob)

    def test_fromBlobRSA(self):
        """
        A public RSA key is correctly generated from a public key blob.
        """
        rsaPublicData = {
            "n": keydata.RSAData["n"],
            "e": keydata.RSAData["e"],
        }
        rsaBlob = (
            common.NS(b"ssh-rsa")
            + common.MP(rsaPublicData["e"])
            + common.MP(rsaPublicData["n"])
        )

        rsaKey = keys.Key.fromString(rsaBlob)

        self.assertTrue(rsaKey.isPublic())
        self.assertEqual(rsaPublicData, rsaKey.data())

    def test_fromBlobDSA(self):
        """
        A public DSA key is correctly generated from a public key blob.
        """
        dsaPublicData = {
            "p": keydata.DSAData["p"],
            "q": keydata.DSAData["q"],
            "g": keydata.DSAData["g"],
            "y": keydata.DSAData["y"],
        }
        dsaBlob = (
            common.NS(b"ssh-dss")
            + common.MP(dsaPublicData["p"])
            + common.MP(dsaPublicData["q"])
            + common.MP(dsaPublicData["g"])
            + common.MP(dsaPublicData["y"])
        )

        dsaKey = keys.Key.fromString(dsaBlob)

        self.assertTrue(dsaKey.isPublic())
        self.assertEqual(dsaPublicData, dsaKey.data())

    def test_fromBlobECDSA(self):
        """
        Key.fromString generates ECDSA keys from blobs.
        """
        from cryptography import utils

        ecPublicData = {
            "x": keydata.ECDatanistp256["x"],
            "y": keydata.ECDatanistp256["y"],
            "curve": keydata.ECDatanistp256["curve"],
        }

        ecblob = (
            common.NS(ecPublicData["curve"])
            + common.NS(ecPublicData["curve"][-8:])
            + common.NS(
                b"\x04"
                + utils.int_to_bytes(ecPublicData["x"], 32)
                + utils.int_to_bytes(ecPublicData["y"], 32)
            )
        )

        eckey = keys.Key.fromString(ecblob)
        self.assertTrue(eckey.isPublic())
        self.assertEqual(ecPublicData, eckey.data())

    @skipWithoutEd25519
    def test_fromBlobEd25519(self):
        """
        A public Ed25519 key is correctly generated from a public key blob.
        """
        ed25519PublicData = {
            "a": keydata.Ed25519Data["a"],
        }

        ed25519Blob = common.NS(b"ssh-ed25519") + common.NS(ed25519PublicData["a"])

        ed25519Key = keys.Key.fromString(ed25519Blob)

        self.assertTrue(ed25519Key.isPublic())
        self.assertEqual(ed25519PublicData, ed25519Key.data())

    def test_fromPrivateBlobUnsupportedType(self):
        """
        C{BadKeyError} is raised when loading a private blob with an
        unsupported type.
        """
        badBlob = common.NS(b"ssh-bad")

        self.assertRaises(keys.BadKeyError, keys.Key._fromString_PRIVATE_BLOB, badBlob)

    def test_fromPrivateBlobRSA(self):
        """
        A private RSA key is correctly generated from a private key blob.
        """
        rsaBlob = (
            common.NS(b"ssh-rsa")
            + common.MP(keydata.RSAData["n"])
            + common.MP(keydata.RSAData["e"])
            + common.MP(keydata.RSAData["d"])
            + common.MP(keydata.RSAData["u"])
            + common.MP(keydata.RSAData["p"])
            + common.MP(keydata.RSAData["q"])
        )

        rsaKey = keys.Key._fromString_PRIVATE_BLOB(rsaBlob)

        self.assertFalse(rsaKey.isPublic())
        self.assertEqual(keydata.RSAData, rsaKey.data())
        self.assertEqual(
            rsaKey, keys.Key._fromString_PRIVATE_BLOB(rsaKey.privateBlob())
        )

    def test_fromPrivateBlobDSA(self):
        """
        A private DSA key is correctly generated from a private key blob.
        """
        dsaBlob = (
            common.NS(b"ssh-dss")
            + common.MP(keydata.DSAData["p"])
            + common.MP(keydata.DSAData["q"])
            + common.MP(keydata.DSAData["g"])
            + common.MP(keydata.DSAData["y"])
            + common.MP(keydata.DSAData["x"])
        )

        dsaKey = keys.Key._fromString_PRIVATE_BLOB(dsaBlob)

        self.assertFalse(dsaKey.isPublic())
        self.assertEqual(keydata.DSAData, dsaKey.data())
        self.assertEqual(
            dsaKey, keys.Key._fromString_PRIVATE_BLOB(dsaKey.privateBlob())
        )

    def test_fromPrivateBlobECDSA(self):
        """
        A private EC key is correctly generated from a private key blob.
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        publicNumbers = ec.EllipticCurvePublicNumbers(
            x=keydata.ECDatanistp256["x"],
            y=keydata.ECDatanistp256["y"],
            curve=ec.SECP256R1(),
        )
        ecblob = (
            common.NS(keydata.ECDatanistp256["curve"])
            + common.NS(keydata.ECDatanistp256["curve"][-8:])
            + common.NS(
                publicNumbers.public_key(default_backend()).public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
            )
            + common.MP(keydata.ECDatanistp256["privateValue"])
        )

        eckey = keys.Key._fromString_PRIVATE_BLOB(ecblob)

        self.assertFalse(eckey.isPublic())
        self.assertEqual(keydata.ECDatanistp256, eckey.data())
        self.assertEqual(eckey, keys.Key._fromString_PRIVATE_BLOB(eckey.privateBlob()))

    @skipWithoutEd25519
    def test_fromPrivateBlobEd25519(self):
        """
        A private Ed25519 key is correctly generated from a private key blob.
        """
        ed25519Blob = (
            common.NS(b"ssh-ed25519")
            + common.NS(keydata.Ed25519Data["a"])
            + common.NS(keydata.Ed25519Data["k"] + keydata.Ed25519Data["a"])
        )

        ed25519Key = keys.Key._fromString_PRIVATE_BLOB(ed25519Blob)

        self.assertFalse(ed25519Key.isPublic())
        self.assertEqual(keydata.Ed25519Data, ed25519Key.data())
        self.assertEqual(
            ed25519Key, keys.Key._fromString_PRIVATE_BLOB(ed25519Key.privateBlob())
        )

    def test_blobRSA(self):
        """
        Return the over-the-wire SSH format of the RSA public key.
        """
        self.assertEqual(
            keys.Key(self.rsaObj).blob(),
            common.NS(b"ssh-rsa")
            + common.MP(self.rsaObj.private_numbers().public_numbers.e)
            + common.MP(self.rsaObj.private_numbers().public_numbers.n),
        )

    def test_blobDSA(self):
        """
        Return the over-the-wire SSH format of the DSA public key.
        """
        publicNumbers = self.dsaObj.private_numbers().public_numbers

        self.assertEqual(
            keys.Key(self.dsaObj).blob(),
            common.NS(b"ssh-dss")
            + common.MP(publicNumbers.parameter_numbers.p)
            + common.MP(publicNumbers.parameter_numbers.q)
            + common.MP(publicNumbers.parameter_numbers.g)
            + common.MP(publicNumbers.y),
        )

    def test_blobEC(self):
        """
        Return the over-the-wire SSH format of the EC public key.
        """
        from cryptography import utils

        byteLength = (self.ecObj.curve.key_size + 7) // 8
        self.assertEqual(
            keys.Key(self.ecObj).blob(),
            common.NS(keydata.ECDatanistp256["curve"])
            + common.NS(keydata.ECDatanistp256["curve"][-8:])
            + common.NS(
                b"\x04"
                + utils.int_to_bytes(
                    self.ecObj.private_numbers().public_numbers.x, byteLength
                )
                + utils.int_to_bytes(
                    self.ecObj.private_numbers().public_numbers.y, byteLength
                )
            ),
        )

    @skipWithoutEd25519
    def test_blobEd25519(self):
        """
        Return the over-the-wire SSH format of the Ed25519 public key.
        """
        from cryptography.hazmat.primitives import serialization

        publicBytes = self.ed25519Obj.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

        self.assertEqual(
            keys.Key(self.ed25519Obj).blob(),
            common.NS(b"ssh-ed25519") + common.NS(publicBytes),
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
        numbers = self.rsaObj.private_numbers()
        self.assertEqual(
            keys.Key(self.rsaObj).privateBlob(),
            common.NS(b"ssh-rsa")
            + common.MP(numbers.public_numbers.n)
            + common.MP(numbers.public_numbers.e)
            + common.MP(numbers.d)
            + common.MP(numbers.iqmp)
            + common.MP(numbers.p)
            + common.MP(numbers.q),
        )

    def test_privateBlobDSA(self):
        """
        L{keys.Key.privateBlob} returns the SSH protocol-level format of a DSA
        private key.
        """
        publicNumbers = self.dsaObj.private_numbers().public_numbers

        self.assertEqual(
            keys.Key(self.dsaObj).privateBlob(),
            common.NS(b"ssh-dss")
            + common.MP(publicNumbers.parameter_numbers.p)
            + common.MP(publicNumbers.parameter_numbers.q)
            + common.MP(publicNumbers.parameter_numbers.g)
            + common.MP(publicNumbers.y)
            + common.MP(self.dsaObj.private_numbers().x),
        )

    def test_privateBlobEC(self):
        """
        L{keys.Key.privateBlob} returns the SSH ptotocol-level format of EC
        private key.
        """
        from cryptography.hazmat.primitives import serialization

        self.assertEqual(
            keys.Key(self.ecObj).privateBlob(),
            common.NS(keydata.ECDatanistp256["curve"])
            + common.NS(keydata.ECDatanistp256["curve"][-8:])
            + common.NS(
                self.ecObj.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
            )
            + common.MP(self.ecObj.private_numbers().private_value),
        )

    @skipWithoutEd25519
    def test_privateBlobEd25519(self):
        """
        L{keys.Key.privateBlob} returns the SSH protocol-level format of an
        Ed25519 private key.
        """
        from cryptography.hazmat.primitives import serialization

        publicBytes = self.ed25519Obj.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        privateBytes = self.ed25519Obj.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )

        self.assertEqual(
            keys.Key(self.ed25519Obj).privateBlob(),
            common.NS(b"ssh-ed25519")
            + common.NS(publicBytes)
            + common.NS(privateBytes + publicBytes),
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
        self.assertEqual(key.toString("openssh"), keydata.privateRSA_openssh)
        self.assertEqual(
            key.toString("openssh", passphrase=b"encrypted"),
            keydata.privateRSA_openssh_encrypted,
        )
        self.assertEqual(
            key.public().toString("openssh"), keydata.publicRSA_openssh[:-8]
        )  # no comment
        self.assertEqual(
            key.public().toString("openssh", comment=b"comment"),
            keydata.publicRSA_openssh,
        )

    def test_toOpenSSHRSA_v1_format(self):
        """
        L{keys.Key.toString} serializes an RSA key in OpenSSH's v1 format.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        new_key_data = key.toString("openssh", subtype="v1")
        new_enc_key_data = key.toString("openssh", subtype="v1", passphrase="encrypted")
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_key_data.splitlines()[0]
        )
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_enc_key_data.splitlines()[0]
        )
        self.assertEqual(key, keys.Key.fromString(new_key_data))
        self.assertEqual(
            key, keys.Key.fromString(new_enc_key_data, passphrase="encrypted")
        )

    def test_toOpenSSHDSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in OpenSSH format.
        """
        key = keys.Key.fromString(keydata.privateDSA_lsh)
        self.assertEqual(key.toString("openssh"), keydata.privateDSA_openssh)
        self.assertEqual(
            key.public().toString("openssh", comment=b"comment"),
            keydata.publicDSA_openssh,
        )
        self.assertEqual(
            key.public().toString("openssh"), keydata.publicDSA_openssh[:-8]
        )  # no comment

    def test_toOpenSSHDSA_v1_format(self):
        """
        L{keys.Key.toString} serializes a DSA key in OpenSSH's v1 format.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        new_key_data = key.toString("openssh", subtype="v1")
        new_enc_key_data = key.toString("openssh", subtype="v1", passphrase="encrypted")
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_key_data.splitlines()[0]
        )
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_enc_key_data.splitlines()[0]
        )
        self.assertEqual(key, keys.Key.fromString(new_key_data))
        self.assertEqual(
            key, keys.Key.fromString(new_enc_key_data, passphrase="encrypted")
        )

    def test_toOpenSSHECDSA(self):
        """
        L{keys.Key.toString} serializes an ECDSA key in OpenSSH format.
        """
        key = keys.Key.fromString(keydata.privateECDSA_openssh)
        self.assertEqual(
            key.public().toString("openssh", comment=b"comment"),
            keydata.publicECDSA_openssh,
        )
        self.assertEqual(
            key.public().toString("openssh"), keydata.publicECDSA_openssh[:-8]
        )  # no comment

    def test_toOpenSSHECDSA_v1_format(self):
        """
        L{keys.Key.toString} serializes an ECDSA key in OpenSSH's v1 format.
        """
        key = keys.Key.fromString(keydata.privateECDSA_openssh)
        new_key_data = key.toString("openssh", subtype="v1")
        new_enc_key_data = key.toString("openssh", subtype="v1", passphrase="encrypted")
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_key_data.splitlines()[0]
        )
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_enc_key_data.splitlines()[0]
        )
        self.assertEqual(key, keys.Key.fromString(new_key_data))
        self.assertEqual(
            key, keys.Key.fromString(new_enc_key_data, passphrase="encrypted")
        )

    @skipWithoutEd25519
    def test_toOpenSSHEd25519(self):
        """
        L{keys.Key.toString} serializes an Ed25519 key in OpenSSH's v1 format.
        """
        key = keys.Key.fromString(keydata.privateEd25519_openssh_new)
        new_key_data = key.toString("openssh")
        new_enc_key_data = key.toString("openssh", passphrase="encrypted")
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_key_data.splitlines()[0]
        )
        self.assertEqual(
            b"-----BEGIN OPENSSH PRIVATE KEY-----", new_enc_key_data.splitlines()[0]
        )
        self.assertEqual(key, keys.Key.fromString(new_key_data))
        self.assertEqual(
            key, keys.Key.fromString(new_enc_key_data, passphrase="encrypted")
        )
        self.assertEqual(new_key_data, key.toString("openssh", subtype="v1"))

    @skipWithoutEd25519
    def test_toOpenSSHEd25519_PEM_format(self):
        """
        L{keys.Key.toString} refuses to serialize an Ed25519 key in
        OpenSSH's old PEM format, as no encoding of Ed25519 is defined for
        that format.
        """
        key = keys.Key.fromString(keydata.privateEd25519_openssh_new)
        self.assertRaises(ValueError, key.toString, "openssh", subtype="PEM")

    def test_toLSHRSA(self):
        """
        L{keys.Key.toString} serializes an RSA key in LSH format.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertEqual(key.toString("lsh"), keydata.privateRSA_lsh)
        self.assertEqual(key.public().toString("lsh"), keydata.publicRSA_lsh)

    def test_toLSHDSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in LSH format.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        self.assertEqual(key.toString("lsh"), keydata.privateDSA_lsh)
        self.assertEqual(key.public().toString("lsh"), keydata.publicDSA_lsh)

    def test_toAgentv3RSA(self):
        """
        L{keys.Key.toString} serializes an RSA key in Agent v3 format.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertEqual(key.toString("agentv3"), keydata.privateRSA_agentv3)

    def test_toAgentv3DSA(self):
        """
        L{keys.Key.toString} serializes a DSA key in Agent v3 format.
        """
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        self.assertEqual(key.toString("agentv3"), keydata.privateDSA_agentv3)

    def test_toStringNormalizesUnicodePassphrase(self):
        """
        L{keys.Key.toString} applies Normalization Form KC to Unicode
        passphrases.
        """
        key = keys.Key(self.rsaObj)
        key_data = key.toString("openssh", passphrase="verschlu\u0308sselt")
        self.assertEqual(
            keys.Key.fromString(key_data, passphrase="verschl\u00FCsselt".encode()),
            key,
        )
        # U+FFFF is a "noncharacter" and guaranteed to have General_Category
        # Cn (Unassigned).
        self.assertRaises(
            keys.PassphraseNormalizationError,
            key.toString,
            "openssh",
            passphrase="unassigned \uFFFF",
        )

    def test_toStringErrors(self):
        """
        L{keys.Key.toString} raises L{keys.BadKeyError} when passed an invalid
        format type.
        """
        self.assertRaises(keys.BadKeyError, keys.Key(self.rsaObj).toString, "bad_type")

    def test_signAndVerifyRSA(self):
        """
        Signed data can be verified using RSA (with SHA-1, the default).
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        signature = key.sign(data)
        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))
        # Verify that the signature uses SHA-1.
        signatureType, signature = common.getNS(signature)
        self.assertEqual(signatureType, b"ssh-rsa")
        self.assertIsNone(
            key._keyObject.public_key().verify(
                common.getNS(signature)[0], data, padding.PKCS1v15(), hashes.SHA1()
            )
        )

    def test_signAndVerifyRSASHA256(self):
        """
        Signed data can be verified using RSA with SHA-256.
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        signature = key.sign(data, signatureType=b"rsa-sha2-256")
        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))
        # Verify that the signature uses SHA-256.
        signatureType, signature = common.getNS(signature)
        self.assertEqual(signatureType, b"rsa-sha2-256")
        self.assertIsNone(
            key._keyObject.public_key().verify(
                common.getNS(signature)[0], data, padding.PKCS1v15(), hashes.SHA256()
            )
        )

    def test_signAndVerifyRSASHA512(self):
        """
        Signed data can be verified using RSA with SHA-512.
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        signature = key.sign(data, signatureType=b"rsa-sha2-512")
        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))
        # Verify that the signature uses SHA-512.
        signatureType, signature = common.getNS(signature)
        self.assertEqual(signatureType, b"rsa-sha2-512")
        self.assertIsNone(
            key._keyObject.public_key().verify(
                common.getNS(signature)[0], data, padding.PKCS1v15(), hashes.SHA512()
            )
        )

    def test_signAndVerifyDSA(self):
        """
        Signed data can be verified using DSA.
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateDSA_openssh)
        signature = key.sign(data)
        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))

    def test_signAndVerifyEC(self):
        """
        Signed data can be verified using EC.
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateECDSA_openssh)
        signature = key.sign(data)

        key384 = keys.Key.fromString(keydata.privateECDSA_openssh384)
        signature384 = key384.sign(data)

        key521 = keys.Key.fromString(keydata.privateECDSA_openssh521)
        signature521 = key521.sign(data)

        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))
        self.assertTrue(key384.public().verify(signature384, data))
        self.assertTrue(key384.verify(signature384, data))
        self.assertTrue(key521.public().verify(signature521, data))
        self.assertTrue(key521.verify(signature521, data))

    @skipWithoutEd25519
    def test_signAndVerifyEd25519(self):
        """
        Signed data can be verified using Ed25519.
        """
        data = b"some-data"
        key = keys.Key.fromString(keydata.privateEd25519_openssh_new)
        signature = key.sign(data)
        self.assertTrue(key.public().verify(signature, data))
        self.assertTrue(key.verify(signature, data))

    def test_signWithWrongAlgorithm(self):
        """
        L{keys.Key.sign} raises L{keys.BadSignatureAlgorithmError} when
        asked to sign with a public key algorithm that doesn't make sense
        with the given key.
        """
        key = keys.Key.fromString(keydata.privateRSA_openssh)
        self.assertRaises(
            keys.BadSignatureAlgorithmError,
            key.sign,
            b"some data",
            signatureType=b"ssh-dss",
        )
        key = keys.Key.fromString(keydata.privateECDSA_openssh)
        self.assertRaises(
            keys.BadSignatureAlgorithmError,
            key.sign,
            b"some data",
            signatureType=b"ssh-dss",
        )

    def test_verifyRSA(self):
        """
        A known-good RSA signature verifies successfully.
        """
        key = keys.Key.fromString(keydata.publicRSA_openssh)
        self.assertTrue(key.verify(self.rsaSignature, b""))
        self.assertFalse(key.verify(self.rsaSignature, b"a"))
        self.assertFalse(key.verify(self.dsaSignature, b""))

    def test_verifyDSA(self):
        """
        A known-good DSA signature verifies successfully.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        self.assertTrue(key.verify(self.dsaSignature, b""))
        self.assertFalse(key.verify(self.dsaSignature, b"a"))
        self.assertFalse(key.verify(self.rsaSignature, b""))

    def test_verifyDSANoPrefix(self):
        """
        Some commercial SSH servers send DSA keys as 2 20-byte numbers;
        they are still verified as valid keys.
        """
        key = keys.Key.fromString(keydata.publicDSA_openssh)
        self.assertTrue(key.verify(self.dsaSignature[-40:], b""))

    def test_reprPrivateRSA(self):
        """
        The repr of a L{keys.Key} contains all of the RSA components for an RSA
        private key.
        """
        self.assertEqual(
            repr(keys.Key(self.rsaObj)),
            """<RSA Private Key (2048 bits)
attr d:
\t21:4c:08:66:a2:28:d5:b4:fb:8e:0f:72:1b:85:09:
\t00:b9:f2:4e:37:f0:1c:57:4b:e3:51:7f:9e:23:a7:
\te4:3a:98:55:1b:ea:8b:7a:98:1e:bc:d8:ba:b1:f9:
\t89:12:18:60:ac:e8:cc:0b:4e:09:5a:40:6a:ba:2f:
\t99:f8:b3:24:60:84:b9:ce:69:95:9a:f9:e2:fc:1f:
\t51:4d:27:15:db:2b:27:ad:ef:b4:69:ac:be:7d:10:
\teb:86:47:70:73:b4:00:87:95:15:3b:37:f9:e7:14:
\te7:80:bb:68:1e:1b:e6:dd:bb:73:63:b9:67:e6:b2:
\t27:7f:cf:cf:30:9b:c2:98:fd:d9:18:36:2f:36:2e:
\tf1:3d:81:7a:9f:e1:03:2d:47:db:34:51:62:39:dd:
\t4f:e9:ac:a8:8b:d9:d6:f3:84:c4:17:b9:71:9d:06:
\t08:42:78:4d:bb:c5:2a:f4:c3:58:cd:55:2b:ed:be:
\t33:5f:04:ea:7b:e6:04:24:63:f2:2d:d7:3d:1b:6c:
\td5:9c:63:43:2f:92:88:8d:3e:6e:da:18:37:d8:0f:
\t25:67:89:1d:b9:46:34:5e:c9:ce:c4:8b:ed:92:5a:
\t33:07:0f:df:86:08:f9:92:e9:db:eb:38:08:36:c9:
\tcd:cd:0a:01:48:5b:39:3e:7a:ca:c6:80:a9:dc:d4:
\t39
attr e:
\t01:00:01
attr n:
\t00:d5:6a:ac:78:23:d6:d6:1b:ec:25:a1:50:c4:77:
\t63:50:84:45:01:55:42:14:2a:2a:e0:d0:60:ee:d4:
\te9:a3:ad:4a:fa:39:06:5e:84:55:75:5f:00:36:bf:
\t6f:aa:2a:3f:83:26:37:c1:69:2e:5b:fd:f0:f3:d2:
\t7d:d6:98:cd:3a:40:78:d5:ca:a8:18:c0:11:93:24:
\t09:0c:81:4c:8f:f7:9c:ed:13:16:6a:a4:04:e9:49:
\t77:c3:e4:55:64:b3:79:68:9e:2c:08:eb:ac:e8:04:
\t2d:21:77:05:a7:8e:ef:53:30:0d:a5:e5:bb:3d:6a:
\te2:09:36:6f:fd:34:d3:7d:6f:46:ff:87:da:a9:29:
\t27:aa:ff:ad:f5:85:e6:3e:1a:b8:7a:1d:4a:b1:ea:
\tc0:5a:f7:30:df:1f:c2:a4:e4:ef:3f:91:49:96:40:
\td5:19:77:2d:37:c3:5e:ec:9d:a6:3a:44:a5:c2:a4:
\t29:dd:d5:ba:9c:3d:45:b3:c6:2c:18:64:d5:ba:3d:
\tdf:ab:7f:cd:42:ac:a7:f1:18:0b:a0:58:15:62:0b:
\ta4:2a:6e:43:c3:e4:04:9f:35:a3:47:8e:46:ed:33:
\ta5:65:bd:bc:3b:29:6e:02:0b:57:df:74:e8:13:b4:
\t37:35:7e:83:5f:20:26:60:a6:dc:ad:8b:c6:6c:79:
\t98:f7
attr p:
\t00:d9:70:06:d8:e2:bc:d4:78:91:50:94:d4:c1:1b:
\t89:38:6c:46:64:5a:51:a0:9a:07:3d:48:8f:03:51:
\tcc:6b:12:8e:7d:1a:b1:65:e7:71:75:39:e0:32:05:
\t75:8d:18:4c:af:93:b1:49:b1:66:5f:78:62:7a:d1:
\t0c:ca:e6:4d:43:b3:9c:f4:6b:7d:e6:0c:98:dc:cf:
\t21:62:8e:d5:2e:12:de:04:ae:d7:24:6e:83:31:a2:
\t15:a2:44:3d:22:a9:62:26:22:b9:b2:ed:54:0a:9d:
\t08:83:a7:07:0d:ff:19:18:8e:d8:ab:1d:da:48:9c:
\t31:68:11:a1:66:6d:e3:d8:1d
attr q:
\t00:fb:44:17:8b:a4:36:be:1e:37:1d:a7:f6:61:6c:
\t04:c4:aa:dd:78:3e:07:8c:1e:33:02:ae:03:14:87:
\t83:7a:e5:9e:7d:08:67:a8:f2:aa:bf:12:70:cf:72:
\ta9:a7:c7:0b:1d:88:d5:20:fd:9c:63:ca:47:30:55:
\t4e:8b:c4:cf:f4:7f:16:a4:92:12:74:a1:09:c2:c4:
\t6e:9c:8c:33:ef:a5:e5:f7:e0:2b:ad:4f:5c:11:aa:
\t1a:84:37:5b:fd:7a:ea:c3:cd:7c:b0:c8:e4:1f:54:
\t63:b5:c7:af:df:f4:09:a7:fc:c7:25:fc:5c:e9:91:
\td7:92:c5:98:1e:56:d3:b1:23
attr u:
\t00:85:4b:1b:7a:9b:12:10:37:9e:1f:ad:5e:da:fe:
\tc6:96:fe:df:35:6b:b9:34:e2:16:97:92:26:09:bd:
\tbd:70:20:03:a7:35:bd:2d:1b:a0:d2:07:47:2b:d4:
\tde:a8:a8:07:07:1b:b8:04:20:a7:27:41:3c:6c:39:
\t39:e9:41:ce:e7:17:1d:d1:4c:5c:bc:3d:d2:26:26:
\tfe:6a:d6:fd:48:72:ae:46:fa:7b:c3:d3:19:60:44:
\t1d:a5:13:a7:80:f5:63:29:d4:7a:5d:06:07:16:5d:
\tf6:8b:3d:cb:64:3a:e2:84:5a:4d:8c:06:2d:2d:9d:
\t1c:eb:83:4c:78:3d:79:54:ce>""",
        )

    def test_reprPublicRSA(self):
        """
        The repr of a L{keys.Key} contains all of the RSA components for an RSA
        public key.
        """
        self.assertEqual(
            repr(keys.Key(self.rsaObj).public()),
            """<RSA Public Key (2048 bits)
attr e:
\t01:00:01
attr n:
\t00:d5:6a:ac:78:23:d6:d6:1b:ec:25:a1:50:c4:77:
\t63:50:84:45:01:55:42:14:2a:2a:e0:d0:60:ee:d4:
\te9:a3:ad:4a:fa:39:06:5e:84:55:75:5f:00:36:bf:
\t6f:aa:2a:3f:83:26:37:c1:69:2e:5b:fd:f0:f3:d2:
\t7d:d6:98:cd:3a:40:78:d5:ca:a8:18:c0:11:93:24:
\t09:0c:81:4c:8f:f7:9c:ed:13:16:6a:a4:04:e9:49:
\t77:c3:e4:55:64:b3:79:68:9e:2c:08:eb:ac:e8:04:
\t2d:21:77:05:a7:8e:ef:53:30:0d:a5:e5:bb:3d:6a:
\te2:09:36:6f:fd:34:d3:7d:6f:46:ff:87:da:a9:29:
\t27:aa:ff:ad:f5:85:e6:3e:1a:b8:7a:1d:4a:b1:ea:
\tc0:5a:f7:30:df:1f:c2:a4:e4:ef:3f:91:49:96:40:
\td5:19:77:2d:37:c3:5e:ec:9d:a6:3a:44:a5:c2:a4:
\t29:dd:d5:ba:9c:3d:45:b3:c6:2c:18:64:d5:ba:3d:
\tdf:ab:7f:cd:42:ac:a7:f1:18:0b:a0:58:15:62:0b:
\ta4:2a:6e:43:c3:e4:04:9f:35:a3:47:8e:46:ed:33:
\ta5:65:bd:bc:3b:29:6e:02:0b:57:df:74:e8:13:b4:
\t37:35:7e:83:5f:20:26:60:a6:dc:ad:8b:c6:6c:79:
\t98:f7>""",
        )

    def test_reprPublicECDSA(self):
        """
        The repr of a L{keys.Key} contains all the OpenSSH format for an ECDSA
        public key.
        """
        self.assertEqual(
            repr(keys.Key(self.ecObj).public()),
            dedent(
                """\
                <Elliptic Curve Public Key (256 bits)
                curve:
                \tecdsa-sha2-nistp256
                x:
                \t{x}
                y:
                \t{y}>
                """
            ).format(**keydata.ECDatanistp256),
        )

    def test_reprPrivateECDSA(self):
        """
        The repr of a L{keys.Key} contains all the OpenSSH format for an ECDSA
        private key.
        """
        self.assertEqual(
            repr(keys.Key(self.ecObj)),
            dedent(
                """\
                <Elliptic Curve Private Key (256 bits)
                curve:
                \tecdsa-sha2-nistp256
                privateValue:
                \t{privateValue}
                x:
                \t{x}
                y:
                \t{y}>
                """
            ).format(**keydata.ECDatanistp256),
        )

    @skipWithoutEd25519
    def test_reprPublicEd25519(self):
        """
        The repr of a L{keys.Key} contains all the OpenSSH format for an
        Ed25519 public key.
        """
        self.assertEqual(
            repr(keys.Key(self.ed25519Obj).public()),
            dedent(
                """\
                <Ed25519 Public Key (256 bits)
                attr a:
                \tf1:16:d1:15:4a:1e:15:0e:19:5e:19:46:b5:f2:44:
                \t0d:b2:52:a0:ae:2a:6b:23:13:73:45:fd:40:d9:57:
                \t7b:8b>"""
            ),
        )

    @skipWithoutEd25519
    def test_reprPrivateEd25519(self):
        """
        The repr of a L{keys.Key} contains all the OpenSSH format for an
        Ed25519 private key.
        """
        self.assertEqual(
            repr(keys.Key(self.ed25519Obj)),
            dedent(
                """\
                <Ed25519 Private Key (256 bits)
                attr a:
                \tf1:16:d1:15:4a:1e:15:0e:19:5e:19:46:b5:f2:44:
                \t0d:b2:52:a0:ae:2a:6b:23:13:73:45:fd:40:d9:57:
                \t7b:8b
                attr k:
                \t37:2f:25:da:8d:d4:a8:9a:78:7c:61:f0:98:01:c6:
                \tf4:5e:6d:67:05:69:31:37:4c:69:0d:05:55:bb:c9:
                \t44:58>"""
            ),
        )


class PyNaClKeyTests(KeyTests):
    """
    Key tests, but forcing the use of C{PyNaCl}.
    """

    if cryptography is None:
        skip = skipCryptography
    if _keys_pynacl is None:
        skip = "Cannot run without PyNaCl"

    def setUp(self):
        super().setUp()
        self.patch(keys, "Ed25519PublicKey", _keys_pynacl.Ed25519PublicKey)
        self.patch(keys, "Ed25519PrivateKey", _keys_pynacl.Ed25519PrivateKey)

    def test_naclPrivateBytes(self):
        """
        L{_keys_pynacl.Ed25519PrivateKey.private_bytes} and
        L{_keys_pynacl.Ed25519PrivateKey.from_private_bytes} round-trip.
        """
        from cryptography.hazmat.primitives import serialization

        key = _keys_pynacl.Ed25519PrivateKey.generate()
        key_bytes = key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        self.assertIsInstance(key_bytes, bytes)
        self.assertEqual(
            key, _keys_pynacl.Ed25519PrivateKey.from_private_bytes(key_bytes)
        )

    def test_naclPrivateBytesInvalidParameters(self):
        """
        L{_keys_pynacl.Ed25519PrivateKey.private_bytes} only accepts certain parameters.
        """
        from cryptography.hazmat.primitives import serialization

        key = _keys_pynacl.Ed25519PrivateKey.generate()
        self.assertRaises(
            ValueError,
            key.private_bytes,
            serialization.Encoding.PEM,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        self.assertRaises(
            ValueError,
            key.private_bytes,
            serialization.Encoding.Raw,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        self.assertRaises(
            ValueError,
            key.private_bytes,
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.BestAvailableEncryption(b"password"),
        )

    def test_naclPrivateHash(self):
        """
        L{_keys_pynacl.Ed25519PrivateKey.__hash__} allows instances to be hashed.
        """
        key = _keys_pynacl.Ed25519PrivateKey.generate()
        d = {key: True}
        self.assertTrue(d[key])

    def test_naclPrivateEquality(self):
        """
        L{_keys_pynacl.Ed25519PrivateKey} implements equality test methods.
        """
        key1 = _keys_pynacl.Ed25519PrivateKey.generate()
        key2 = _keys_pynacl.Ed25519PrivateKey.generate()
        self.assertEqual(key1, key1)
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key1, bytes(key1))

    def test_naclPublicBytes(self):
        """
        L{_keys_pynacl.Ed25519PublicKey.public_bytes} and
        L{_keys_pynacl.Ed25519PublicKey.from_public_bytes} round-trip.
        """
        from cryptography.hazmat.primitives import serialization

        key = _keys_pynacl.Ed25519PrivateKey.generate().public_key()
        key_bytes = key.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.assertIsInstance(key_bytes, bytes)
        self.assertEqual(
            key, _keys_pynacl.Ed25519PublicKey.from_public_bytes(key_bytes)
        )

    def test_naclPublicBytesInvalidParameters(self):
        """
        L{_keys_pynacl.Ed25519PublicKey.public_bytes} only accepts certain parameters.
        """
        from cryptography.hazmat.primitives import serialization

        key = _keys_pynacl.Ed25519PrivateKey.generate().public_key()
        self.assertRaises(
            ValueError,
            key.public_bytes,
            serialization.Encoding.PEM,
            serialization.PublicFormat.Raw,
        )
        self.assertRaises(
            ValueError,
            key.public_bytes,
            serialization.Encoding.Raw,
            serialization.PublicFormat.PKCS1,
        )

    def test_naclPublicHash(self):
        """
        L{_keys_pynacl.Ed25519PublicKey.__hash__} allows instances to be hashed.
        """
        key = _keys_pynacl.Ed25519PrivateKey.generate().public_key()
        d = {key: True}
        self.assertTrue(d[key])

    def test_naclPublicEquality(self):
        """
        L{_keys_pynacl.Ed25519PublicKey} implements equality test methods.
        """
        key1 = _keys_pynacl.Ed25519PrivateKey.generate().public_key()
        key2 = _keys_pynacl.Ed25519PrivateKey.generate().public_key()
        self.assertEqual(key1, key1)
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key1, bytes(key1))

    def test_naclVerify(self):
        """
        L{_keys_pynacl.Ed25519PublicKey.verify} raises appropriate exceptions.
        """
        key = _keys_pynacl.Ed25519PrivateKey.generate()
        self.assertIsInstance(key, keys.Ed25519PrivateKey)
        signature = key.sign(b"test data")
        self.assertIsNone(key.public_key().verify(signature, b"test data"))
        self.assertRaises(
            InvalidSignature, key.public_key().verify, signature, b"wrong data"
        )
        self.assertRaises(
            InvalidSignature, key.public_key().verify, b"0" * 64, b"test data"
        )


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

    def test_keySizeZero(self):
        """
        If the key generated by L{keys.getPersistentRSAKey} is set to None
        the key size should then become 0.
        """
        tempDir = FilePath(self.mktemp())
        keyFile = tempDir.child("mykey.pem")

        key = keys._getPersistentRSAKey(keyFile, keySize=512)
        key._keyObject = None
        self.assertEqual(key.size(), 0)
