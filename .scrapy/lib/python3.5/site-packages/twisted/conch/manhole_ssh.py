# -*- test-case-name: twisted.conch.test.test_manhole -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
insults/SSH integration support.

@author: Jp Calderone
"""

from zope.interface import implementer

from twisted.conch import avatar, interfaces as iconch, error as econch
from twisted.conch.ssh import factory, session
from twisted.python import components

from twisted.conch.insults import insults


class _Glue:
    """A feeble class for making one attribute look like another.

    This should be replaced with a real class at some point, probably.
    Try not to write new code that uses it.
    """
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        raise AttributeError(self.name, "has no attribute", name)



class TerminalSessionTransport:
    def __init__(self, proto, chainedProtocol, avatar, width, height):
        self.proto = proto
        self.avatar = avatar
        self.chainedProtocol = chainedProtocol

        protoSession = self.proto.session

        self.proto.makeConnection(
            _Glue(write=self.chainedProtocol.dataReceived,
                  loseConnection=lambda: avatar.conn.sendClose(protoSession),
                  name="SSH Proto Transport"))

        def loseConnection():
            self.proto.loseConnection()

        self.chainedProtocol.makeConnection(
            _Glue(write=self.proto.write,
                  loseConnection=loseConnection,
                  name="Chained Proto Transport"))

        # XXX TODO
        # chainedProtocol is supposed to be an ITerminalTransport,
        # maybe.  That means perhaps its terminalProtocol attribute is
        # an ITerminalProtocol, it could be.  So calling terminalSize
        # on that should do the right thing But it'd be nice to clean
        # this bit up.
        self.chainedProtocol.terminalProtocol.terminalSize(width, height)



@implementer(iconch.ISession)
class TerminalSession(components.Adapter):
    transportFactory = TerminalSessionTransport
    chainedProtocolFactory = insults.ServerProtocol

    def getPty(self, term, windowSize, attrs):
        self.height, self.width = windowSize[:2]

    def openShell(self, proto):
        self.transportFactory(
            proto, self.chainedProtocolFactory(),
            iconch.IConchUser(self.original),
            self.width, self.height)

    def execCommand(self, proto, cmd):
        raise econch.ConchError("Cannot execute commands")

    def closed(self):
        pass



class TerminalUser(avatar.ConchUser, components.Adapter):
    def __init__(self, original, avatarId):
        components.Adapter.__init__(self, original)
        avatar.ConchUser.__init__(self)
        self.channelLookup[b'session'] = session.SSHSession



class TerminalRealm:
    userFactory = TerminalUser
    sessionFactory = TerminalSession

    transportFactory = TerminalSessionTransport
    chainedProtocolFactory = insults.ServerProtocol

    def _getAvatar(self, avatarId):
        comp = components.Componentized()
        user = self.userFactory(comp, avatarId)
        sess = self.sessionFactory(comp)

        sess.transportFactory = self.transportFactory
        sess.chainedProtocolFactory = self.chainedProtocolFactory

        comp.setComponent(iconch.IConchUser, user)
        comp.setComponent(iconch.ISession, sess)

        return user

    def __init__(self, transportFactory=None):
        if transportFactory is not None:
            self.transportFactory = transportFactory

    def requestAvatar(self, avatarId, mind, *interfaces):
        for i in interfaces:
            if i is iconch.IConchUser:
                return (iconch.IConchUser,
                        self._getAvatar(avatarId),
                        lambda: None)
        raise NotImplementedError()



class ConchFactory(factory.SSHFactory):
    publicKeys = {}
    privateKeys = {}

    def __init__(self, portal):
        self.portal = portal
