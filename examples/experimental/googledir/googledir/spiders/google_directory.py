from scrapy.selector import HtmlXPathSelector
from scrapy.contrib.loader import XPathItemLoader
from scrapy.contrib_exp.crawlspider import CrawlSpider, Rule

from googledir.items import GoogledirItem

class GoogleDirectorySpider(CrawlSpider):

    name = 'google_directory'
    allowed_domains = ['directory.google.com']
    start_urls = ['http://directory.google.com/']

    rules = (
        # search for categories pattern and follow links
        Rule(r'/[A-Z][a-zA-Z_/]+$', 'parse_category', follow=True),
        )

    def parse_category(self, response):
        # The main selector we're using to extract data from the page
        main_selector = HtmlXPathSelector(response)

        # The XPath to website links in the directory page
        xpath = '//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font'

        # Get a list of (sub) selectors to each website node pointed by the XPath
        sub_selectors = main_selector.select(xpath)

        # Iterate over the sub-selectors to extract data for each website
        for selector in sub_selectors:
            item = GoogledirItem()

            l = XPathItemLoader(item=item, selector=selector)
            l.add_xpath('name', 'a/text()')
            l.add_xpath('url', 'a/@href')
            l.add_xpath('description', 'font[2]/text()')

            # Here we populate the item and yield it
            yield l.load_item()

SPIDER = GoogleDirectorySpider()

