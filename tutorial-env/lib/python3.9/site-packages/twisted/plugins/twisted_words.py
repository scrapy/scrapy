# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from zope.interface import provider

from twisted.application.service import ServiceMaker
from twisted.plugin import IPlugin
from twisted.words import iwords

NewTwistedWords = ServiceMaker(
    "New Twisted Words", "twisted.words.tap", "A modern words server", "words"
)

TwistedXMPPRouter = ServiceMaker(
    "XMPP Router", "twisted.words.xmpproutertap", "An XMPP Router server", "xmpp-router"
)


@provider(IPlugin, iwords.IProtocolPlugin)
class RelayChatInterface:

    name = "irc"

    @classmethod
    def getFactory(cls, realm, portal):
        from twisted.words import service

        return service.IRCFactory(realm, portal)


@provider(IPlugin, iwords.IProtocolPlugin)
class PBChatInterface:

    name = "pb"

    @classmethod
    def getFactory(cls, realm, portal):
        from twisted.spread import pb

        return pb.PBServerFactory(portal, True)
