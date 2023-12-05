# -*- test-case-name: twisted.conch.test.test_ssh -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Common functions for the SSH classes.

Maintainer: Paul Swartz
"""


import struct

from cryptography.utils import int_to_bytes

from twisted.python.deprecate import deprecated
from twisted.python.versions import Version

__all__ = ["NS", "getNS", "MP", "getMP", "ffs"]


def NS(t):
    """
    net string
    """
    if isinstance(t, str):
        t = t.encode("utf-8")
    return struct.pack("!L", len(t)) + t


def getNS(s, count=1):
    """
    get net string
    """
    ns = []
    c = 0
    for i in range(count):
        (l,) = struct.unpack("!L", s[c : c + 4])
        ns.append(s[c + 4 : 4 + l + c])
        c += 4 + l
    return tuple(ns) + (s[c:],)


def MP(number):
    if number == 0:
        return b"\000" * 4
    assert number > 0
    bn = int_to_bytes(number)
    if ord(bn[0:1]) & 128:
        bn = b"\000" + bn
    return struct.pack(">L", len(bn)) + bn


def getMP(data, count=1):
    """
    Get multiple precision integer out of the string.  A multiple precision
    integer is stored as a 4-byte length followed by length bytes of the
    integer.  If count is specified, get count integers out of the string.
    The return value is a tuple of count integers followed by the rest of
    the data.
    """
    mp = []
    c = 0
    for i in range(count):
        (length,) = struct.unpack(">L", data[c : c + 4])
        mp.append(int.from_bytes(data[c + 4 : c + 4 + length], "big"))
        c += 4 + length
    return tuple(mp) + (data[c:],)


def ffs(c, s):
    """
    first from second
    goes through the first list, looking for items in the second, returns the first one
    """
    for i in c:
        if i in s:
            return i


@deprecated(Version("Twisted", 16, 5, 0))
def install():
    # This used to install gmpy, but is technically public API, so just do
    # nothing.
    pass
