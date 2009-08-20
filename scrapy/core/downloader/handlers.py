"""
Download handlers for different schemes
"""
from __future__ import with_statement

import urlparse

from twisted.internet import reactor
try:
    from twisted.internet import ssl
except ImportError:
    pass

from scrapy import optional_features
from scrapy.core import signals
from scrapy.http import Headers
from scrapy.core.exceptions import NotSupported
from scrapy.utils.defer import defer_succeed
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.signal import send_catch_log
from scrapy.core.downloader.responsetypes import responsetypes
from scrapy.core.downloader.webclient import ScrapyHTTPClientFactory
from scrapy.conf import settings


default_timeout = settings.getint('DOWNLOAD_TIMEOUT')
ssl_supported = 'ssl' in optional_features

def download_any(request, spider):
    scheme = urlparse_cached(request).scheme
    if scheme == 'http':
        return download_http(request, spider)
    elif scheme == 'https':
        if ssl_supported:
            return download_https(request, spider)
        else:
            raise NotSupported("HTTPS not supported: install pyopenssl library")
    elif scheme == 'file':
        return download_file(request, spider)
    else:
        raise NotSupported("Unsupported URL scheme '%s' in: <%s>" % (scheme, request.url))

def create_factory(request, spider):
    """Return HTTPClientFactory for the given Request"""
    url = urlparse.urldefrag(request.url)[0]
    timeout = getattr(spider, "download_timeout", None) or default_timeout
    factory = ScrapyHTTPClientFactory.from_request(request, timeout)

    def _create_response(body):
        body = body or ''
        status = int(factory.status)
        headers = Headers(factory.response_headers)
        respcls = responsetypes.from_args(headers=headers, url=url)
        r = respcls(url=request.url, status=status, headers=headers, body=body)
        send_catch_log(signal=signals.request_uploaded, sender='download_http', \
            request=request, spider=spider)
        send_catch_log(signal=signals.response_downloaded, sender='download_http', \
            response=r, spider=spider)
        return r

    factory.deferred.addCallbacks(_create_response)
    return factory

def download_http(request, spider):
    """Return a deferred for the HTTP download"""
    factory = create_factory(request, spider)
    url = urlparse_cached(request)
    port = url.port
    reactor.connectTCP(url.hostname, port or 80, factory)
    return factory.deferred

def download_https(request, spider):
    """Return a deferred for the HTTPS download"""
    factory = create_factory(request, spider)
    url = urlparse_cached(request)
    port = url.port
    contextFactory = ssl.ClientContextFactory()
    reactor.connectSSL(url.hostname, port or 443, factory, contextFactory)
    return factory.deferred

def download_file(request, spider) :
    """Return a deferred for a file download."""
    filepath = request.url.split("file://")[1]
    with open(filepath) as f:
        body = f.read()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        response = respcls(url=request.url, body=body)

    return defer_succeed(response)
