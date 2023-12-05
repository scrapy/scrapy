# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.cred}'s implementation of CRAM-MD5.
"""


import hashlib
from binascii import hexlify
from hmac import HMAC

from twisted.cred.credentials import CramMD5Credentials, IUsernameHashedPassword
from twisted.trial.unittest import TestCase


class CramMD5CredentialsTests(TestCase):
    """
    Tests for L{CramMD5Credentials}.
    """

    def test_idempotentChallenge(self):
        """
        The same L{CramMD5Credentials} will always provide the same challenge,
        no matter how many times it is called.
        """
        c = CramMD5Credentials()
        chal = c.getChallenge()
        self.assertEqual(chal, c.getChallenge())

    def test_checkPassword(self):
        """
        When a valid response (which is a hex digest of the challenge that has
        been encrypted by the user's shared secret) is set on the
        L{CramMD5Credentials} that created the challenge, and C{checkPassword}
        is called with the user's shared secret, it will return L{True}.
        """
        c = CramMD5Credentials()
        chal = c.getChallenge()
        c.response = hexlify(HMAC(b"secret", chal, digestmod=hashlib.md5).digest())
        self.assertTrue(c.checkPassword(b"secret"))

    def test_noResponse(self):
        """
        When there is no response set, calling C{checkPassword} will return
        L{False}.
        """
        c = CramMD5Credentials()
        self.assertFalse(c.checkPassword(b"secret"))

    def test_wrongPassword(self):
        """
        When an invalid response is set on the L{CramMD5Credentials} (one that
        is not the hex digest of the challenge, encrypted with the user's shared
        secret) and C{checkPassword} is called with the user's correct shared
        secret, it will return L{False}.
        """
        c = CramMD5Credentials()
        chal = c.getChallenge()
        c.response = hexlify(
            HMAC(b"thewrongsecret", chal, digestmod=hashlib.md5).digest()
        )
        self.assertFalse(c.checkPassword(b"secret"))

    def test_setResponse(self):
        """
        When C{setResponse} is called with a string that is the username and
        the hashed challenge separated with a space, they will be set on the
        L{CramMD5Credentials}.
        """
        c = CramMD5Credentials()
        chal = c.getChallenge()
        c.setResponse(
            b" ".join(
                (
                    b"squirrel",
                    hexlify(HMAC(b"supersecret", chal, digestmod=hashlib.md5).digest()),
                )
            )
        )
        self.assertTrue(c.checkPassword(b"supersecret"))
        self.assertEqual(c.username, b"squirrel")

    def test_interface(self):
        """
        L{CramMD5Credentials} implements the L{IUsernameHashedPassword}
        interface.
        """
        self.assertTrue(IUsernameHashedPassword.implementedBy(CramMD5Credentials))
