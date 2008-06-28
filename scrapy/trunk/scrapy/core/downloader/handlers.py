"""
Download handlers for different schemes
"""
from __future__ import with_statement

import os
import urlparse

from twisted.web.client import HTTPClientFactory
from twisted.internet import defer, reactor
from twisted.web import error as web_error

from scrapy.core import signals
from scrapy.http import Request, Response, Headers
from scrapy.core.exceptions import UsageError, HttpException
from scrapy.utils.misc import defer_succeed
from scrapy.conf import settings

def download_any(request, spider):
    u = urlparse.urlparse(request.url)
    if u.scheme == 'file':
        return download_file(request, spider)
    elif u.scheme in ('http', 'https'):
        return download_http(request, spider)
    else:
        raise UsageError("Unsupported scheme '%s' in URL: <%s>" % (u.scheme, request.url))

def download_http(request, spider):
    """This functions handles http/https downloads"""
    url = urlparse.urldefrag(request.url)[0]
    
    agent = request.headers.get('user-agent', settings.get('USER_AGENT'))
    request.headers.pop('user-agent', None)  # remove user-agent if already present
    factory = HTTPClientFactory(url=str(url), # never pass unicode urls to twisted
                                method=request.method,
                                postdata=request.body,
                                headers=request.headers,
                                agent=agent,
                                cookies=request.cookies,
                                timeout=getattr(spider, "download_timeout", None) or settings.getint('DOWNLOAD_TIMEOUT'),
                                followRedirect=False)

    def _response(body):
        body = body or ''
        status = factory.status
        parent = request.headers.get('Referer')
        headers = Headers(factory.response_headers)
        r = Response(domain=spider.domain_name, url=request.url, headers=headers, status=status, body=body, parent=parent)
        signals.send_catch_log(signal=signals.request_uploaded, sender='download_http', request=request, spider=spider)
        signals.send_catch_log(signal=signals.response_downloaded, sender='download_http', response=r, spider=spider)
        return r

    def _on_success(body):
        return _response(body)

    def _on_error(_failure):
        ex = _failure.value
        if isinstance(ex, web_error.Error): # HttpException
            raise HttpException(ex.status, ex.message, _response(ex.response))
        return _failure

    factory.noisy = False
    factory.deferred.addCallbacks(_on_success, _on_error)

    u = urlparse.urlparse(request.url)
    if u.scheme == 'https' :
        from twisted.internet import ssl
        contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(u.hostname, u.port or 443, factory, contextFactory)
    else:
        reactor.connectTCP(u.hostname, u.port or 80, factory)
    return factory.deferred

def download_file(request, spider) :
    """Return a deferred for a file download."""
    filepath = request.url.split("file://")[1]
    with open(filepath) as f:
        response = Response(domain=spider.domain_name, url=request.url, body=f.read())
    return defer_succeed(response)
