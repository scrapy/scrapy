# -*- test-case-name: twisted.test.test_strports -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Construct listening port services from a simple string description.

@see: L{twisted.internet.endpoints.serverFromString}
@see: L{twisted.internet.endpoints.clientFromString}
"""

from __future__ import absolute_import, division

import warnings

from twisted.internet import endpoints
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.versions import Version
from twisted.python.compat import _PY3
from twisted.application.internet import StreamServerEndpointService



def parse(description, factory, default='tcp'):
    """
    This function is deprecated as of Twisted 10.2.

    @see: L{twisted.internet.endpoints.serverFromString}
    """
    return endpoints._parseServer(description, factory, default)

deprecatedModuleAttribute(
    Version("Twisted", 10, 2, 0),
    "in favor of twisted.internet.endpoints.serverFromString",
    __name__, "parse")



_DEFAULT = object()

def service(description, factory, default=_DEFAULT, reactor=None):
    """
    Return the service corresponding to a description.

    @param description: The description of the listening port, in the syntax
        described by L{twisted.internet.endpoints.serverFromString}.

    @type description: C{str}

    @param factory: The protocol factory which will build protocols for
        connections to this service.

    @type factory: L{twisted.internet.interfaces.IProtocolFactory}

    @type default: C{str} or L{None}

    @param default: Do not use this parameter. It has been deprecated since
        Twisted 10.2.0.

    @rtype: C{twisted.application.service.IService}

    @return: the service corresponding to a description of a reliable
        stream server.

    @see: L{twisted.internet.endpoints.serverFromString}
    """
    if reactor is None:
        from twisted.internet import reactor
    if default is _DEFAULT:
        default = None
    else:
        message = "The 'default' parameter was deprecated in Twisted 10.2.0."
        if default is not None:
            message += (
                "  Use qualified endpoint descriptions; for example, "
                "'tcp:%s'." % (description,))
        warnings.warn(
            message=message, category=DeprecationWarning, stacklevel=2)
    svc = StreamServerEndpointService(
        endpoints._serverFromStringLegacy(reactor, description, default),
        factory)
    svc._raiseSynchronously = True
    return svc



def listen(description, factory, default=None):
    """Listen on a port corresponding to a description

    @type description: C{str}
    @type factory: L{twisted.internet.interfaces.IProtocolFactory}
    @type default: C{str} or L{None}
    @rtype: C{twisted.internet.interfaces.IListeningPort}
    @return: the port corresponding to a description of a reliable
    virtual circuit server.

    See the documentation of the C{parse} function for description
    of the semantics of the arguments.
    """
    from twisted.internet import reactor
    name, args, kw = parse(description, factory, default)
    return getattr(reactor, 'listen'+name)(*args, **kw)



__all__ = ['parse', 'service', 'listen']

if _PY3:
    __all3__ = ['service']
    for name in __all__[:]:
        if name not in __all3__:
            __all__.remove(name)
            del globals()[name]
    del name, __all3__
