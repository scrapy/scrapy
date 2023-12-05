# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.protocols.jabber.jid}.
"""

from twisted.trial import unittest
from twisted.words.protocols.jabber import jid


class JIDParsingTests(unittest.TestCase):
    def test_parse(self):
        """
        Test different forms of JIDs.
        """
        # Basic forms
        self.assertEqual(jid.parse("user@host/resource"), ("user", "host", "resource"))
        self.assertEqual(jid.parse("user@host"), ("user", "host", None))
        self.assertEqual(jid.parse("host"), (None, "host", None))
        self.assertEqual(jid.parse("host/resource"), (None, "host", "resource"))

        # More interesting forms
        self.assertEqual(jid.parse("foo/bar@baz"), (None, "foo", "bar@baz"))
        self.assertEqual(jid.parse("boo@foo/bar@baz"), ("boo", "foo", "bar@baz"))
        self.assertEqual(jid.parse("boo@foo/bar/baz"), ("boo", "foo", "bar/baz"))
        self.assertEqual(jid.parse("boo/foo@bar@baz"), (None, "boo", "foo@bar@baz"))
        self.assertEqual(jid.parse("boo/foo/bar"), (None, "boo", "foo/bar"))
        self.assertEqual(jid.parse("boo//foo"), (None, "boo", "/foo"))

    def test_noHost(self):
        """
        Test for failure on no host part.
        """
        self.assertRaises(jid.InvalidFormat, jid.parse, "user@")

    def test_doubleAt(self):
        """
        Test for failure on double @ signs.

        This should fail because @ is not a valid character for the host
        part of the JID.
        """
        self.assertRaises(jid.InvalidFormat, jid.parse, "user@@host")

    def test_multipleAt(self):
        """
        Test for failure on two @ signs.

        This should fail because @ is not a valid character for the host
        part of the JID.
        """
        self.assertRaises(jid.InvalidFormat, jid.parse, "user@host@host")

    # Basic tests for case mapping. These are fallback tests for the
    # prepping done in twisted.words.protocols.jabber.xmpp_stringprep

    def test_prepCaseMapUser(self):
        """
        Test case mapping of the user part of the JID.
        """
        self.assertEqual(
            jid.prep("UsEr", "host", "resource"), ("user", "host", "resource")
        )

    def test_prepCaseMapHost(self):
        """
        Test case mapping of the host part of the JID.
        """
        self.assertEqual(
            jid.prep("user", "hoST", "resource"), ("user", "host", "resource")
        )

    def test_prepNoCaseMapResource(self):
        """
        Test no case mapping of the resourcce part of the JID.
        """
        self.assertEqual(
            jid.prep("user", "hoST", "resource"), ("user", "host", "resource")
        )
        self.assertNotEqual(
            jid.prep("user", "host", "Resource"), ("user", "host", "resource")
        )


class JIDTests(unittest.TestCase):
    def test_noneArguments(self):
        """
        Test that using no arguments raises an exception.
        """
        self.assertRaises(RuntimeError, jid.JID)

    def test_attributes(self):
        """
        Test that the attributes correspond with the JID parts.
        """
        j = jid.JID("user@host/resource")
        self.assertEqual(j.user, "user")
        self.assertEqual(j.host, "host")
        self.assertEqual(j.resource, "resource")

    def test_userhost(self):
        """
        Test the extraction of the bare JID.
        """
        j = jid.JID("user@host/resource")
        self.assertEqual("user@host", j.userhost())

    def test_userhostOnlyHost(self):
        """
        Test the extraction of the bare JID of the full form host/resource.
        """
        j = jid.JID("host/resource")
        self.assertEqual("host", j.userhost())

    def test_userhostJID(self):
        """
        Test getting a JID object of the bare JID.
        """
        j1 = jid.JID("user@host/resource")
        j2 = jid.internJID("user@host")
        self.assertIdentical(j2, j1.userhostJID())

    def test_userhostJIDNoResource(self):
        """
        Test getting a JID object of the bare JID when there was no resource.
        """
        j = jid.JID("user@host")
        self.assertIdentical(j, j.userhostJID())

    def test_fullHost(self):
        """
        Test giving a string representation of the JID with only a host part.
        """
        j = jid.JID(tuple=(None, "host", None))
        self.assertEqual("host", j.full())

    def test_fullHostResource(self):
        """
        Test giving a string representation of the JID with host, resource.
        """
        j = jid.JID(tuple=(None, "host", "resource"))
        self.assertEqual("host/resource", j.full())

    def test_fullUserHost(self):
        """
        Test giving a string representation of the JID with user, host.
        """
        j = jid.JID(tuple=("user", "host", None))
        self.assertEqual("user@host", j.full())

    def test_fullAll(self):
        """
        Test giving a string representation of the JID.
        """
        j = jid.JID(tuple=("user", "host", "resource"))
        self.assertEqual("user@host/resource", j.full())

    def test_equality(self):
        """
        Test JID equality.
        """
        j1 = jid.JID("user@host/resource")
        j2 = jid.JID("user@host/resource")
        self.assertNotIdentical(j1, j2)
        self.assertEqual(j1, j2)

    def test_equalityWithNonJIDs(self):
        """
        Test JID equality.
        """
        j = jid.JID("user@host/resource")
        self.assertFalse(j == "user@host/resource")

    def test_inequality(self):
        """
        Test JID inequality.
        """
        j1 = jid.JID("user1@host/resource")
        j2 = jid.JID("user2@host/resource")
        self.assertNotEqual(j1, j2)

    def test_inequalityWithNonJIDs(self):
        """
        Test JID equality.
        """
        j = jid.JID("user@host/resource")
        self.assertNotEqual(j, "user@host/resource")

    def test_hashable(self):
        """
        Test JID hashability.
        """
        j1 = jid.JID("user@host/resource")
        j2 = jid.JID("user@host/resource")
        self.assertEqual(hash(j1), hash(j2))

    def test_str(self):
        """
        Test unicode representation of JIDs.
        """
        j = jid.JID(tuple=("user", "host", "resource"))
        self.assertEqual("user@host/resource", str(j))

    def test_repr(self):
        """
        Test representation of JID objects.
        """
        j = jid.JID(tuple=("user", "host", "resource"))
        self.assertEqual("JID(%s)" % repr("user@host/resource"), repr(j))


class InternJIDTests(unittest.TestCase):
    def test_identity(self):
        """
        Test that two interned JIDs yield the same object.
        """
        j1 = jid.internJID("user@host")
        j2 = jid.internJID("user@host")
        self.assertIdentical(j1, j2)
