"""
Download handlers for different schemes
"""
from __future__ import with_statement

import os
import urlparse

from twisted.web.client import HTTPClientFactory
from twisted.internet import defer, reactor
from twisted.web import error as web_error

try:
    from twisted.internet import ssl
except ImportError:
    pass

from scrapy import optional_features
from scrapy.core import signals
from scrapy.http import Request, Response, Headers
from scrapy.core.exceptions import UsageError, HttpException, NotSupported
from scrapy.utils.defer import defer_succeed
from scrapy.conf import settings

from scrapy.core.downloader.dnscache import DNSCache
from scrapy.core.downloader.responsetypes import responsetypes

default_timeout = settings.getint('DOWNLOAD_TIMEOUT')
default_agent = settings.get('USER_AGENT')
ssl_supported = 'ssl' in optional_features

# Cache for dns lookups.
dnscache = DNSCache()

def download_any(request, spider):
    scheme = request.url.scheme
    if scheme == 'http':
        return download_http(request, spider)
    elif scheme == 'https':
        if ssl_supported:
            return download_https(request, spider)
        else:
            raise NotSupported("HTTPS not supported: install pyopenssl library")
    elif request.url.scheme == 'file':
        return download_file(request, spider)
    else:
        raise NotSupported("Unsupported URL scheme '%s' in: <%s>" % (request.url.scheme, request.url))

def create_factory(request, spider):
    """Return HTTPClientFactory for the given Request"""
    url = urlparse.urldefrag(request.url)[0]

    agent = request.headers.pop('user-agent', default_agent)
    factory = HTTPClientFactory(url=url, # never pass unicode urls to twisted
                                method=request.method,
                                postdata=request.body or None,
                                headers=request.headers,
                                agent=agent,
                                cookies=request.cookies,
                                timeout=getattr(spider, "download_timeout", default_timeout),
                                followRedirect=False)

    def _create_response(body):
        body = body or ''
        status = int(factory.status)
        headers = Headers(factory.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=url)
        r = respcls(url=request.url, status=status, headers=headers, body=body)
        signals.send_catch_log(signal=signals.request_uploaded, sender='download_http', request=request, spider=spider)
        signals.send_catch_log(signal=signals.response_downloaded, sender='download_http', response=r, spider=spider)
        return r

    def _on_success(body):
        return _create_response(body)

    def _on_error(_failure):
        ex = _failure.value
        if isinstance(ex, web_error.Error): # HttpException
            raise HttpException(ex.status, ex.message, _create_response(ex.response))
        return _failure

    factory.noisy = False
    factory.deferred.addCallbacks(_on_success, _on_error)
    return factory

def download_http(request, spider):
    """Return a deferred for the HTTP download"""
    factory = create_factory(request, spider)
    ip = dnscache.get(request.url.hostname)
    port = request.url.port
    reactor.connectTCP(ip, port or 80, factory)
    return factory.deferred

def download_https(request, spider):
    """Return a deferred for the HTTPS download"""
    factory = create_factory(request, spider)
    ip = dnscache.get(request.url.hostname)
    port = request.url.port
    contextFactory = ssl.ClientContextFactory()
    reactor.connectSSL(ip, port or 443, factory, contextFactory)
    return factory.deferred

def download_file(request, spider) :
    """Return a deferred for a file download."""
    filepath = request.url.split("file://")[1]
    with open(filepath) as f:
        body = f.read()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        response = respcls(url=request.url, body=body)

    return defer_succeed(response)
