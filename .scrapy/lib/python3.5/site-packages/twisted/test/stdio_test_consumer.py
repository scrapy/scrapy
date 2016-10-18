# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_consumer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_consumer} to test
that process transports implement IConsumer properly.
"""

from __future__ import absolute_import, division

import sys

from twisted.python import log, reflect
from twisted.internet import stdio, protocol
from twisted.protocols import basic

def failed(err):
    log.startLogging(sys.stderr)
    log.err(err)



class ConsumerChild(protocol.Protocol):
    def __init__(self, junkPath):
        self.junkPath = junkPath


    def connectionMade(self):
        d = basic.FileSender().beginFileTransfer(open(self.junkPath, 'rb'),
                                                 self.transport)
        d.addErrback(failed)
        d.addCallback(lambda ign: self.transport.loseConnection())


    def connectionLost(self, reason):
        reactor.stop()



if __name__ == '__main__':
    reflect.namedAny(sys.argv[1]).install()
    from twisted.internet import reactor
    stdio.StandardIO(ConsumerChild(sys.argv[2]))
    reactor.run()
