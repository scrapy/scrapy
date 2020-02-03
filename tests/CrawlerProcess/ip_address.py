from urllib.parse import urlparse

from twisted.internet import defer
from twisted.internet.base import ThreadedResolver
from twisted.internet.interfaces import IResolverSimple
from zope.interface.declarations import implementer

from scrapy import Spider, Request
from scrapy.crawler import CrawlerProcess

from tests.mockserver import MockServer


@implementer(IResolverSimple)
class MockThreadedResolver(ThreadedResolver):
    """
    Resolves all names to localhost
    """

    @classmethod
    def from_crawler(cls, crawler, reactor):
        return cls(reactor)

    def install_on_reactor(self):
        self.reactor.installResolver(self)

    def getHostByName(self, name, timeout=None):
        return defer.succeed("127.0.0.1")


class LocalhostSpider(Spider):
    name = "localhost_spider"

    def start_requests(self):
        yield Request(self.url)

    def parse(self, response):
        netloc = urlparse(response.url).netloc
        self.logger.info("Host: %s" % netloc.split(":")[0])
        self.logger.info("Type: %s" % type(response.ip_address))
        self.logger.info("IP address: %s" % response.ip_address)


with MockServer() as mockserver:
    settings = {"DNS_RESOLVER": __name__ + ".MockThreadedResolver"}
    process = CrawlerProcess(settings)

    port = urlparse(mockserver.http_address).port
    url = "http://not.a.real.domain:{port}/echo?body=test".format(port=port)
    process.crawl(LocalhostSpider, url=url)
    process.start()
