import re
import urlparse
from scrapy.http import XmlResponse
from scrapy.utils.gz import gunzip, is_gzipped
from scrapy.contrib.spiders import SitemapSpider

class SitemapWithoutSchemeMiddleware(object):
    def process_response(self, request, response, spider):
        """Replace all wrongly formatted location URLs"""
        if isinstance(spider, SitemapSpider):
            body = self._get_sitemap_body(response)

            if body:
                scheme = urlparse.urlsplit(response.url).scheme
                body = re.sub(r'<loc>\/\/(.+)<\/loc>', r'<loc>%s://\1</loc>' % scheme, body)
                return response.replace(body=body)

        return response

    def _get_sitemap_body(self, response):
        """Return the sitemap body contained in the given response, or None if the
        response is not a sitemap.
        """
        if isinstance(response, XmlResponse):
            return response.body
        elif is_gzipped(response):
            return gunzip(response.body)
        elif response.url.endswith('.xml'):
            return response.body
        elif response.url.endswith('.xml.gz'):
            return gunzip(response.body)
