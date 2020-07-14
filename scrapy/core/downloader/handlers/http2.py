import warnings

from scrapy.core.downloader.tls import openssl_methods
from scrapy.core.http2.agent import H2Agent, H2ConnectionPool
from scrapy.http.request import Request
from scrapy.settings import Settings
from scrapy.utils.misc import create_instance, load_object


class H2DownloadHandler:
    def __init__(self, settings: Settings, crawler=None):
        self._crawler = crawler

        from twisted.internet import reactor
        self._pool = H2ConnectionPool(reactor, settings)

        self._ssl_method = openssl_methods[settings.get('DOWNLOADER_CLIENT_TLS_METHOD')]
        self._context_factory_cls = load_object(settings['DOWNLOADER_CLIENTCONTEXTFACTORY'])
        # try method-aware context factory
        try:
            self._context_factory = create_instance(
                objcls=self._context_factory_cls,
                settings=settings,
                crawler=crawler,
                method=self._ssl_method,
            )
        except TypeError:
            # use context factory defaults
            self._context_factory = create_instance(
                objcls=self._context_factory_cls,
                settings=settings,
                crawler=crawler,
            )
            msg = """
         '%s' does not accept `method` argument (type OpenSSL.SSL method,\
         e.g. OpenSSL.SSL.SSLv23_METHOD) and/or `tls_verbose_logging` argument and/or `tls_ciphers` argument.\
         Please upgrade your context factory class to handle them or ignore them.""" % (
                settings['DOWNLOADER_CLIENTCONTEXTFACTORY'],)
            warnings.warn(msg)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider):
        from twisted.internet import reactor

        agent = H2Agent(reactor, self._pool, self._context_factory)
        d = agent.request(request)

        def print_result(result):
            print(result)
            return result

        d.addCallback(print_result)
        return d
