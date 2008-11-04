"""
This module contains some basic spiders for scraping websites (CrawlSpider)
and XML feeds (XMLFeedSpider).
"""

from scrapy.http import Request, Response, ResponseBody
from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem
from scrapy.xpath.selector import XmlXPathSelector
from scrapy.core.exceptions import UsageError
from scrapy.utils.iterators import xmliter, csviter
from scrapy.utils.misc import hash_values

class BasicSpider(BaseSpider):
    """
    This class is basically a BaseSpider with support for GUID generating
    """
    gen_guid_attribs = []

    def set_guid(self, item):
        item.guid = hash_values(self.domain_name, *[str(getattr(item, aname) or '') for aname in self.gen_guid_attribs])
   
class CrawlSpider(BasicSpider):
    """
    This class works as a base class for spiders that crawl over websites
    """
    def __init__(self):
        super(BaseSpider, self).__init__()
        
        self._links_callback = []
        for attr in dir(self):
            if attr.startswith('links_'):
                suffix = attr.split('_', 1)[1]
                value = getattr(self, attr)
                callback = getattr(self, 'parse_%s' % suffix, None)
                self._links_callback.append((value, callback))

    def parse(self, response):
        """This function is called by the core for all the start_urls. Do not
        override this function, override parse_start_url instead."""
        return self._parse_wrapper(response, self.parse_start_url)

    def parse_start_url(self, response):
        """Callback function for processing start_urls. It must return a list
        of ScrapedItems and/or Requests."""
        return []

    def _links_to_follow(self, response):
        res = []
        links_to_follow = {}
        for lx, callback in self._links_callback:
            links = lx.extract_urls(response)
            links = self.post_extract_links(links) if hasattr(self, 'post_extract_links') else links
            for link in links:
                links_to_follow[link.url] = (callback, link.text)

        for url, (callback, link_text) in links_to_follow.iteritems():
            request = Request(url=url, link_text=link_text)
            request.append_callback(self._parse_wrapper, callback)
            res.append(request)
        return res

    def _parse_wrapper(self, response, callback):
        res = self._links_to_follow(response)
        res += callback(response) if callback else ()
        for entry in res:
            if isinstance(entry, ScrapedItem):
               self.set_guid(entry)
        return res

    def parse_url(self, response):
        """
        This method is called whenever you run scrapy with the 'parse' command
        over an URL.
        """
        extractor_names = [attrname for attrname in dir(self) if attrname.startswith('links_')]
        ret = []
        for name in extractor_names:
            extractor = getattr(self, name)
            callback_name = 'parse_%s' % name[6:]
            if hasattr(self, callback_name):
                if extractor.match(response.url):
                    ret.extend(getattr(self, callback_name)(response))
        return ret

class XMLFeedSpider(BasicSpider):
    """
    This class intends to be the base class for spiders that scrape
    from XML feeds.

    You can choose whether to parse the file using the iternodes tool,
    or not using it (which just splits the tags using xpath)
    """
    iternodes = True
    itertag = 'product'

    def parse_item_wrapper(self, response, xSel):
        ret = self.parse_item(response, xSel)
        if isinstance(ret, ScrapedItem):
            self.set_guid(ret)
        return ret

    def parse(self, response):
        if not hasattr(self, 'parse_item'):
            raise NotConfigured('You must define parse_item method in order to scrape this feed')

        if self.iternodes:
            nodes = xmliter(response, self.itertag)
        else:
            nodes = XmlXPathSelector(response).x('//%s' % self.itertag)

        return (self.parse_item_wrapper(response, xSel) for xSel in nodes)

