"""Download handlers for http and https schemes"""

from twisted.internet import reactor

from scrapy.core import signals
from scrapy.core.exceptions import NotSupported
from scrapy.utils.signal import send_catch_log
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy import optional_features

ssl_supported = 'ssl' in optional_features
if ssl_supported:
    from twisted.internet.ssl import ClientContextFactory


HTTPClientFactory = load_object(settings['DOWNLOADER_HTTPCLIENTFACTORY'])
default_timeout = settings.getint('DOWNLOAD_TIMEOUT')

def _create_factory(request, spider):
    def _download_signals(response):
        send_catch_log(signal=signals.request_uploaded, \
                sender='download_http', request=request, spider=spider)
        send_catch_log(signal=signals.response_downloaded, \
                sender='download_http', response=response, spider=spider)
        return response

    timeout = getattr(spider, "download_timeout", None) or default_timeout
    factory = HTTPClientFactory(request, timeout)
    factory.deferred.addCallbacks(_download_signals)
    return factory


def _connect(factory):
    host, port = factory.host, factory.port
    if factory.scheme == 'https':
        if ssl_supported:
            return reactor.connectSSL(host, port, factory, ClientContextFactory())
        raise NotSupported("HTTPS not supported: install pyopenssl library")
    else:
        return reactor.connectTCP(host, port, factory)


def download_http(request, spider):
    """Return a deferred for the HTTP download"""
    factory = _create_factory(request, spider)
    _connect(factory)
    return factory.deferred


