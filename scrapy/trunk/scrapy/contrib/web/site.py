"""Twisted website object as django

################################################################################
## Simple Usage example:

from twisted.internet import reactor
from scrapy.contrib.web.http import WebSite, HttpResponse

def helloword(request):
   return HttpResponse('Hello World!')

def hello(request, name):
    return HttpResponse('Hello %s' % name)

urls = (
        ('^hello/(?P<name>\w+)/$', hello),
        ('^$', helloword),
        )


resource = WebResource(urls)
site = WebSite(port=8081, resource=resource)
reactor.run()

# now go to http://localhost:8081/



################################################################################
## Complex usage example:

from twisted.internet import reactor, defer
from scrapy.contrib.web.http import WebSite, HttpResponse

def delayed(request):
    def _callback(result):
        return HttpResponse('Heavy task completed: %s' % result)

    def _errback(_failure):
        return HttpResponse('Internal Server Error: %s' % _failure, status=500)

    def heavytask(_):
        import random
        assert random.randint(0,1), "Exception found processing request"
        return _

    d = defer.Deferred().addCallback(heavytask)
    d.addCallbacks(_callback, _errback)
    reactor.callLater(1, d.callback, "Well done")
    return d

urls = (('^delayed/$', delayed),)

resource = WebResource(urls)
site = WebSite(port=8081, resource=resource)
reactor.run()

"""

import re

from twisted.web import server, resource
from twisted.internet import reactor
from scrapy.utils.defer import mustbe_deferred

from .http import HttpResponse, build_httprequest


def urlresolver(urls, path):
    """Simple path to view mapper"""
    path = path.lstrip('/')
    for pathre, view in urls:
        m = re.search(pathre, path)
        if m:
            kwargs = m.groupdict()
            args = () if kwargs else m.groups()
            return view, args, kwargs
    return None, (), {}


class WebSite(server.Site):
    def __init__(self, port=None, *args, **kwargs):
        server.Site.__init__(self, *args, **kwargs)
        if port:
            self.bind(port)

    def bind(self, port):
        from scrapy.core.engine import scrapyengine
        scrapyengine.listenTCP(port, self)


class WebResource(resource.Resource):
    """Translate twisted web approach to django alike way"""
    isLeaf = True
    debug = True

    def __init__(self, urls, timeout=3, urlresolver=urlresolver):
        resource.Resource.__init__(self)
        self.urlresolver = urlresolver
        self.timeout = timeout
        self.urls = urls

    def render(self, twistedrequest):
        httprequest = build_httprequest(twistedrequest)

        def _send_response(response):
            assert isinstance(response, HttpResponse), 'view should return a HttpResponse object'
            twistedrequest.setResponseCode(response.status_code or 200)
            for key, val in response.items():
                twistedrequest.setHeader(key, response[key])
            twistedrequest.write(response.content)
            twistedrequest.finish()

        def _on_error(_failure):
            content = _failure.getTraceback() if self.debug else 'Internal Error'
            response = HttpResponse(content=str(_failure), status=500)
            return _send_response(response)

        view, args, kwargs = self.urlresolver(self.urls, httprequest.path)
        if not view:
            response = HttpResponse(content='Not Found', status=404)
            _send_response(response)
            return server.NOT_DONE_YET

        deferred = mustbe_deferred(view, httprequest, *args, **kwargs)
        deferred.addCallback(_send_response)
        deferred.addErrback(_on_error)
        if not deferred.timeoutCall:
            deferred.setTimeout(self.timeout)

        return server.NOT_DONE_YET


