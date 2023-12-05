# -*- test-case-name: twisted.protocols.haproxy.test.test_parser -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Parser for 'haproxy:' string endpoint.
"""
from typing import Mapping, Tuple

from zope.interface import implementer

from twisted.internet import interfaces
from twisted.internet.endpoints import (
    IStreamServerEndpointStringParser,
    _WrapperServerEndpoint,
    quoteStringArgument,
    serverFromString,
)
from twisted.plugin import IPlugin
from . import proxyEndpoint


def unparseEndpoint(args: Tuple[object, ...], kwargs: Mapping[str, object]) -> str:
    """
    Un-parse the already-parsed args and kwargs back into endpoint syntax.

    @param args: C{:}-separated arguments

    @param kwargs: C{:} and then C{=}-separated keyword arguments

    @return: a string equivalent to the original format which this was parsed
        as.
    """

    description = ":".join(
        [quoteStringArgument(str(arg)) for arg in args]
        + sorted(
            "{}={}".format(
                quoteStringArgument(str(key)), quoteStringArgument(str(value))
            )
            for key, value in kwargs.items()
        )
    )
    return description


@implementer(IPlugin, IStreamServerEndpointStringParser)
class HAProxyServerParser:
    """
    Stream server endpoint string parser for the HAProxyServerEndpoint type.

    @ivar prefix: See L{IStreamServerEndpointStringParser.prefix}.
    """

    prefix = "haproxy"

    def parseStreamServer(
        self, reactor: interfaces.IReactorCore, *args: object, **kwargs: object
    ) -> _WrapperServerEndpoint:
        """
        Parse a stream server endpoint from a reactor and string-only arguments
        and keyword arguments.

        @param reactor: The reactor.

        @param args: The parsed string arguments.

        @param kwargs: The parsed keyword arguments.

        @return: a stream server endpoint
        @rtype: L{IStreamServerEndpoint}
        """
        subdescription = unparseEndpoint(args, kwargs)
        wrappedEndpoint = serverFromString(reactor, subdescription)
        return proxyEndpoint(wrappedEndpoint)
