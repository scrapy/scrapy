# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division

from twisted.internet.endpoints import (
    _SystemdParser, _TCP6ServerParser, _StandardIOParser,
    _TLSClientEndpointParser)

from twisted.protocols.haproxy._parser import (
    HAProxyServerParser as _HAProxyServerParser
)

systemdEndpointParser = _SystemdParser()
tcp6ServerEndpointParser = _TCP6ServerParser()
stdioEndpointParser = _StandardIOParser()
tlsClientEndpointParser = _TLSClientEndpointParser()
_haProxyServerEndpointParser = _HAProxyServerParser()
