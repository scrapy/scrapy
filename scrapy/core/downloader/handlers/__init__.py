"""Download handlers for different schemes"""

from scrapy.core.exceptions import NotSupported
from scrapy.utils.httpobj import urlparse_cached
from scrapy.conf import settings
from scrapy.utils.misc import load_object


class RequestHandlers(object):

    def __init__(self):
        self._handlers = {}
        handlers = settings.get('REQUEST_HANDLERS_BASE')
        handlers.update(settings.get('REQUEST_HANDLERS', {}))
        for scheme, cls in handlers.iteritems():
            self._handlers[scheme] = load_object(cls)

    def download_request(self, request, spider):
        scheme = urlparse_cached(request).scheme
        try:
            handler = self._handlers[scheme]
        except KeyError:
            raise NotSupported("Unsupported URL scheme '%s' in: <%s>" % (scheme, request.url))
        return handler(request, spider)


download_any = RequestHandlers().download_request
