# ruff: noqa: E402

from scrapy.utils.reactor import install_reactor

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from urllib.parse import urlparse

from twisted.names import cache, resolve
from twisted.names import hosts as hostsModule
from twisted.names.client import Resolver
from twisted.python.runtime import platform

from scrapy import Request, Spider
from scrapy.crawler import CrawlerRunner
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.log import configure_logging
from tests.mockserver import MockDNSServer, MockServer


# https://stackoverflow.com/a/32784190
def createResolver(servers=None, resolvconf=None, hosts=None):
    if hosts is None:
        hosts = b"/etc/hosts" if platform.getType() == "posix" else r"c:\windows\hosts"
    theResolver = Resolver(resolvconf, servers)
    hostResolver = hostsModule.Resolver(hosts)
    chain = [hostResolver, cache.CacheResolver(), theResolver]
    return resolve.ResolverChain(chain)


class LocalhostSpider(Spider):
    name = "localhost_spider"

    async def start(self):
        yield Request(self.url)

    def parse(self, response):
        netloc = urlparse_cached(response).netloc
        host = netloc.split(":")[0]
        self.logger.info(f"Host: {host}")
        self.logger.info(f"Type: {type(response.ip_address)}")
        self.logger.info(f"IP address: {response.ip_address}")


if __name__ == "__main__":
    from twisted.internet import reactor

    with MockServer() as mock_http_server, MockDNSServer() as mock_dns_server:
        port = urlparse(mock_http_server.http_address).port
        url = f"http://not.a.real.domain:{port}/echo"

        servers = [(mock_dns_server.host, mock_dns_server.port)]
        reactor.installResolver(createResolver(servers=servers))

        configure_logging()
        runner = CrawlerRunner()
        d = runner.crawl(LocalhostSpider, url=url)
        d.addBoth(lambda _: reactor.stop())
        reactor.run()
