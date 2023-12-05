# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Loopback helper used in test_ssh and test_recvline
"""


from twisted.protocols import loopback


class LoopbackRelay(loopback.LoopbackRelay):
    clearCall = None

    def logPrefix(self):
        return f"LoopbackRelay({self.target.__class__.__name__!r})"

    def write(self, data):
        loopback.LoopbackRelay.write(self, data)
        if self.clearCall is not None:
            self.clearCall.cancel()

        from twisted.internet import reactor

        self.clearCall = reactor.callLater(0, self._clearBuffer)

    def _clearBuffer(self):
        self.clearCall = None
        loopback.LoopbackRelay.clearBuffer(self)
