# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The parent class for all the SSH services.  Currently implemented services
are ssh-userauth and ssh-connection.

Maintainer: Paul Swartz
"""

from __future__ import division, absolute_import

from twisted.python import log

class SSHService(log.Logger):
    name = None # this is the ssh name for the service
    protocolMessages = {} # these map #'s -> protocol names
    transport = None # gets set later

    def serviceStarted(self):
        """
        called when the service is active on the transport.
        """

    def serviceStopped(self):
        """
        called when the service is stopped, either by the connection ending
        or by another service being started
        """

    def logPrefix(self):
        return "SSHService %r on %s" % (self.name,
                self.transport.transport.logPrefix())

    def packetReceived(self, messageNum, packet):
        """
        called when we receive a packet on the transport
        """
        #print self.protocolMessages
        if messageNum in self.protocolMessages:
            messageType = self.protocolMessages[messageNum]
            f = getattr(self,'ssh_%s' % messageType[4:],
                        None)
            if f is not None:
                return f(packet)
        log.msg("couldn't handle %r" % messageNum)
        log.msg(repr(packet))
        self.transport.sendUnimplemented()
