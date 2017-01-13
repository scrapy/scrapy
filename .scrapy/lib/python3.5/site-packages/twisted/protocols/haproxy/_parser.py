# -*- test-case-name: twisted.protocols.haproxy.test.test_parser -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Parser for 'haproxy:' string endpoint.
"""

from zope.interface import implementer
from twisted.plugin import IPlugin

from twisted.internet.endpoints import (
    quoteStringArgument, serverFromString, IStreamServerEndpointStringParser
)
from twisted.python.compat import iteritems

from . import proxyEndpoint


def unparseEndpoint(args, kwargs):
    """
    Un-parse the already-parsed args and kwargs back into endpoint syntax.

    @param args: C{:}-separated arguments
    @type args: L{tuple} of native L{str}

    @param kwargs: C{:} and then C{=}-separated keyword arguments

    @type arguments: L{tuple} of native L{str}

    @return: a string equivalent to the original format which this was parsed
        as.
    @rtype: native L{str}
    """

    description = ':'.join(
        [quoteStringArgument(str(arg)) for arg in args] +
        sorted(['%s=%s' % (quoteStringArgument(str(key)),
                    quoteStringArgument(str(value)))
         for key, value in iteritems(kwargs)
        ]))
    return description



@implementer(IPlugin, IStreamServerEndpointStringParser)
class HAProxyServerParser(object):
    """
    Stream server endpoint string parser for the HAProxyServerEndpoint type.

    @ivar prefix: See L{IStreamServerEndpointStringParser.prefix}.
    """
    prefix = "haproxy"

    def parseStreamServer(self, reactor, *args, **kwargs):
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
