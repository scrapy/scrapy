# -*- test-case-name: twisted.conch.test.test_common -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Backported functions from Cryptography to support older versions.

These functions can be obtained from C{cryptography.utils} instead, from
version 1.1 onwards.
"""
from __future__ import absolute_import, division
import binascii
import struct

def intFromBytes(data, byteorder, signed=False):
    """
    Convert an integer in packed form to a Python L{int}.

    @type data: L{bytes}
    @param data: The packed integer.

    @type byteorder: L{str}
    @param byteorder: The byte order the data is in.  Only C{'big'} is
        currently supported.

    @type signed: L{bool}
    @param signed: C{True} for signed, C{False} for unsigned.

    @rtype: L{int}
    @return: The decoded integer.
    """
    assert byteorder == 'big'
    assert not signed

    if len(data) % 4 != 0:
        data = (b'\x00' * (4 - (len(data) % 4))) + data

    result = 0

    while len(data) > 0:
        digit, = struct.unpack('>I', data[:4])
        result = (result << 32) + digit
        data = data[4:]

    return result



def intToBytes(integer, length=None):
    """
    Convert a Python L{int} to packed data.

    @type integer: L{int}
    @param integer: The integer to pack.

    @type length: L{int} or L{None}
    @param length: The length to pad the result to, or L{None} for no padding.

    @rtype: L{bytes}
    @return: The packed integer.
    """
    hexString = '%x' % (integer,)
    if length is None:
        n = len(hexString)
    else:
        n = length * 2
    return binascii.unhexlify(hexString.zfill(n + (n & 1)))
