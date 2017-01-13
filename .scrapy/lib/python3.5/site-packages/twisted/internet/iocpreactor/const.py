# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Windows constants for IOCP
"""


# this stuff should really be gotten from Windows headers via pyrex, but it
# probably is not going to change

ERROR_PORT_UNREACHABLE = 1234
ERROR_NETWORK_UNREACHABLE = 1231
ERROR_CONNECTION_REFUSED = 1225
ERROR_IO_PENDING = 997
ERROR_OPERATION_ABORTED = 995
WAIT_TIMEOUT = 258
ERROR_NETNAME_DELETED = 64
ERROR_HANDLE_EOF = 38

INFINITE = -1

SO_UPDATE_CONNECT_CONTEXT = 0x7010
SO_UPDATE_ACCEPT_CONTEXT = 0x700B

