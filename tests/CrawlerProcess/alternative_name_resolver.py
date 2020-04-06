import scrapy
from scrapy.crawler import CrawlerProcess


class IPv6Spider(scrapy.Spider):
    name = "ipv6_spider"
    start_urls = ["http://[::1]"]


process = CrawlerProcess(settings={
    "RETRY_ENABLED": False,
    "DNS_RESOLVER": "scrapy.resolver.CachingHostnameResolver",
})
process.crawl(IPv6Spider)
process.start()
