"""Download handlers for http and https schemes
"""
from twisted.internet import reactor

from scrapy.utils.misc import load_object, create_instance
from scrapy.utils.python import to_unicode


class HTTP10DownloadHandler(object):
    lazy = False

    def __init__(self, crawler):
        self.HTTPClientFactory = load_object(crawler.settings['DOWNLOADER_HTTPCLIENTFACTORY'])
        self.ClientContextFactory = load_object(crawler.settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        self._crawler = crawler
        self._settings = crawler.settings

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self.HTTPClientFactory(request)
        self._connect(factory)
        return factory.deferred

    def _connect(self, factory):
        host, port = to_unicode(factory.host), factory.port
        if factory.scheme == b'https':
            client_context_factory = create_instance(
                self.ClientContextFactory,
                settings=self._settings,
                crawler=self._crawler,
            )
            return reactor.connectSSL(host, port, factory, client_context_factory)
        else:
            return reactor.connectTCP(host, port, factory)
