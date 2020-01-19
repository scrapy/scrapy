"""Download handlers for http and https schemes
"""
from twisted.internet import reactor
from scrapy.utils.misc import load_object, create_instance
from scrapy.utils.python import to_unicode


class HTTP10DownloadHandler(object):
    lazy = False

    def __init__(self, settings):
        self.HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
        self.ClientContextFactory = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        self._settings = settings

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self.HTTPClientFactory(request)
        self._connect(factory)
        return factory.deferred

    def _connect(self, factory):
        host, port = to_unicode(factory.host), factory.port
        if factory.scheme == b'https':
            client_context_factory = create_instance(self.ClientContextFactory, settings=self._settings, crawler=None)
            return reactor.connectSSL(host, port, factory, client_context_factory)
        else:
            return reactor.connectTCP(host, port, factory)
