# -*- test-case-name: twisted.test.test_sendmsg -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
sendmsg(2) and recvmsg(2) support for Python.
"""


from collections import namedtuple
from socket import CMSG_SPACE, SCM_RIGHTS, socket as Socket
from typing import List, Tuple

__all__ = ["sendmsg", "recvmsg", "getSocketFamily", "SCM_RIGHTS"]


ReceivedMessage = namedtuple("ReceivedMessage", ["data", "ancillary", "flags"])


def sendmsg(
    socket: Socket,
    data: bytes,
    ancillary: List[Tuple[int, int, bytes]] = [],
    flags: int = 0,
) -> int:
    """
    Send a message on a socket.

    @param socket: The socket to send the message on.
    @param data: Bytes to write to the socket.
    @param ancillary: Extra data to send over the socket outside of the normal
        datagram or stream mechanism.  By default no ancillary data is sent.
    @param flags: Flags to affect how the message is sent.  See the C{MSG_}
        constants in the sendmsg(2) manual page.  By default no flags are set.

    @return: The return value of the underlying syscall, if it succeeds.
    """
    return socket.sendmsg([data], ancillary, flags)


def recvmsg(
    socket: Socket, maxSize: int = 8192, cmsgSize: int = 4096, flags: int = 0
) -> ReceivedMessage:
    """
    Receive a message on a socket.

    @param socket: The socket to receive the message on.
    @param maxSize: The maximum number of bytes to receive from the socket using
        the datagram or stream mechanism. The default maximum is 8192.
    @param cmsgSize: The maximum number of bytes to receive from the socket
        outside of the normal datagram or stream mechanism. The default maximum
        is 4096.
    @param flags: Flags to affect how the message is sent.  See the C{MSG_}
        constants in the sendmsg(2) manual page. By default no flags are set.

    @return: A named 3-tuple of the bytes received using the datagram/stream
        mechanism, a L{list} of L{tuple}s giving ancillary received data, and
        flags as an L{int} describing the data received.
    """
    # In Twisted's _sendmsg.c, the csmg_space was defined as:
    #     int cmsg_size = 4096;
    #     cmsg_space = CMSG_SPACE(cmsg_size);
    # Since the default in Python 3's socket is 0, we need to define our
    # own default of 4096. -hawkie
    data, ancillary, flags = socket.recvmsg(maxSize, CMSG_SPACE(cmsgSize), flags)[0:3]

    return ReceivedMessage(data=data, ancillary=ancillary, flags=flags)


def getSocketFamily(socket: Socket) -> int:
    """
    Return the family of the given socket.

    @param socket: The socket to get the family of.
    """
    return socket.family
