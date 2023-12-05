# -*- test-case-name: twisted.conch.test.test_mixin -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Experimental optimization

This module provides a single mixin class which allows protocols to
collapse numerous small writes into a single larger one.

@author: Jp Calderone
"""

from twisted.internet import reactor


class BufferingMixin:
    """
    Mixin which adds write buffering.
    """

    _delayedWriteCall = None
    data = None

    DELAY = 0.0

    def schedule(self):
        return reactor.callLater(self.DELAY, self.flush)

    def reschedule(self, token):
        token.reset(self.DELAY)

    def write(self, data):
        """
        Buffer some bytes to be written soon.

        Every call to this function delays the real write by C{self.DELAY}
        seconds.  When the delay expires, all collected bytes are written
        to the underlying transport using L{ITransport.writeSequence}.
        """
        if self._delayedWriteCall is None:
            self.data = []
            self._delayedWriteCall = self.schedule()
        else:
            self.reschedule(self._delayedWriteCall)
        self.data.append(data)

    def flush(self):
        """
        Flush the buffer immediately.
        """
        self._delayedWriteCall = None
        self.transport.writeSequence(self.data)
        self.data = None
