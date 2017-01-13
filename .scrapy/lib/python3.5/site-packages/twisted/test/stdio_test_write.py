# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_write -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_write} to test that
ITransport.write() works for process transports.
"""

from __future__ import absolute_import, division

import sys

from twisted.internet import stdio, protocol
from twisted.python import reflect



class WriteChild(protocol.Protocol):
    def connectionMade(self):
        self.transport.write(b'o')
        self.transport.write(b'k')
        self.transport.write(b'!')
        self.transport.loseConnection()


    def connectionLost(self, reason):
        reactor.stop()



if __name__ == '__main__':
    reflect.namedAny(sys.argv[1]).install()
    from twisted.internet import reactor
    stdio.StandardIO(WriteChild())
    reactor.run()
