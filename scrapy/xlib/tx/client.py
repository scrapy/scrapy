# -*- test-case-name: twisted.web.test.test_webclient,twisted.web.test.test_agent -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTTP client.
"""

from __future__ import division, absolute_import

import os

try:
    from urlparse import urlunparse
    from urllib import splithost, splittype
except ImportError:
    from urllib.parse import splithost, splittype
    from urllib.parse import urlunparse as _urlunparse

    def urlunparse(parts):
        result = _urlunparse(tuple([p.decode("charmap") for p in parts]))
        return result.encode("charmap")
import zlib

from zope.interface import implementer

from twisted.python import log
from twisted.python.failure import Failure
from twisted.web import http
from twisted.internet import defer, protocol, task, reactor
from twisted.internet.interfaces import IProtocol
from twisted.internet.endpoints import TCP4ClientEndpoint, SSL4ClientEndpoint
from twisted.python import failure
from twisted.python.components import proxyForInterface
from twisted.web import error
from twisted.web.iweb import UNKNOWN_LENGTH, IBodyProducer, IResponse
from twisted.web.http_headers import Headers

from twisted.web.client import (
    PartialDownloadError, FileBodyProducer,
    CookieAgent, GzipDecoder, ContentDecoderAgent, RedirectAgent,
    Agent, ProxyAgent, HTTPConnectionPool, readBody,
)


# The code which follows is based on the new HTTP client implementation.  It
# should be significantly better than anything above, though it is not yet
# feature equivalent.

from twisted.web._newclient import Response
from twisted.web._newclient import ResponseDone, ResponseFailed


__all__ = [
    'PartialDownloadError',
    'ResponseDone', 'Response', 'ResponseFailed', 'Agent', 'CookieAgent',
    'ProxyAgent', 'ContentDecoderAgent', 'GzipDecoder', 'RedirectAgent',
    'HTTPConnectionPool', 'readBody']
