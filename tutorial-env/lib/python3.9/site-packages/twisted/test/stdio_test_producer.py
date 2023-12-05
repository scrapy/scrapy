# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_producer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_producer} to test
that process transports implement IProducer properly.
"""


import sys

from twisted.internet import protocol, stdio
from twisted.python import log, reflect


class ProducerChild(protocol.Protocol):
    _paused = False
    buf = b""

    def connectionLost(self, reason):
        log.msg("*****OVER*****")
        reactor.callLater(1, reactor.stop)

    def dataReceived(self, data):
        self.buf += data
        if self._paused:
            log.startLogging(sys.stderr)
            log.msg("dataReceived while transport paused!")
            self.transport.loseConnection()
        else:
            self.transport.write(data)
            if self.buf.endswith(b"\n0\n"):
                self.transport.loseConnection()
            else:
                self.pause()

    def pause(self):
        self._paused = True
        self.transport.pauseProducing()
        reactor.callLater(0.01, self.unpause)

    def unpause(self):
        self._paused = False
        self.transport.resumeProducing()


if __name__ == "__main__":
    reflect.namedAny(sys.argv[1]).install()
    from twisted.internet import reactor

    stdio.StandardIO(ProducerChild())
    reactor.run()  # type: ignore[attr-defined]
