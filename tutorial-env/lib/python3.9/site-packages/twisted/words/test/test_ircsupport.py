# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.im.ircsupport}.
"""

from twisted.test.proto_helpers import StringTransport
from twisted.words.im.basechat import ChatUI, Conversation, GroupConversation
from twisted.words.im.ircsupport import IRCAccount, IRCProto
from twisted.words.im.locals import OfflineError
from twisted.words.test.test_irc import IRCTestCase


class StubConversation(Conversation):
    def show(self):
        pass

    def showMessage(self, message, metadata):
        self.message = message
        self.metadata = metadata


class StubGroupConversation(GroupConversation):
    def setTopic(self, topic, nickname):
        self.topic = topic
        self.topicSetBy = nickname

    def show(self):
        pass

    def showGroupMessage(self, sender, text, metadata=None):
        self.metadata = metadata
        self.text = text
        self.metadata = metadata


class StubChatUI(ChatUI):
    def getConversation(self, group, Class=StubConversation, stayHidden=0):
        return ChatUI.getGroupConversation(self, group, Class, stayHidden)

    def getGroupConversation(self, group, Class=StubGroupConversation, stayHidden=0):
        return ChatUI.getGroupConversation(self, group, Class, stayHidden)


class IRCProtoTests(IRCTestCase):
    """
    Tests for L{IRCProto}.
    """

    def setUp(self):
        self.account = IRCAccount(
            "Some account", False, "alice", None, "example.com", 6667
        )
        self.proto = IRCProto(self.account, StubChatUI(), None)
        self.transport = StringTransport()

    def test_login(self):
        """
        When L{IRCProto} is connected to a transport, it sends I{NICK} and
        I{USER} commands with the username from the account object.
        """
        self.proto.makeConnection(self.transport)
        self.assertEqualBufferValue(
            self.transport.value(),
            "NICK alice\r\n" "USER alice foo bar :Twisted-IM user\r\n",
        )

    def test_authenticate(self):
        """
        If created with an account with a password, L{IRCProto} sends a
        I{PASS} command before the I{NICK} and I{USER} commands.
        """
        self.account.password = "secret"
        self.proto.makeConnection(self.transport)
        self.assertEqualBufferValue(
            self.transport.value(),
            "PASS secret\r\n"
            "NICK alice\r\n"
            "USER alice foo bar :Twisted-IM user\r\n",
        )

    def test_channels(self):
        """
        If created with an account with a list of channels, L{IRCProto}
        joins each of those channels after registering.
        """
        self.account.channels = ["#foo", "#bar"]
        self.proto.makeConnection(self.transport)
        self.assertEqualBufferValue(
            self.transport.value(),
            "NICK alice\r\n"
            "USER alice foo bar :Twisted-IM user\r\n"
            "JOIN #foo\r\n"
            "JOIN #bar\r\n",
        )

    def test_isupport(self):
        """
        L{IRCProto} can interpret I{ISUPPORT} (I{005}) messages from the server
        and reflect their information in its C{supported} attribute.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":irc.example.com 005 alice MODES=4 CHANLIMIT=#:20\r\n")
        self.assertEqual(4, self.proto.supported.getFeature("MODES"))

    def test_nick(self):
        """
        IRC NICK command changes the nickname of a user.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice JOIN #group1\r\n")
        self.proto.dataReceived(":alice1 JOIN #group1\r\n")
        self.proto.dataReceived(":alice1 NICK newnick\r\n")
        self.proto.dataReceived(":alice3 NICK newnick3\r\n")
        self.assertIn("newnick", self.proto._ingroups)
        self.assertNotIn("alice1", self.proto._ingroups)

    def test_part(self):
        """
        IRC PART command removes a user from an IRC channel.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice1 JOIN #group1\r\n")
        self.assertIn("group1", self.proto._ingroups["alice1"])
        self.assertNotIn("group2", self.proto._ingroups["alice1"])
        self.proto.dataReceived(":alice PART #group1\r\n")
        self.proto.dataReceived(":alice1 PART #group1\r\n")
        self.proto.dataReceived(":alice1 PART #group2\r\n")
        self.assertNotIn("group1", self.proto._ingroups["alice1"])
        self.assertNotIn("group2", self.proto._ingroups["alice1"])

    def test_quit(self):
        """
        IRC QUIT command removes a user from all IRC channels.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice1 JOIN #group1\r\n")
        self.assertIn("group1", self.proto._ingroups["alice1"])
        self.assertNotIn("group2", self.proto._ingroups["alice1"])
        self.proto.dataReceived(":alice1 JOIN #group3\r\n")
        self.assertIn("group3", self.proto._ingroups["alice1"])
        self.proto.dataReceived(":alice1 QUIT\r\n")
        self.assertTrue(len(self.proto._ingroups["alice1"]) == 0)
        self.proto.dataReceived(":alice3 QUIT\r\n")

    def test_topic(self):
        """
        IRC TOPIC command changes the topic of an IRC channel.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice1 JOIN #group1\r\n")
        self.proto.dataReceived(":alice1 TOPIC #group1 newtopic\r\n")
        groupConversation = self.proto.getGroupConversation("group1")
        self.assertEqual(groupConversation.topic, "newtopic")
        self.assertEqual(groupConversation.topicSetBy, "alice1")

    def test_privmsg(self):
        """
        PRIVMSG sends a private message to a user or channel.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice1 PRIVMSG t2 test_message_1\r\n")
        conversation = self.proto.chat.getConversation(self.proto.getPerson("alice1"))
        self.assertEqual(conversation.message, "test_message_1")

        self.proto.dataReceived(":alice1 PRIVMSG #group1 test_message_2\r\n")
        groupConversation = self.proto.getGroupConversation("group1")
        self.assertEqual(groupConversation.text, "test_message_2")

        self.proto.setNick("alice")
        self.proto.dataReceived(":alice PRIVMSG #foo test_message_3\r\n")
        groupConversation = self.proto.getGroupConversation("foo")
        self.assertFalse(hasattr(groupConversation, "text"))
        conversation = self.proto.chat.getConversation(self.proto.getPerson("alice"))
        self.assertFalse(hasattr(conversation, "message"))

    def test_action(self):
        """
        CTCP ACTION to a user or channel.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":alice1 PRIVMSG alice1 :\01ACTION smiles\01\r\n")
        conversation = self.proto.chat.getConversation(self.proto.getPerson("alice1"))
        self.assertEqual(conversation.message, "smiles")

        self.proto.dataReceived(":alice1 PRIVMSG #group1 :\01ACTION laughs\01\r\n")
        groupConversation = self.proto.getGroupConversation("group1")
        self.assertEqual(groupConversation.text, "laughs")

        self.proto.setNick("alice")
        self.proto.dataReceived(":alice PRIVMSG #group1 :\01ACTION cries\01\r\n")
        groupConversation = self.proto.getGroupConversation("foo")
        self.assertFalse(hasattr(groupConversation, "text"))
        conversation = self.proto.chat.getConversation(self.proto.getPerson("alice"))
        self.assertFalse(hasattr(conversation, "message"))

    def test_rplNamreply(self):
        """
        RPL_NAMREPLY server response (353) lists all the users in a channel.
        RPL_ENDOFNAMES server response (363) is sent at the end of RPL_NAMREPLY
        to indicate that there are no more names.
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(
            ":example.com 353 z3p = #bnl :pSwede Dan- SkOyg @MrOp +MrPlus\r\n"
        )
        expectedInGroups = {
            "Dan-": ["bnl"],
            "pSwede": ["bnl"],
            "SkOyg": ["bnl"],
            "MrOp": ["bnl"],
            "MrPlus": ["bnl"],
        }
        expectedNamReplies = {"bnl": ["pSwede", "Dan-", "SkOyg", "MrOp", "MrPlus"]}
        self.assertEqual(expectedInGroups, self.proto._ingroups)
        self.assertEqual(expectedNamReplies, self.proto._namreplies)

        self.proto.dataReceived(":example.com 366 alice #bnl :End of /NAMES list\r\n")
        self.assertEqual({}, self.proto._namreplies)
        groupConversation = self.proto.getGroupConversation("bnl")
        self.assertEqual(expectedNamReplies["bnl"], groupConversation.members)

    def test_rplTopic(self):
        """
        RPL_TOPIC server response (332) is sent when a channel's topic is changed
        """
        self.proto.makeConnection(self.transport)
        self.proto.dataReceived(":example.com 332 alice, #foo :Some random topic\r\n")
        self.assertEqual("Some random topic", self.proto._topics["foo"])

    def test_sendMessage(self):
        """
        L{IRCPerson.sendMessage}
        """
        self.proto.makeConnection(self.transport)
        person = self.proto.getPerson("alice")
        self.assertRaises(OfflineError, person.sendMessage, "Some message")

        person.account.client = self.proto
        self.transport.clear()
        person.sendMessage("Some message 2")
        self.assertEqual(
            self.transport.io.getvalue(), b"PRIVMSG alice :Some message 2\r\n"
        )

        self.transport.clear()
        person.sendMessage("smiles", {"style": "emote"})
        self.assertEqual(
            self.transport.io.getvalue(), b"PRIVMSG alice :\x01ACTION smiles\x01\r\n"
        )

    def test_sendGroupMessage(self):
        """
        L{IRCGroup.sendGroupMessage}
        """
        self.proto.makeConnection(self.transport)
        group = self.proto.chat.getGroup("#foo", self.proto)
        self.assertRaises(OfflineError, group.sendGroupMessage, "Some message")

        group.account.client = self.proto
        self.transport.clear()
        group.sendGroupMessage("Some message 2")
        self.assertEqual(
            self.transport.io.getvalue(), b"PRIVMSG #foo :Some message 2\r\n"
        )

        self.transport.clear()
        group.sendGroupMessage("smiles", {"style": "emote"})
        self.assertEqual(
            self.transport.io.getvalue(), b"PRIVMSG #foo :\x01ACTION smiles\x01\r\n"
        )
