"""Download handlers for http and https schemes"""

from twisted.internet import reactor

from scrapy.exceptions import NotSupported
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy import optional_features

ssl_supported = 'ssl' in optional_features

HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
ClientContextFactory = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])


class HttpDownloadHandler(object):

    def __init__(self, httpclientfactory=HTTPClientFactory):
        self.httpclientfactory = httpclientfactory

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self.httpclientfactory(request)
        self._connect(factory)
        return factory.deferred

    def _connect(self, factory):
        host, port = factory.host, factory.port
        if factory.scheme == 'https':
            if ssl_supported:
                return reactor.connectSSL(host, port, factory, \
                        ClientContextFactory())
            raise NotSupported("HTTPS not supported: install pyopenssl library")
        else:
            return reactor.connectTCP(host, port, factory)
