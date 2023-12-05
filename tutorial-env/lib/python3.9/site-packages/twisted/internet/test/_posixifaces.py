# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
POSIX implementation of local network interface enumeration.
"""


import socket
import sys
from ctypes import (
    CDLL,
    POINTER,
    Structure,
    c_char_p,
    c_int,
    c_ubyte,
    c_uint8,
    c_uint32,
    c_ushort,
    c_void_p,
    cast,
    pointer,
)
from ctypes.util import find_library
from socket import AF_INET, AF_INET6, inet_ntop
from typing import Any, List, Tuple

from twisted.python.compat import nativeString

libc = CDLL(find_library("c") or "")

if sys.platform.startswith("freebsd") or sys.platform == "darwin":
    _sockaddrCommon: List[Tuple[str, Any]] = [
        ("sin_len", c_uint8),
        ("sin_family", c_uint8),
    ]
else:
    _sockaddrCommon: List[Tuple[str, Any]] = [
        ("sin_family", c_ushort),
    ]


class in_addr(Structure):
    _fields_ = [
        ("in_addr", c_ubyte * 4),
    ]


class in6_addr(Structure):
    _fields_ = [
        ("in_addr", c_ubyte * 16),
    ]


class sockaddr(Structure):
    _fields_ = _sockaddrCommon + [
        ("sin_port", c_ushort),
    ]


class sockaddr_in(Structure):
    _fields_ = _sockaddrCommon + [
        ("sin_port", c_ushort),
        ("sin_addr", in_addr),
    ]


class sockaddr_in6(Structure):
    _fields_ = _sockaddrCommon + [
        ("sin_port", c_ushort),
        ("sin_flowinfo", c_uint32),
        ("sin_addr", in6_addr),
    ]


class ifaddrs(Structure):
    pass


ifaddrs_p = POINTER(ifaddrs)
ifaddrs._fields_ = [
    ("ifa_next", ifaddrs_p),
    ("ifa_name", c_char_p),
    ("ifa_flags", c_uint32),
    ("ifa_addr", POINTER(sockaddr)),
    ("ifa_netmask", POINTER(sockaddr)),
    ("ifa_dstaddr", POINTER(sockaddr)),
    ("ifa_data", c_void_p),
]

getifaddrs = libc.getifaddrs
getifaddrs.argtypes = [POINTER(ifaddrs_p)]
getifaddrs.restype = c_int

freeifaddrs = libc.freeifaddrs
freeifaddrs.argtypes = [ifaddrs_p]


def _maybeCleanupScopeIndex(family, packed):
    """
    On FreeBSD, kill the embedded interface indices in link-local scoped
    addresses.

    @param family: The address family of the packed address - one of the
        I{socket.AF_*} constants.

    @param packed: The packed representation of the address (ie, the bytes of a
        I{in_addr} field).
    @type packed: L{bytes}

    @return: The packed address with any FreeBSD-specific extra bits cleared.
    @rtype: L{bytes}

    @see: U{https://twistedmatrix.com/trac/ticket/6843}
    @see: U{http://www.freebsd.org/doc/en/books/developers-handbook/ipv6.html#ipv6-scope-index}

    @note: Indications are that the need for this will be gone in FreeBSD >=10.
    """
    if sys.platform.startswith("freebsd") and packed[:2] == b"\xfe\x80":
        return packed[:2] + b"\x00\x00" + packed[4:]
    return packed


def _interfaces():
    """
    Call C{getifaddrs(3)} and return a list of tuples of interface name, address
    family, and human-readable address representing its results.
    """
    ifaddrs = ifaddrs_p()
    if getifaddrs(pointer(ifaddrs)) < 0:
        raise OSError()
    results = []
    try:
        while ifaddrs:
            if ifaddrs[0].ifa_addr:
                family = ifaddrs[0].ifa_addr[0].sin_family
                if family == AF_INET:
                    addr = cast(ifaddrs[0].ifa_addr, POINTER(sockaddr_in))
                elif family == AF_INET6:
                    addr = cast(ifaddrs[0].ifa_addr, POINTER(sockaddr_in6))
                else:
                    addr = None

                if addr:
                    packed = bytes(addr[0].sin_addr.in_addr[:])
                    packed = _maybeCleanupScopeIndex(family, packed)
                    results.append(
                        (ifaddrs[0].ifa_name, family, inet_ntop(family, packed))
                    )

            ifaddrs = ifaddrs[0].ifa_next
    finally:
        freeifaddrs(ifaddrs)
    return results


def posixGetLinkLocalIPv6Addresses():
    """
    Return a list of strings in colon-hex format representing all the link local
    IPv6 addresses available on the system, as reported by I{getifaddrs(3)}.
    """
    retList = []
    for (interface, family, address) in _interfaces():
        interface = nativeString(interface)
        address = nativeString(address)
        if family == socket.AF_INET6 and address.startswith("fe80:"):
            retList.append(f"{address}%{interface}")
    return retList
