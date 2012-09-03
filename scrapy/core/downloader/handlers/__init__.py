"""Download handlers for different schemes"""

from scrapy.exceptions import NotSupported, NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object


class DownloadHandlers(object):

    def __init__(self, settings):
        self._handlers = {}
        self._notconfigured = {}
        handlers = settings.get('DOWNLOAD_HANDLERS_BASE')
        handlers.update(settings.get('DOWNLOAD_HANDLERS', {}))
        for scheme, clspath in handlers.iteritems():
            cls = load_object(clspath)
            try:
                dh = cls(settings)
            except NotConfigured, ex:
                self._notconfigured[scheme] = str(ex)
            else:
                self._handlers[scheme] = dh.download_request

    def download_request(self, request, spider):
        scheme = urlparse_cached(request).scheme
        try:
            handler = self._handlers[scheme]
        except KeyError:
            msg = self._notconfigured.get(scheme, \
                    'no handler available for that scheme')
            raise NotSupported("Unsupported URL scheme '%s': %s" % (scheme, msg))
        return handler(request, spider)
