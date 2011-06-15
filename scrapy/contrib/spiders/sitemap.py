import re

from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots

class SitemapSpider(BaseSpider):

    sitemap_urls = ()
    sitemap_rules = [('', 'parse')]

    def __init__(self, *a, **kw):
        super(SitemapSpider, self).__init__(*a, **kw)
        self._cbs = []
        for r, c in self.sitemap_rules:
            if isinstance(r, basestring):
                r = re.compile(r)
            if isinstance(c, basestring):
                c = getattr(self, c)
            self._cbs.append((r, c))
            print self._cbs

    def start_requests(self):
        return [Request(x, callback=self._parse_sitemap) for x in self.sitemap_urls]

    def _parse_sitemap(self, response):
        if response.url.endswith('/robots.txt'):
            for url in sitemap_urls_from_robots(response.body):
                yield Request(url, callback=self._parse_sitemap)
        else:
            s = Sitemap(response.body)
            if s.type == 'sitemapindex':
                for sitemap in s:
                    yield Request(sitemap['loc'], callback=self._parse_sitemap)
            elif s.type == 'urlset':
                for url in s:
                    loc = url['loc']
                    for r, c in self._cbs:
                        if r.search(loc):
                            yield Request(loc, callback=c)
                            break
