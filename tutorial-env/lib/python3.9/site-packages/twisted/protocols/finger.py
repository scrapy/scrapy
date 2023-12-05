# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""The Finger User Information Protocol (RFC 1288)"""

from twisted.protocols import basic


class Finger(basic.LineReceiver):
    def lineReceived(self, line):
        parts = line.split()
        if not parts:
            parts = [b""]
        if len(parts) == 1:
            slash_w = 0
        else:
            slash_w = 1
        user = parts[-1]
        if b"@" in user:
            hostPlace = user.rfind(b"@")
            user = user[:hostPlace]
            host = user[hostPlace + 1 :]
            return self.forwardQuery(slash_w, user, host)
        if user:
            return self.getUser(slash_w, user)
        else:
            return self.getDomain(slash_w)

    def _refuseMessage(self, message):
        self.transport.write(message + b"\n")
        self.transport.loseConnection()

    def forwardQuery(self, slash_w, user, host):
        self._refuseMessage(b"Finger forwarding service denied")

    def getDomain(self, slash_w):
        self._refuseMessage(b"Finger online list denied")

    def getUser(self, slash_w, user):
        self.transport.write(b"Login: " + user + b"\n")
        self._refuseMessage(b"No such user")
