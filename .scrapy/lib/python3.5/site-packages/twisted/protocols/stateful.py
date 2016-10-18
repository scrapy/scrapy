# -*- test-case-name: twisted.test.test_stateful -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.internet import protocol

from io import BytesIO

class StatefulProtocol(protocol.Protocol):
    """A Protocol that stores state for you.

    state is a pair (function, num_bytes). When num_bytes bytes of data arrives
    from the network, function is called. It is expected to return the next
    state or None to keep same state. Initial state is returned by
    getInitialState (override it).
    """
    _sful_data = None, None, 0

    def makeConnection(self, transport):
        protocol.Protocol.makeConnection(self, transport)
        self._sful_data = self.getInitialState(), BytesIO(), 0

    def getInitialState(self):
        raise NotImplementedError

    def dataReceived(self, data):
        state, buffer, offset = self._sful_data
        buffer.seek(0, 2)
        buffer.write(data)
        blen = buffer.tell() # how many bytes total is in the buffer
        buffer.seek(offset)
        while blen - offset >= state[1]:
            d = buffer.read(state[1])
            offset += state[1]
            next = state[0](d)
            if self.transport.disconnecting: # XXX: argh stupid hack borrowed right from LineReceiver
                return # dataReceived won't be called again, so who cares about consistent state
            if next:
                state = next
        if offset != 0:
            b = buffer.read()
            buffer.seek(0)
            buffer.truncate()
            buffer.write(b)
            offset = 0
        self._sful_data = state, buffer, offset

