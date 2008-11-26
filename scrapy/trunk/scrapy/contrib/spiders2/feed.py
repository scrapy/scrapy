from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem
from scrapy.utils.iterators import xmliter, csviter
from scrapy.xpath.selector import XmlXPathSelector
from scrapy.core.exceptions import NotConfigured

class XMLFeedSpider(BaseSpider):
    """
    This class intends to be the base class for spiders that scrape
    from XML feeds.

    You can choose whether to parse the file using the iternodes tool,
    or not using it (which just splits the tags using xpath)
    """
    iternodes = True
    itertag = 'item'

    def item_scraped(self, response, item):
        """
        This method is called for each item returned by the spider, and it's intended
        to do anything that it's needed before returning the item to the core, specially
        setting its GUID.
        It receives and returns an item
        """
        return item

    def parse_item_wrapper(self, response, xSel):
        ret = self.parse_item(response, xSel)
        if isinstance(ret, ScrapedItem):
            self.scraped_item(response, ret)
        return ret

    def parse(self, response):
        if not hasattr(self, 'parse_item'):
            raise NotConfigured('You must define parse_item method in order to scrape this XML feed')

        if self.iternodes:
            nodes = xmliter(response, self.itertag)
        else:
            nodes = XmlXPathSelector(response).x('//%s' % self.itertag)

        return (self.parse_item_wrapper(response, xSel) for xSel in nodes)

class CSVFeedSpider(BaseSpider):
    """
    Spider for parsing CSV feeds.
    It receives a CSV file in a response; iterates through each of its rows,
    and calls parse_row with a dict containing each field's data.

    You can set some options regarding the CSV file, such as the delimiter
    and the file's headers.
    """
    delimiter = None # When this is None, python's csv module's default delimiter is used
    headers = None

    def scraped_item(self, response, item):
        """This method has the same purpose as the one in XMLFeedSpider"""
        return item

    def adapt_feed(self, response):
        """You can override this function in order to make any changes you want
        to into the feed before parsing it. This function may return either a
        response or a string.  """

        return response

    def parse_row_wrapper(self, response, row):
        ret = self.parse_row(response, row)
        if isinstance(ret, ScrapedItem):
            self.scraped_item(response, ret)
        return ret

    def parse(self, response):
        if not hasattr(self, 'parse_row'):
            raise NotConfigured('You must define parse_row method in order to scrape this CSV feed')

        feed = self.adapt_feed(response)
        return (self.parse_row_wrapper(feed, row) for row in csviter(response, self.delimiter, self.headers))

