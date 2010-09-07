"""Download handlers for http and https schemes"""

from twisted.internet import reactor

from scrapy.exceptions import NotSupported
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy import optional_features

ssl_supported = 'ssl' in optional_features
if ssl_supported:
    from twisted.internet.ssl import ClientContextFactory

HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
DOWNLOAD_TIMEOUT = settings.getint('DOWNLOAD_TIMEOUT')


class HttpDownloadHandler(object):

    def __init__(self, httpclientfactory=HTTPClientFactory, \
            download_timeout=DOWNLOAD_TIMEOUT):
        self.httpclientfactory = httpclientfactory
        self.download_timeout = download_timeout

    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        factory = self._create_factory(request, spider)
        self._connect(factory)
        return factory.deferred

    def _create_factory(self, request, spider):
        timeout = getattr(spider, "download_timeout", None) or self.download_timeout
        return self.httpclientfactory(request, timeout)

    def _connect(self, factory):
        host, port = factory.host, factory.port
        if factory.scheme == 'https':
            if ssl_supported:
                return reactor.connectSSL(host, port, factory, \
                        ClientContextFactory())
            raise NotSupported("HTTPS not supported: install pyopenssl library")
        else:
            return reactor.connectTCP(host, port, factory)
