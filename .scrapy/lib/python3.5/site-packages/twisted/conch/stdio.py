# -*- test-case-name: twisted.conch.test.test_manhole -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Asynchronous local terminal input handling

@author: Jp Calderone
"""

import os, tty, sys, termios

from twisted.internet import reactor, stdio, protocol, defer
from twisted.python import failure, reflect, log

from twisted.conch.insults.insults import ServerProtocol
from twisted.conch.manhole import ColoredManhole

class UnexpectedOutputError(Exception):
    pass

class TerminalProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, proto):
        self.proto = proto
        self.onConnection = defer.Deferred()

    def connectionMade(self):
        self.proto.makeConnection(self)
        self.onConnection.callback(None)
        self.onConnection = None


    def write(self, data):
        """
        Write to the terminal.

        @param data: Data to write.
        @type data: L{bytes}
        """
        self.transport.write(data)


    def outReceived(self, data):
        """
        Receive data from the terminal.

        @param data: Data received.
        @type data: L{bytes}
        """
        self.proto.dataReceived(data)


    def errReceived(self, data):
        """
        Report an error.

        @param data: Data to include in L{Failure}.
        @type data: L{bytes}
        """
        self.transport.loseConnection()
        if self.proto is not None:
            self.proto.connectionLost(failure.Failure(UnexpectedOutputError(data)))
            self.proto = None


    def childConnectionLost(self, childFD):
        if self.proto is not None:
            self.proto.childConnectionLost(childFD)


    def processEnded(self, reason):
        if self.proto is not None:
            self.proto.connectionLost(reason)
            self.proto = None



class ConsoleManhole(ColoredManhole):
    """
    A manhole protocol specifically for use with L{stdio.StandardIO}.
    """
    def connectionLost(self, reason):
        """
        When the connection is lost, there is nothing more to do.  Stop the
        reactor so that the process can exit.
        """
        reactor.stop()



def runWithProtocol(klass):
    fd = sys.__stdin__.fileno()
    oldSettings = termios.tcgetattr(fd)
    tty.setraw(fd)
    try:
        p = ServerProtocol(klass)
        stdio.StandardIO(p)
        reactor.run()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, oldSettings)
        os.write(fd, b"\r\x1bc\r")



def main(argv=None):
    log.startLogging(open('child.log', 'w'))

    if argv is None:
        argv = sys.argv[1:]
    if argv:
        klass = reflect.namedClass(argv[0])
    else:
        klass = ConsoleManhole
    runWithProtocol(klass)


if __name__ == '__main__':
    main()
