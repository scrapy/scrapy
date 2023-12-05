# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for basic constructs of L{twisted.cred.credentials}.
"""


from twisted.cred.credentials import (
    IUsernameHashedPassword,
    IUsernamePassword,
    UsernamePassword,
)
from twisted.cred.test.test_cred import _uhpVersion
from twisted.trial.unittest import TestCase


class UsernamePasswordTests(TestCase):
    """
    Tests for L{UsernamePassword}.
    """

    def test_initialisation(self):
        """
        The initialisation of L{UsernamePassword} will set C{username} and
        C{password} on it.
        """
        creds = UsernamePassword(b"foo", b"bar")
        self.assertEqual(creds.username, b"foo")
        self.assertEqual(creds.password, b"bar")

    def test_correctPassword(self):
        """
        Calling C{checkPassword} on a L{UsernamePassword} will return L{True}
        when the password given is the password on the object.
        """
        creds = UsernamePassword(b"user", b"pass")
        self.assertTrue(creds.checkPassword(b"pass"))

    def test_wrongPassword(self):
        """
        Calling C{checkPassword} on a L{UsernamePassword} will return L{False}
        when the password given is NOT the password on the object.
        """
        creds = UsernamePassword(b"user", b"pass")
        self.assertFalse(creds.checkPassword(b"someotherpass"))

    def test_interface(self):
        """
        L{UsernamePassword} implements L{IUsernamePassword}.
        """
        self.assertTrue(IUsernamePassword.implementedBy(UsernamePassword))


class UsernameHashedPasswordTests(TestCase):
    """
    Tests for L{UsernameHashedPassword}.
    """

    def test_initialisation(self):
        """
        The initialisation of L{UsernameHashedPassword} will set C{username}
        and C{hashed} on it.
        """
        UsernameHashedPassword = self.getDeprecatedModuleAttribute(
            "twisted.cred.credentials", "UsernameHashedPassword", _uhpVersion
        )
        creds = UsernameHashedPassword(b"foo", b"bar")
        self.assertEqual(creds.username, b"foo")
        self.assertEqual(creds.hashed, b"bar")

    def test_correctPassword(self):
        """
        Calling C{checkPassword} on a L{UsernameHashedPassword} will return
        L{True} when the password given is the password on the object.
        """
        UsernameHashedPassword = self.getDeprecatedModuleAttribute(
            "twisted.cred.credentials", "UsernameHashedPassword", _uhpVersion
        )
        creds = UsernameHashedPassword(b"user", b"pass")
        self.assertTrue(creds.checkPassword(b"pass"))

    def test_wrongPassword(self):
        """
        Calling C{checkPassword} on a L{UsernameHashedPassword} will return
        L{False} when the password given is NOT the password on the object.
        """
        UsernameHashedPassword = self.getDeprecatedModuleAttribute(
            "twisted.cred.credentials", "UsernameHashedPassword", _uhpVersion
        )
        creds = UsernameHashedPassword(b"user", b"pass")
        self.assertFalse(creds.checkPassword(b"someotherpass"))

    def test_interface(self):
        """
        L{UsernameHashedPassword} implements L{IUsernameHashedPassword}.
        """
        UsernameHashedPassword = self.getDeprecatedModuleAttribute(
            "twisted.cred.credentials", "UsernameHashedPassword", _uhpVersion
        )
        self.assertTrue(IUsernameHashedPassword.implementedBy(UsernameHashedPassword))
