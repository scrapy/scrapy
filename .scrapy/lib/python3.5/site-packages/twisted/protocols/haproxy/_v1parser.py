# -*- test-case-name: twisted.protocols.haproxy.test.test_v1parser -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
IProxyParser implementation for version one of the PROXY protocol.
"""

from zope.interface import implementer
from twisted.internet import address

from ._exceptions import (
    convertError, InvalidProxyHeader, InvalidNetworkProtocol,
    MissingAddressData
)
from . import _info
from . import _interfaces



@implementer(_interfaces.IProxyParser)
class V1Parser(object):
    """
    PROXY protocol version one header parser.

    Version one of the PROXY protocol is a human readable format represented
    by a single, newline delimited binary string that contains all of the
    relevant source and destination data.
    """

    PROXYSTR = b'PROXY'
    UNKNOWN_PROTO = b'UNKNOWN'
    TCP4_PROTO = b'TCP4'
    TCP6_PROTO = b'TCP6'
    ALLOWED_NET_PROTOS = (
        TCP4_PROTO,
        TCP6_PROTO,
        UNKNOWN_PROTO,
    )
    NEWLINE = b'\r\n'

    def __init__(self):
        self.buffer = b''


    def feed(self, data):
        """
        Consume a chunk of data and attempt to parse it.

        @param data: A bytestring.
        @type data: L{bytes}

        @return: A two-tuple containing, in order, a
            L{_interfaces.IProxyInfo} and any bytes fed to the
            parser that followed the end of the header.  Both of these values
            are None until a complete header is parsed.

        @raises InvalidProxyHeader: If the bytes fed to the parser create an
            invalid PROXY header.
        """
        self.buffer += data
        if len(self.buffer) > 107 and self.NEWLINE not in self.buffer:
            raise InvalidProxyHeader()
        lines = (self.buffer).split(self.NEWLINE, 1)
        if not len(lines) > 1:
            return (None, None)
        self.buffer = b''
        remaining = lines.pop()
        header = lines.pop()
        info = self.parse(header)
        return (info, remaining)


    @classmethod
    def parse(cls, line):
        """
        Parse a bytestring as a full PROXY protocol header line.

        @param line: A bytestring that represents a valid HAProxy PROXY
            protocol header line.
        @type line: bytes

        @return: A L{_interfaces.IProxyInfo} containing the parsed data.

        @raises InvalidProxyHeader: If the bytestring does not represent a
            valid PROXY header.

        @raises InvalidNetworkProtocol: When no protocol can be parsed or is
            not one of the allowed values.

        @raises MissingAddressData: When the protocol is TCP* but the header
            does not contain a complete set of addresses and ports.
        """
        originalLine = line
        proxyStr = None
        networkProtocol = None
        sourceAddr = None
        sourcePort = None
        destAddr = None
        destPort = None

        with convertError(ValueError, InvalidProxyHeader):
            proxyStr, line = line.split(b' ', 1)

        if proxyStr != cls.PROXYSTR:
            raise InvalidProxyHeader()

        with convertError(ValueError, InvalidNetworkProtocol):
            networkProtocol, line = line.split(b' ', 1)

        if networkProtocol not in cls.ALLOWED_NET_PROTOS:
            raise InvalidNetworkProtocol()

        if networkProtocol == cls.UNKNOWN_PROTO:

            return _info.ProxyInfo(originalLine, None, None)

        with convertError(ValueError, MissingAddressData):
            sourceAddr, line = line.split(b' ', 1)

        with convertError(ValueError, MissingAddressData):
            destAddr, line = line.split(b' ', 1)

        with convertError(ValueError, MissingAddressData):
            sourcePort, line = line.split(b' ', 1)

        with convertError(ValueError, MissingAddressData):
            destPort = line.split(b' ')[0]

        if networkProtocol == cls.TCP4_PROTO:

            return _info.ProxyInfo(
                originalLine,
                address.IPv4Address('TCP', sourceAddr, int(sourcePort)),
                address.IPv4Address('TCP', destAddr, int(destPort)),
            )

        return _info.ProxyInfo(
            originalLine,
            address.IPv6Address('TCP', sourceAddr, int(sourcePort)),
            address.IPv6Address('TCP', destAddr, int(destPort)),
        )
