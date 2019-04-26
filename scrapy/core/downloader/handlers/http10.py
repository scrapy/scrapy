"""Download handlers for http and https schemes
"""
from twisted.internet import reactor
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_unicode


class HTTP10DownloadHandler(object):
    lazy = False

    def __init__(self, settings):
        self.HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
        self.ClientContextFactory = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self.HTTPClientFactory(request)
        self._connect(factory)
        return factory.deferred

    def _connect(self, factory):
        host, port = to_unicode(factory.host), factory.port
        if factory.scheme == b'https':
            return reactor.connectSSL(host, port, factory,
                                      self.ClientContextFactory())
        else:
            return reactor.connectTCP(host, port, factory)
