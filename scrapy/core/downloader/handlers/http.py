"""Download handlers for http and https schemes"""

from twisted.internet import reactor

from scrapy.exceptions import NotSupported
from scrapy.utils.misc import load_object
from scrapy import optional_features

ssl_supported = 'ssl' in optional_features


class HttpDownloadHandler(object):

    def __init__(self, settings):
        self.HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
        self.ClientContextFactory = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self.HTTPClientFactory(request)
        host, port = factory.host, factory.port
        if factory.scheme == 'https':
            if ssl_supported:
                ccf = self.ClientContextFactory(request)
                reactor.connectSSL(host, port, factory, ccf)
            else:
                raise NotSupported("HTTPS not supported: install pyopenssl library")
        else:
            reactor.connectTCP(host, port, factory)

        return factory.deferred
