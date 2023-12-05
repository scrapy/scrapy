# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_loseConnection -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_loseConnection} to
test that ITransport.loseConnection() works for process transports.
"""


import sys

from twisted.internet import protocol, stdio
from twisted.internet.error import ConnectionDone
from twisted.python import log, reflect


class LoseConnChild(protocol.Protocol):
    exitCode = 0

    def connectionMade(self):
        self.transport.loseConnection()

    def connectionLost(self, reason):
        """
        Check that C{reason} is a L{Failure} wrapping a L{ConnectionDone}
        instance and stop the reactor.  If C{reason} is wrong for some reason,
        log something about that in C{self.errorLogFile} and make sure the
        process exits with a non-zero status.
        """
        try:
            try:
                reason.trap(ConnectionDone)
            except BaseException:
                log.err(None, "Problem with reason passed to connectionLost")
                self.exitCode = 1
        finally:
            reactor.stop()


if __name__ == "__main__":
    reflect.namedAny(sys.argv[1]).install()
    log.startLogging(open(sys.argv[2], "wb"))
    from twisted.internet import reactor

    protocolLoseConnChild = LoseConnChild()
    stdio.StandardIO(protocolLoseConnChild)
    reactor.run()  # type: ignore[attr-defined]
    sys.exit(protocolLoseConnChild.exitCode)
