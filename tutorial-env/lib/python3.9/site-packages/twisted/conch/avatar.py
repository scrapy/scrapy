# -*- test-case-name: twisted.conch.test.test_conch -*-


from zope.interface import implementer

from twisted.conch.error import ConchError
from twisted.conch.interfaces import IConchUser
from twisted.conch.ssh.connection import OPEN_UNKNOWN_CHANNEL_TYPE
from twisted.logger import Logger
from twisted.python.compat import nativeString


@implementer(IConchUser)
class ConchUser:
    _log = Logger()

    def __init__(self):
        self.channelLookup = {}
        self.subsystemLookup = {}

    @property
    def conn(self):
        return self._conn

    @conn.setter
    def conn(self, value):
        self._conn = value

    def lookupChannel(self, channelType, windowSize, maxPacket, data):
        klass = self.channelLookup.get(channelType, None)
        if not klass:
            raise ConchError(OPEN_UNKNOWN_CHANNEL_TYPE, "unknown channel")
        else:
            return klass(
                remoteWindow=windowSize,
                remoteMaxPacket=maxPacket,
                data=data,
                avatar=self,
            )

    def lookupSubsystem(self, subsystem, data):
        self._log.debug(
            "Subsystem lookup: {subsystem!r}", subsystem=self.subsystemLookup
        )
        klass = self.subsystemLookup.get(subsystem, None)
        if not klass:
            return False
        return klass(data, avatar=self)

    def gotGlobalRequest(self, requestType, data):
        # XXX should this use method dispatch?
        requestType = nativeString(requestType.replace(b"-", b"_"))
        f = getattr(self, "global_%s" % requestType, None)
        if not f:
            return 0
        return f(data)
