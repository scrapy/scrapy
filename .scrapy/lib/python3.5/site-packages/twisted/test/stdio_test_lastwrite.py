# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_lastWriteReceived -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_lastWriteReceived}
to test that L{os.write} can be reliably used after
L{twisted.internet.stdio.StandardIO} has finished.
"""

from __future__ import absolute_import, division

import sys

from twisted.internet.protocol import Protocol
from twisted.internet.stdio import StandardIO
from twisted.python.reflect import namedAny


class LastWriteChild(Protocol):
    def __init__(self, reactor, magicString):
        self.reactor = reactor
        self.magicString = magicString


    def connectionMade(self):
        self.transport.write(self.magicString)
        self.transport.loseConnection()


    def connectionLost(self, reason):
        self.reactor.stop()



def main(reactor, magicString):
    p = LastWriteChild(reactor, magicString.encode('ascii'))
    StandardIO(p)
    reactor.run()



if __name__ == '__main__':
    namedAny(sys.argv[1]).install()
    from twisted.internet import reactor
    main(reactor, sys.argv[2])
