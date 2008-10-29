"""
This module contains BasicSpider, a spider class which provides support for
basic crawling.
"""

from scrapy.http import Request
from scrapy.spider import BaseSpider
from scrapy.core.exceptions import UsageError
from scrapy.utils.misc import hash_values

class BasicSpider(BaseSpider):
    """
    BasicSpider extends BaseSpider by providing support for simple crawling
    by following links contained in web pages. 
    
    With BasicSpider you can write a basic spider very easily and quickly. For
    more information refer to the Scrapy tutorial
    """

    gen_guid_attribs = ['supplier', 'site_id']
    gen_variant_guid_attribs = ['site_id']

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
            for url, link_text in lx.extract_urls(response).iteritems():
                links_to_follow[url] = (callback, link_text)

        for url, (callback, link_text) in links_to_follow.iteritems():
            request = Request(url=url, link_text=link_text)
            request.append_callback(self._parse_wrapper, callback)
            res.append(request)
        return res

    def _parse_wrapper(self, response, callback):
        res = self._links_to_follow(response)
        res += callback(response) if callback else ()
        return res

    def set_guid(self, item):
        item.guid = hash_values(*[str(getattr(item, aname) or '') for aname in self.gen_guid_attribs])

