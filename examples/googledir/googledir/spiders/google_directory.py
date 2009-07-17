from scrapy.xpath import HtmlXPathSelector
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.contrib.spiders import CrawlSpider, Rule
from googledir.items import GoogledirItem

class GoogleDirectorySpider(CrawlSpider):

    domain_name = 'directory.google.com'
    start_urls = ['http://directory.google.com/']

    rules = (
        Rule(SgmlLinkExtractor(allow='directory.google.com/[A-Z][a-zA-Z_/]+$'),
            'parse_category',
            follow=True,
        ),
    )
    
    def parse_category(self, response):
        # The selector we're going to use in order to extract data from the page
        hxs = HtmlXPathSelector(response)

        # The path to website links in directory page
        links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

        for link in links:
            item = GoogledirItem()

            item.name = link.x('a/text()').extract()
            item.url = link.x('a/@href').extract()
            item.description = link.x('font[2]/text()').extract()
            yield item

SPIDER = GoogleDirectorySpider()
