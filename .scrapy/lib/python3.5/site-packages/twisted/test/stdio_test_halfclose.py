# -*- test-case-name: twisted.test.test_stdio.StandardInputOutputTests.test_readConnectionLost -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Main program for the child process run by
L{twisted.test.test_stdio.StandardInputOutputTests.test_readConnectionLost}
to test that IHalfCloseableProtocol.readConnectionLost works for process
transports.
"""

from __future__ import absolute_import, division

import sys

from zope.interface import implementer

from twisted.internet.interfaces import IHalfCloseableProtocol
from twisted.internet import stdio, protocol
from twisted.python import reflect, log


@implementer(IHalfCloseableProtocol)
class HalfCloseProtocol(protocol.Protocol):
    """
    A protocol to hook up to stdio and observe its transport being
    half-closed.  If all goes as expected, C{exitCode} will be set to C{0};
    otherwise it will be set to C{1} to indicate failure.
    """
    exitCode = None

    def connectionMade(self):
        """
        Signal the parent process that we're ready.
        """
        self.transport.write(b"x")


    def readConnectionLost(self):
        """
        This is the desired event.  Once it has happened, stop the reactor so
        the process will exit.
        """
        self.exitCode = 0
        reactor.stop()


    def connectionLost(self, reason):
        """
        This may only be invoked after C{readConnectionLost}.  If it happens
        otherwise, mark it as an error and shut down.
        """
        if self.exitCode is None:
            self.exitCode = 1
            log.err(reason, "Unexpected call to connectionLost")
        reactor.stop()



if __name__ == '__main__':
    reflect.namedAny(sys.argv[1]).install()
    log.startLogging(open(sys.argv[2], 'wb'))
    from twisted.internet import reactor
    protocol = HalfCloseProtocol()
    stdio.StandardIO(protocol)
    reactor.run()
    sys.exit(protocol.exitCode)
