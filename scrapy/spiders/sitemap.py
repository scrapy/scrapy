import re
import logging
import six

from scrapy.spiders import Spider
from scrapy.http import Request, XmlResponse
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from scrapy.utils.gz import gunzip, gzip_magic_number


logger = logging.getLogger(__name__)


class SitemapSpider(Spider):
    """SitemapSpider allows you to crawl a site by discovering the URLs using
    `Sitemaps`_.

    It supports nested sitemaps and discovering sitemap urls from
    `robots.txt`_.
    """

    #: A list of urls pointing to the sitemaps whose urls you want to crawl.
    #:
    #: You can also point to a `robots.txt`_ and it will be parsed to extract
    #: sitemap urls from it.
    sitemap_urls = ()

    #: A list of tuples ``(regex, callback)`` where:
    #:
    #: * ``regex`` is a regular expression to match urls extracted from sitemaps.
    #:   ``regex`` can be either a str or a compiled regex object.
    #:
    #: * callback is the callback to use for processing the urls that match
    #:   the regular expression. ``callback`` can be a string (indicating the
    #:   name of a spider method) or a callable.
    #:
    #: For example::
    #:
    #:     sitemap_rules = [('/product/', 'parse_product')]
    #:
    #: Rules are applied in order, and only the first one that matches will be
    #: used.
    #:
    #: If you omit this attribute, all urls found in sitemaps will be
    #: processed with the ``parse`` callback.
    sitemap_rules = [('', 'parse')]

    #: A list of regexes of sitemap that should be followed. This is is only
    #: for sites that use `Sitemap index files`_ that point to other sitemap
    #: files.
    #:
    #: By default, all sitemaps are followed.
    sitemap_follow = ['']

    #: Specifies if alternate links for one ``url`` should be followed. These
    #: are links for the same website in another language passed within
    #: the same ``url`` block.
    #:
    #: For example::
    #:
    #:     <url>
    #:         <loc>http://example.com/</loc>
    #:         <xhtml:link rel="alternate" hreflang="de" href="http://example.com/de"/>
    #:     </url>
    #:
    #: With ``sitemap_alternate_links`` set, this would retrieve both URLs. With
    #: ``sitemap_alternate_links`` disabled, only ``http://example.com/`` would be
    #: retrieved.
    #:
    #: Default is ``sitemap_alternate_links`` disabled.
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

    def sitemap_filter(self, entries):
        """This is a filter funtion that could be overridden to select sitemap
        entries based on their attributes.

        For example::

            <url>
                <loc>http://example.com/</loc>
                <lastmod>2005-01-01</lastmod>
            </url>

        We can define a ``sitemap_filter`` function to filter ``entries`` by date::

            from datetime import datetime
            from scrapy.spiders import SitemapSpider

            class FilteredSitemapSpider(SitemapSpider):
                name = 'filtered_sitemap_spider'
                allowed_domains = ['example.com']
                sitemap_urls = ['http://example.com/sitemap.xml']

                def sitemap_filter(self, entries):
                    for entry in entries:
                        date_time = datetime.strptime(entry['lastmod'], '%Y-%m-%d')
                        if date_time.year >= 2005:
                            yield entry

        This would retrieve only ``entries`` modified on 2005 and the following
        years.

        Entries are dict objects extracted from the sitemap document.
        Usually, the key is the tag name and the value is the text inside it.

        It's important to notice that:

        - as the loc attribute is required, entries without this tag are discarded
        - alternate links are stored in a list with the key ``alternate``
          (see ``sitemap_alternate_links``)
        - namespaces are removed, so lxml tags named as ``{namespace}tagname`` become only ``tagname``

        If you omit this method, all entries found in sitemaps will be
        processed, observing other attributes and their settings.
        """
        for entry in entries:
            yield entry

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

            s = Sitemap(body)
            it = self.sitemap_filter(s)

            if s.type == 'sitemapindex':
                for loc in iterloc(it, self.sitemap_alternate_links):
                    if any(x.search(loc) for x in self._follow):
                        yield Request(loc, callback=self._parse_sitemap)
            elif s.type == 'urlset':
                for loc in iterloc(it, self.sitemap_alternate_links):
                    for r, c in self._cbs:
                        if r.search(loc):
                            yield Request(loc, callback=c)
                            break

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


def iterloc(it, alt=False):
    for d in it:
        yield d['loc']

        # Also consider alternate URLs (xhtml:link rel="alternate")
        if alt and 'alternate' in d:
            for l in d['alternate']:
                yield l
