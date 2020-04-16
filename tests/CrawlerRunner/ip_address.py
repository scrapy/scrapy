from urllib.parse import urlparse

from twisted.internet import reactor
from twisted.names.client import createResolver

from scrapy import Spider, Request
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging

from tests.mockserver import MockServer, MockDNSServer


class LocalhostSpider(Spider):
    name = "localhost_spider"

    def start_requests(self):
        yield Request(self.url)

    def parse(self, response):
        netloc = urlparse(response.url).netloc
        self.logger.info("Host: %s" % netloc.split(":")[0])
        self.logger.info("Type: %s" % type(response.ip_address))
        self.logger.info("IP address: %s" % response.ip_address)


if __name__ == "__main__":
    with MockServer() as mock_http_server, MockDNSServer() as mock_dns_server:
        port = urlparse(mock_http_server.http_address).port
        url = "http://not.a.real.domain:{port}/echo".format(port=port)

        servers = [(mock_dns_server.host, mock_dns_server.port)]
        reactor.installResolver(createResolver(servers=servers))

        configure_logging()
        runner = CrawlerRunner()
        d = runner.crawl(LocalhostSpider, url=url)
        d.addBoth(lambda _: reactor.stop())
        reactor.run()
