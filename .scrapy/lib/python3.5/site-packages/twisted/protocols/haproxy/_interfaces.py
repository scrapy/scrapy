# -*- test-case-name: twisted.protocols.haproxy.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interfaces used by the PROXY protocol modules.
"""

import zope.interface


class IProxyInfo(zope.interface.Interface):
    """
    Data container for PROXY protocol header data.
    """

    header = zope.interface.Attribute(
        "The raw byestring that represents the PROXY protocol header.",
    )
    source = zope.interface.Attribute(
        "An L{twisted.internet.interfaces.IAddress} representing the "
        "connection source."
    )
    destination = zope.interface.Attribute(
        "An L{twisted.internet.interfaces.IAddress} representing the "
        "connection destination."
    )



class IProxyParser(zope.interface.Interface):
    """
    Streaming parser that handles PROXY protocol headers.
    """

    def feed(self, data):
        """
        Consume a chunk of data and attempt to parse it.

        @param data: A bytestring.
        @type data: bytes

        @return: A two-tuple containing, in order, an L{IProxyInfo} and any
            bytes fed to the parser that followed the end of the header.  Both
            of these values are None until a complete header is parsed.

        @raises InvalidProxyHeader: If the bytes fed to the parser create an
            invalid PROXY header.
        """


    def parse(self, line):
        """
        Parse a bytestring as a full PROXY protocol header line.

        @param line: A bytestring that represents a valid HAProxy PROXY
            protocol header line.
        @type line: bytes

        @return: An L{IProxyInfo} containing the parsed data.

        @raises InvalidProxyHeader: If the bytestring does not represent a
            valid PROXY header.
        """
