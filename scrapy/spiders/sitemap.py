import re
import logging
import six

from scrapy.spiders import Spider
from scrapy.http import Request, XmlResponse
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from scrapy.utils.gz import gunzip, gzip_magic_number


logger = logging.getLogger(__name__)


class SitemapSpider(Spider):

    sitemap_urls = ()
    sitemap_rules = [('', 'parse')]
    sitemap_follow = ['']
    sitemap_alternate_links = False

    def __init__(self, *a, **kw):
        super(SitemapSpider, self).__init__(*a, **kw)
        self._cbs = []
        for r, c in self.sitemap_rules:
            if isinstance(c, six.string_types):
                c = getattr(self, c)
            self._cbs.append((regex(r), c))
        self._follow = [regex(x) for x in self.sitemap_follow]

    def start_requests(self):
        for url in self.sitemap_urls:
            yield Request(url, self._parse_sitemap)

    def _parse_sitemap(self, response):
        if response.url.endswith('/robots.txt'):
            for url in sitemap_urls_from_robots(response.text, base_url=response.url):
                yield Request(url, callback=self._parse_sitemap)
        else:
            body = self._get_sitemap_body(response)
            if body is None:
                logger.warning("Ignoring invalid sitemap: %(response)s",
                               {'response': response}, extra={'spider': self})
                return

            sitemap = Sitemap(body)
            for request in self._requests_from_sitemap(sitemap):
                yield request

    def _requests_from_sitemap(self, sitemap):
        if sitemap.type == 'sitemapindex':
            build_request = self._sitemapindex_request
        elif sitemap.type == 'urlset':
            build_request = self._urlset_request
        else:
            return

        for item in sitemap:
            for link in self._sitemapitem_links(item):
                request = build_request(link, item)
                if request:
                    yield request

    def _sitemapindex_request(self, link, sitemap_dict):
        if any(x.search(link) for x in self._follow):
            return Request(link, callback=self._parse_sitemap)

    def _urlset_request(self, link, sitemap_dict):
        for r, c in self._cbs:
            if r.search(link):
                return Request(link, callback=c)

    def _sitemapitem_links(self, sitemap_dict):
        yield sitemap_dict['loc']

        if self.sitemap_alternate_links and 'alternate' in sitemap_dict:
            for link in sitemap_dict['alternate']:
                yield link

    def _get_sitemap_body(self, response):
        """Return the sitemap body contained in the given response,
        or None if the response is not a sitemap.
        """
        if isinstance(response, XmlResponse):
            return response.body
        elif gzip_magic_number(response):
            return gunzip(response.body)
        # actual gzipped sitemap files are decompressed above ;
        # if we are here (response body is not gzipped)
        # and have a response for .xml.gz,
        # it usually means that it was already gunzipped
        # by HttpCompression middleware,
        # the HTTP response being sent with "Content-Encoding: gzip"
        # without actually being a .xml.gz file in the first place,
        # merely XML gzip-compressed on the fly,
        # in other word, here, we have plain XML
        elif response.url.endswith('.xml') or response.url.endswith('.xml.gz'):
            return response.body


def regex(x):
    if isinstance(x, six.string_types):
        return re.compile(x)
    return x
