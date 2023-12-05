# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for IRC portions of L{twisted.words.service}.
"""

from twisted.cred import checkers, portal
from twisted.test import proto_helpers
from twisted.words.protocols import irc
from twisted.words.service import InMemoryWordsRealm, IRCFactory, IRCUser
from twisted.words.test.test_irc import IRCTestCase


class IRCUserTests(IRCTestCase):
    """
    Isolated tests for L{IRCUser}
    """

    def setUp(self):
        """
        Sets up a Realm, Portal, Factory, IRCUser, Transport, and Connection
        for our tests.
        """
        self.realm = InMemoryWordsRealm("example.com")
        self.checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        self.portal = portal.Portal(self.realm, [self.checker])
        self.checker.addUser("john", "pass")
        self.factory = IRCFactory(self.realm, self.portal)
        self.ircUser = self.factory.buildProtocol(None)
        self.stringTransport = proto_helpers.StringTransport()
        self.ircUser.makeConnection(self.stringTransport)

    def test_sendMessage(self):
        """
        Sending a message to a user after they have sent NICK, but before they
        have authenticated, results in a message from "example.com".
        """
        self.ircUser.irc_NICK("", ["mynick"])
        self.stringTransport.clear()
        self.ircUser.sendMessage("foo")
        self.assertEqualBufferValue(
            self.stringTransport.value(), ":example.com foo mynick\r\n"
        )

    def test_utf8Messages(self):
        """
        When a UTF8 message is sent with sendMessage and the current IRCUser
        has a UTF8 nick and is set to UTF8 encoding, the message will be
        written to the transport.
        """
        expectedResult = ":example.com тест ник\r\n".encode()

        self.ircUser.irc_NICK("", ["\u043d\u0438\u043a".encode()])
        self.stringTransport.clear()
        self.ircUser.sendMessage("\u0442\u0435\u0441\u0442".encode())
        self.assertEqualBufferValue(self.stringTransport.value(), expectedResult)

    def test_invalidEncodingNick(self):
        """
        A NICK command sent with a nickname that cannot be decoded with the
        current IRCUser's encoding results in a PRIVMSG from NickServ
        indicating that the nickname could not be decoded.
        """
        self.ircUser.irc_NICK("", [b"\xd4\xc5\xd3\xd4"])
        self.assertRaises(UnicodeError)

    def response(self):
        """
        Grabs our responses and then clears the transport
        """
        response = self.ircUser.transport.value()
        self.ircUser.transport.clear()
        if bytes != str and isinstance(response, bytes):
            response = response.decode("utf-8")
        response = response.splitlines()
        return [irc.parsemsg(r) for r in response]

    def scanResponse(self, response, messageType):
        """
        Gets messages out of a response

        @param response: The parsed IRC messages of the response, as returned
        by L{IRCUserTests.response}

        @param messageType: The string type of the desired messages.

        @return: An iterator which yields 2-tuples of C{(index, ircMessage)}
        """
        for n, message in enumerate(response):
            if message[1] == messageType:
                yield n, message

    def test_sendNickSendsGreeting(self):
        """
        Receiving NICK without authenticating sends the MOTD Start and MOTD End
        messages, which is required by certain popular IRC clients (such as
        Pidgin) before a connection is considered to be fully established.
        """
        self.ircUser.irc_NICK("", ["mynick"])
        response = self.response()
        start = list(self.scanResponse(response, irc.RPL_MOTDSTART))
        end = list(self.scanResponse(response, irc.RPL_ENDOFMOTD))
        self.assertEqual(
            start,
            [
                (
                    0,
                    (
                        "example.com",
                        "375",
                        ["mynick", "- example.com Message of the Day - "],
                    ),
                )
            ],
        )
        self.assertEqual(
            end, [(1, ("example.com", "376", ["mynick", "End of /MOTD command."]))]
        )

    def test_fullLogin(self):
        """
        Receiving USER, PASS, NICK will log in the user, and transmit the
        appropriate response messages.
        """
        self.ircUser.irc_USER("", ["john doe"])
        self.ircUser.irc_PASS("", ["pass"])
        self.ircUser.irc_NICK("", ["john"])

        version = "Your host is example.com, running version {}".format(
            self.factory._serverInfo["serviceVersion"],
        )

        creation = "This server was created on {}".format(
            self.factory._serverInfo["creationDate"],
        )

        self.assertEqual(
            self.response(),
            [
                ("example.com", "375", ["john", "- example.com Message of the Day - "]),
                ("example.com", "376", ["john", "End of /MOTD command."]),
                ("example.com", "001", ["john", "connected to Twisted IRC"]),
                ("example.com", "002", ["john", version]),
                ("example.com", "003", ["john", creation]),
                (
                    "example.com",
                    "004",
                    [
                        "john",
                        "example.com",
                        self.factory._serverInfo["serviceVersion"],
                        "w",
                        "n",
                    ],
                ),
            ],
        )

    def test_PART(self):
        """
        irc_PART
        """
        self.ircUser.irc_NICK("testuser", ["mynick"])
        response = self.response()
        self.ircUser.transport.clear()
        self.assertEqual(response[0][1], irc.RPL_MOTDSTART)
        self.ircUser.irc_JOIN("testuser", ["somechannel"])
        response = self.response()
        self.ircUser.transport.clear()
        self.assertEqual(response[0][1], irc.ERR_NOSUCHCHANNEL)
        self.ircUser.irc_PART("testuser", [b"somechannel", b"booga"])
        response = self.response()
        self.ircUser.transport.clear()
        self.assertEqual(response[0][1], irc.ERR_NOTONCHANNEL)
        self.ircUser.irc_PART("testuser", ["somechannel", "booga"])
        response = self.response()
        self.ircUser.transport.clear()
        self.assertEqual(response[0][1], irc.ERR_NOTONCHANNEL)

    def test_NAMES(self):
        """
        irc_NAMES
        """
        self.ircUser.irc_NICK("", ["testuser"])
        self.ircUser.irc_JOIN("", ["somechannel"])
        self.ircUser.transport.clear()
        self.ircUser.irc_NAMES("", ["somechannel"])
        response = self.response()
        self.assertEqual(response[0][1], irc.RPL_ENDOFNAMES)


class MocksyIRCUser(IRCUser):
    def __init__(self):
        self.realm = InMemoryWordsRealm("example.com")
        self.mockedCodes = []

    def sendMessage(self, code, *_, **__):
        self.mockedCodes.append(code)


BADTEXT = b"\xff"


class IRCUserBadEncodingTests(IRCTestCase):
    """
    Verifies that L{IRCUser} sends the correct error messages back to clients
    when given indecipherable bytes
    """

    # TODO: irc_NICK -- but NICKSERV is used for that, so it isn't as easy.

    def setUp(self):
        self.ircUser = MocksyIRCUser()

    def assertChokesOnBadBytes(self, irc_x, error):
        """
        Asserts that IRCUser sends the relevant error code when a given irc_x
        dispatch method is given undecodable bytes.

        @param irc_x: the name of the irc_FOO method to test.
        For example, irc_x = 'PRIVMSG' will check irc_PRIVMSG

        @param error: the error code irc_x should send. For example,
        irc.ERR_NOTONCHANNEL
        """
        getattr(self.ircUser, "irc_%s" % irc_x)(None, [BADTEXT])
        self.assertEqual(self.ircUser.mockedCodes, [error])

    # No such channel

    def test_JOIN(self):
        """
        Tests that irc_JOIN sends ERR_NOSUCHCHANNEL if the channel name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("JOIN", irc.ERR_NOSUCHCHANNEL)

    def test_NAMES(self):
        """
        Tests that irc_NAMES sends ERR_NOSUCHCHANNEL if the channel name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("NAMES", irc.ERR_NOSUCHCHANNEL)

    def test_TOPIC(self):
        """
        Tests that irc_TOPIC sends ERR_NOSUCHCHANNEL if the channel name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("TOPIC", irc.ERR_NOSUCHCHANNEL)

    def test_LIST(self):
        """
        Tests that irc_LIST sends ERR_NOSUCHCHANNEL if the channel name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("LIST", irc.ERR_NOSUCHCHANNEL)

    # No such nick

    def test_MODE(self):
        """
        Tests that irc_MODE sends ERR_NOSUCHNICK if the target name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("MODE", irc.ERR_NOSUCHNICK)

    def test_PRIVMSG(self):
        """
        Tests that irc_PRIVMSG sends ERR_NOSUCHNICK if the target name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("PRIVMSG", irc.ERR_NOSUCHNICK)

    def test_WHOIS(self):
        """
        Tests that irc_WHOIS sends ERR_NOSUCHNICK if the target name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("WHOIS", irc.ERR_NOSUCHNICK)

    # Not on channel

    def test_PART(self):
        """
        Tests that irc_PART sends ERR_NOTONCHANNEL if the target name can't
        be decoded.
        """
        self.assertChokesOnBadBytes("PART", irc.ERR_NOTONCHANNEL)

    # Probably nothing

    def test_WHO(self):
        """
        Tests that irc_WHO immediately ends the WHO list if the target name
        can't be decoded.
        """
        self.assertChokesOnBadBytes("WHO", irc.RPL_ENDOFWHO)
