# -*- coding: utf8 -*-
from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem
from scrapy.http import Request
from scrapy.utils.iterators import xmliter, csviter
from scrapy.xpath.selector import XmlXPathSelector
from scrapy.core.exceptions import UsageError, NotConfigured

class XMLFeedSpider(BaseSpider):
    """
    This class intends to be the base class for spiders that scrape
    from XML feeds.

    You can choose whether to parse the file using the iternodes tool,
    or not using it (which just splits the tags using xpath)
    """
    iternodes = True
    itertag = 'item'

    def process_results(self, results, response):
        """This overridable method is called for each result (item or request)
        returned by the spider, and it's intended to perform any last time
        processing required before returning the results to the framework core,
        for example setting the item GUIDs. It receives a list of results and
        the response which originated that results. It must return a list
        of results (Items or Requests)."""
        return results

    def parse_nodes(self, response, nodes):
        for xSel in nodes:
            ret = self.parse_item(response, xSel)
            if isinstance(ret, (ScrapedItem, Request)):
                ret = [ret]
            if not isinstance(ret, (list, tuple)):
                raise UsageError('You cannot return an "%s" object from a spider' % type(ret).__name__)
            for result_item in self.process_results(ret, response):
                yield result_item

    def parse(self, response):
        if not hasattr(self, 'parse_item'):
            raise NotConfigured('You must define parse_item method in order to scrape this XML feed')

        if self.iternodes:
            nodes = xmliter(response, self.itertag)
        else:
            nodes = XmlXPathSelector(response).x('//%s' % self.itertag)

        return self.parse_nodes(response, nodes)

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

    def process_results(self, results, response):
        """This method has the same purpose as the one in XMLFeedSpider"""
        return results

    def adapt_response(self, response):
        """You can override this function in order to make any changes you want
        to into the feed before parsing it. This function must return a response."""
        return response

    def parse_rows(self, response):
        for row in csviter(response, self.delimiter, self.headers):
            ret = self.parse_row(response, row)
            if isinstance(ret, (ScrapedItem, Request)):
                ret = [ret]
            if not isinstance(ret, (list, tuple)):
                raise UsageError('You cannot return an "%s" object from a spider' % type(ret).__name__)
            for result_item in self.process_results(ret, response):
                yield result_item

    def parse(self, response):
        if not hasattr(self, 'parse_row'):
            raise NotConfigured('You must define parse_row method in order to scrape this CSV feed')

        response = self.adapt_response(response)
        return self.parse_rows(response)

