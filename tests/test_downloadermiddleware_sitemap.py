from __future__ import absolute_import
import re
import mock
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.trial import unittest
from scrapy.contrib.downloadermiddleware.robotstxt import RobotsTxtMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.settings import Settings


class RobotsTxtMiddlewareTest(unittest.TestCase):

    def test_sitemap_without_scheme(self):
        middleware = self._get_middleware()

        # TODO: Here I am not sure how to go on... do
        # Request('http://site.local/sitemap.xml')
        # or Response('http://site.local/sitemap.xml') to get the
        # response WITH middleware?

    def _get_crawler(self):
        crawler = mock.MagicMock()
        crawler.settings = Settings()
        crawler.settings.set('USER_AGENT', 'CustomAgent')
        self.assertRaises(NotConfigured, SitemapWithoutSchemeMiddleware, crawler)
        crawler.engine.download = mock.MagicMock()
        SITEMAP = re.sub(r'^\s+(?m)', '', '''
        <?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
             <url>
                 <loc>//www.example.com/</loc>
             </url>
        </urlset>
        ''')
        response = Response('http://site.local/sitemap.xml', body=SITEMAP)
        def return_response(request, spider):
            deferred = Deferred()
            reactor.callFromThread(deferred.callback, response)
            return deferred
        crawler.engine.download.side_effect = return_response
        return crawler

    def _get_middleware(self):
        crawler = self._get_crawler()
        return SitemapWithoutSchemeMiddleware(crawler)
