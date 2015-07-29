"""Download handlers for different schemes"""

from twisted.internet import defer
import six
from scrapy.exceptions import NotSupported, NotConfigured
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy import signals


class DownloadHandlers(object):

    def __init__(self, crawler):
        self._crawler_settings = crawler.settings
        self._schemes = {} # stores acceptable schemes on instancing
        self._handlers = {} # stores instanced handlers for schemes
        self._notconfigured = {} # remembers failed handlers
        handlers = crawler.settings.get('DOWNLOAD_HANDLERS_BASE')
        handlers.update(crawler.settings.get('DOWNLOAD_HANDLERS', {}))
        for scheme, clspath in six.iteritems(handlers):
            # Allow to disable a handler just like any other
            # component (extension, middleware, etc).
            if clspath is None:
                continue
            self._schemes[scheme] = clspath

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, scheme):
        """Lazy-load the downloadhandler for a scheme
        only on the first request for that scheme.
        """
        if scheme in self._handlers:
            return self._handlers[scheme]
        if scheme in self._notconfigured:
            return None
        if scheme not in self._schemes:
            self._notconfigured[scheme] = \
                    'no handler available for that scheme'
            return None

        dhcls = load_object(self._schemes[scheme])
        try:
            dh = dhcls(self._crawler_settings)
        except NotConfigured as ex:
            self._notconfigured[scheme] = str(ex)
            return None
        else:
            self._handlers[scheme] = dh
        return self._handlers[scheme]

    def download_request(self, request, spider):
        scheme = urlparse_cached(request).scheme
        handler = self._get_handler(scheme)
        if not handler:
            raise NotSupported("Unsupported URL scheme '%s': %s" %
                    (scheme, self._notconfigured[scheme]))
        return handler.download_request(request, spider)

    @defer.inlineCallbacks
    def _close(self, *_a, **_kw):
        for dh in self._handlers.values():
            if hasattr(dh, 'close'):
                yield dh.close()
