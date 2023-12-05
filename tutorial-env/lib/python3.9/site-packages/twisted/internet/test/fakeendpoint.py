# -*- test-case-name: twisted.internet.test.test_endpoints -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Fake client and server endpoint string parser plugins for testing purposes.
"""


from zope.interface.declarations import implementer

from twisted.internet.interfaces import (
    IStreamClientEndpoint,
    IStreamClientEndpointStringParserWithReactor,
    IStreamServerEndpoint,
    IStreamServerEndpointStringParser,
)
from twisted.plugin import IPlugin


@implementer(IPlugin)
class PluginBase:
    def __init__(self, pfx):
        self.prefix = pfx


@implementer(IStreamClientEndpointStringParserWithReactor)
class FakeClientParserWithReactor(PluginBase):
    def parseStreamClient(self, *a, **kw):
        return StreamClient(self, a, kw)


@implementer(IStreamServerEndpointStringParser)
class FakeParser(PluginBase):
    def parseStreamServer(self, *a, **kw):
        return StreamServer(self, a, kw)


class EndpointBase:
    def __init__(self, parser, args, kwargs):
        self.parser = parser
        self.args = args
        self.kwargs = kwargs


@implementer(IStreamClientEndpoint)
class StreamClient(EndpointBase):
    def connect(self, protocolFactory=None):
        # IStreamClientEndpoint.connect
        pass


@implementer(IStreamServerEndpoint)
class StreamServer(EndpointBase):
    def listen(self, protocolFactory=None):
        # IStreamClientEndpoint.listen
        pass


# Instantiate plugin interface providers to register them.
fake = FakeParser("fake")
fakeClientWithReactor = FakeClientParserWithReactor("crfake")
fakeClientWithReactorAndPreference = FakeClientParserWithReactor("cpfake")
