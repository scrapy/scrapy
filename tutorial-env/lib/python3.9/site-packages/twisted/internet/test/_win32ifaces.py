# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Windows implementation of local network interface enumeration.
"""

from ctypes import (  # type: ignore[attr-defined]
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_int,
    c_void_p,
    cast,
    create_string_buffer,
    create_unicode_buffer,
    wstring_at,
)
from socket import AF_INET6, SOCK_STREAM, socket

WS2_32 = WinDLL("ws2_32")

SOCKET = c_int
DWORD = c_int
LPVOID = c_void_p
LPSOCKADDR = c_void_p
LPWSAPROTOCOL_INFO = c_void_p
LPTSTR = c_void_p
LPDWORD = c_void_p
LPWSAOVERLAPPED = c_void_p
LPWSAOVERLAPPED_COMPLETION_ROUTINE = c_void_p

# http://msdn.microsoft.com/en-us/library/ms741621(v=VS.85).aspx
# int WSAIoctl(
#         __in   SOCKET s,
#         __in   DWORD dwIoControlCode,
#         __in   LPVOID lpvInBuffer,
#         __in   DWORD cbInBuffer,
#         __out  LPVOID lpvOutBuffer,
#         __in   DWORD cbOutBuffer,
#         __out  LPDWORD lpcbBytesReturned,
#         __in   LPWSAOVERLAPPED lpOverlapped,
#         __in   LPWSAOVERLAPPED_COMPLETION_ROUTINE lpCompletionRoutine
#       );
WSAIoctl = WS2_32.WSAIoctl
WSAIoctl.argtypes = [
    SOCKET,
    DWORD,
    LPVOID,
    DWORD,
    LPVOID,
    DWORD,
    LPDWORD,
    LPWSAOVERLAPPED,
    LPWSAOVERLAPPED_COMPLETION_ROUTINE,
]
WSAIoctl.restype = c_int

# http://msdn.microsoft.com/en-us/library/ms741516(VS.85).aspx
# INT WSAAPI WSAAddressToString(
#         __in      LPSOCKADDR lpsaAddress,
#         __in      DWORD dwAddressLength,
#         __in_opt  LPWSAPROTOCOL_INFO lpProtocolInfo,
#         __inout   LPTSTR lpszAddressString,
#         __inout   LPDWORD lpdwAddressStringLength
#       );
WSAAddressToString = WS2_32.WSAAddressToStringW
WSAAddressToString.argtypes = [LPSOCKADDR, DWORD, LPWSAPROTOCOL_INFO, LPTSTR, LPDWORD]
WSAAddressToString.restype = c_int


SIO_ADDRESS_LIST_QUERY = 0x48000016
WSAEFAULT = 10014


class SOCKET_ADDRESS(Structure):
    _fields_ = [("lpSockaddr", c_void_p), ("iSockaddrLength", c_int)]


def make_SAL(ln):
    class SOCKET_ADDRESS_LIST(Structure):
        _fields_ = [("iAddressCount", c_int), ("Address", SOCKET_ADDRESS * ln)]

    return SOCKET_ADDRESS_LIST


def win32GetLinkLocalIPv6Addresses():
    """
    Return a list of strings in colon-hex format representing all the link local
    IPv6 addresses available on the system, as reported by
    I{WSAIoctl}/C{SIO_ADDRESS_LIST_QUERY}.
    """
    s = socket(AF_INET6, SOCK_STREAM)
    size = 4096
    retBytes = c_int()
    for i in range(2):
        buf = create_string_buffer(size)
        ret = WSAIoctl(
            s.fileno(), SIO_ADDRESS_LIST_QUERY, 0, 0, buf, size, byref(retBytes), 0, 0
        )

        # WSAIoctl might fail with WSAEFAULT, which means there was not enough
        # space in the buffer we gave it.  There's no way to check the errno
        # until Python 2.6, so we don't even try. :/ Maybe if retBytes is still
        # 0 another error happened, though.
        if ret and retBytes.value:
            size = retBytes.value
        else:
            break

    # If it failed, then we'll just have to give up.  Still no way to see why.
    if ret:
        raise RuntimeError("WSAIoctl failure")

    addrList = cast(buf, POINTER(make_SAL(0)))
    addrCount = addrList[0].iAddressCount
    addrList = cast(buf, POINTER(make_SAL(addrCount)))

    addressStringBufLength = 1024
    addressStringBuf = create_unicode_buffer(addressStringBufLength)

    retList = []
    for i in range(addrList[0].iAddressCount):
        retBytes.value = addressStringBufLength
        address = addrList[0].Address[i]
        ret = WSAAddressToString(
            address.lpSockaddr,
            address.iSockaddrLength,
            0,
            addressStringBuf,
            byref(retBytes),
        )
        if ret:
            raise RuntimeError("WSAAddressToString failure")
        retList.append(wstring_at(addressStringBuf))
    return [addr for addr in retList if "%" in addr]
