# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.im.basechat}.
"""

from twisted.trial import unittest
from twisted.words.im import basechat, basesupport


class ChatUITests(unittest.TestCase):
    """
    Tests for the L{basechat.ChatUI} chat client.
    """

    def setUp(self):
        self.ui = basechat.ChatUI()
        self.account = basesupport.AbstractAccount(
            "fooAccount", False, "foo", "password", "host", "port"
        )
        self.person = basesupport.AbstractPerson("foo", self.account)

    def test_contactChangedNickNoKey(self):
        """
        L{basechat.ChatUI.contactChangedNick} on an
        L{twisted.words.im.interfaces.IPerson} who doesn't have an account
        associated with the L{basechat.ChatUI} instance has no effect.
        """
        self.assertEqual(self.person.name, "foo")
        self.assertEqual(self.person.account, self.account)

        self.ui.contactChangedNick(self.person, "bar")
        self.assertEqual(self.person.name, "foo")
        self.assertEqual(self.person.account, self.account)

    def test_contactChangedNickNoConversation(self):
        """
        L{basechat.ChatUI.contactChangedNick} changes the name for an
        L{twisted.words.im.interfaces.IPerson}.
        """
        self.ui.persons[self.person.name, self.person.account] = self.person

        self.assertEqual(self.person.name, "foo")
        self.assertEqual(self.person.account, self.account)

        self.ui.contactChangedNick(self.person, "bar")
        self.assertEqual(self.person.name, "bar")
        self.assertEqual(self.person.account, self.account)

    def test_contactChangedNickHasConversation(self):
        """
        If an L{twisted.words.im.interfaces.IPerson} is in a
        L{basechat.Conversation}, L{basechat.ChatUI.contactChangedNick} causes a
        name change for that person in both the L{basechat.Conversation} and the
        L{basechat.ChatUI}.
        """
        self.ui.persons[self.person.name, self.person.account] = self.person
        conversation = basechat.Conversation(self.person, self.ui)
        self.ui.conversations[self.person] = conversation

        self.assertEqual(self.person.name, "foo")
        self.assertEqual(self.person.account, self.account)

        self.ui.contactChangedNick(self.person, "bar")
        self.assertEqual(self.person.name, "bar")
        self.assertEqual(self.person.account, self.account)
