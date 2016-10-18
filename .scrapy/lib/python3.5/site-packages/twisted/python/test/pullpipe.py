# -*- test-case-name: twisted.python.test.test_sendmsg -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import sys
import os
import socket
from struct import unpack

from twisted.python.sendmsg import recvmsg


def recvfd(socketfd):
    """
    Receive a file descriptor from a L{sendmsg} message on the given C{AF_UNIX}
    socket.

    @param socketfd: An C{AF_UNIX} socket, attached to another process waiting
        to send sockets via the ancillary data mechanism in L{send1msg}.

    @param fd: C{int}

    @return: a 2-tuple of (new file descriptor, description).
    @rtype: 2-tuple of (C{int}, C{bytes})
    """
    ourSocket = socket.fromfd(socketfd, socket.AF_UNIX, socket.SOCK_STREAM)
    data, ancillary, flags = recvmsg(ourSocket)
    [(cmsgLevel, cmsgType, packedFD)] = ancillary
    # cmsgLevel and cmsgType really need to be SOL_SOCKET / SCM_RIGHTS, but
    # since those are the *only* standard values, there's not much point in
    # checking.
    [unpackedFD] = unpack("i", packedFD)
    return (unpackedFD, data)


if __name__ == '__main__':
    fd, description = recvfd(int(sys.argv[1]))
    os.write(fd, b"Test fixture data: " + description + b".\n")
    os.close(fd)
