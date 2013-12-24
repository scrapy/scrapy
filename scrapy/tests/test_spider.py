import gzip
import inspect
import warnings
from cStringIO import StringIO

from twisted.trial import unittest

from scrapy.spider import BaseSpider
from scrapy.http import Response, TextResponse, XmlResponse, HtmlResponse
from scrapy.contrib.spiders.init import InitSpider
from scrapy.contrib.spiders import CrawlSpider, XMLFeedSpider, CSVFeedSpider, SitemapSpider
from scrapy.selector import XPath


class BaseSpiderTest(unittest.TestCase):

    spider_class = BaseSpider

    def setUp(self):
        warnings.simplefilter("always")

    def tearDown(self):
        warnings.resetwarnings()

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        self.assertEqual(spider.name, 'example.com')
        self.assertEqual(spider.start_urls, [])

    def test_start_requests(self):
        spider = self.spider_class('example.com')
        start_requests = spider.start_requests()
        self.assertTrue(inspect.isgenerator(start_requests))
        self.assertEqual(list(start_requests), [])

    def test_spider_args(self):
        """Constructor arguments are assigned to spider attributes"""
        spider = self.spider_class('example.com', foo='bar')
        self.assertEqual(spider.foo, 'bar')

    def test_spider_without_name(self):
        """Constructor arguments are assigned to spider attributes"""
        self.assertRaises(ValueError, self.spider_class)
        self.assertRaises(ValueError, self.spider_class, somearg='foo')


class InitSpiderTest(BaseSpiderTest):

    spider_class = InitSpider


class XMLFeedSpiderTest(BaseSpiderTest):

    spider_class = XMLFeedSpider

    def test_register_namespace(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns:x="http://www.google.com/schemas/sitemap/0.84"
                xmlns:y="http://www.example.com/schemas/extras/1.0">
        <url><x:loc>http://www.example.com/Special-Offers.html</loc><y:updated>2009-08-16</updated><other value="bar" y:custom="fuu"/></url>
        <url><loc>http://www.example.com/</loc><y:updated>2009-08-16</updated><other value="foo"/></url>
        </urlset>"""
        response = XmlResponse(url='http://example.com/sitemap.xml', body=body)

        class _XMLSpider(self.spider_class):
            itertag = 'url'
            namespaces = (
                ('a', 'http://www.google.com/schemas/sitemap/0.84'),
                ('b', 'http://www.example.com/schemas/extras/1.0'),
            )

            def parse_node(self, response, selector):
                yield {
                    'loc': selector.xpath('a:loc/text()').extract(),
                    'updated': selector.xpath('b:updated/text()').extract(),
                    'other': selector.xpath('other/@value').extract(),
                    'custom': selector.xpath('other/@b:custom').extract(),
                }

        for iterator in ('iternodes', 'xml'):
            spider = _XMLSpider('example', iterator=iterator)
            output = list(spider.parse(response))
            self.assertEqual(len(output), 2, iterator)
            self.assertEqual(output, [
                {'loc': [u'http://www.example.com/Special-Offers.html'],
                 'updated': [u'2009-08-16'],
                 'custom': [u'fuu'],
                 'other': [u'bar']},
                {'loc': [],
                 'updated': [u'2009-08-16'],
                 'other': [u'foo'],
                 'custom': []},
            ], iterator)

    def test_register_namespace_compiled(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns:x="http://www.google.com/schemas/sitemap/0.84"
                xmlns:y="http://www.example.com/schemas/extras/1.0">
        <url><x:loc>http://www.example.com/Special-Offers.html</loc><y:updated>2009-08-16</updated><other value="bar" y:custom="fuu"/></url>
        <url><loc>http://www.example.com/</loc><y:updated>2009-08-16</updated><other value="foo"/></url>
        </urlset>"""
        response = XmlResponse(url='http://example.com/sitemap.xml', body=body)

        class _XMLSpider(self.spider_class):
            itertag = 'url'
            namespaces = (
                ('a', 'http://www.google.com/schemas/sitemap/0.84'),
                ('b', 'http://www.example.com/schemas/extras/1.0'),
            )
            xp_loc_text = XPath('a:loc/text()')
            xp_loc_text.register_namespace(
                'a', 'http://www.google.com/schemas/sitemap/0.84')

            xp_updated_text = XPath('b:updated/text()', namespaces={
                'b':'http://www.example.com/schemas/extras/1.0'
            })
            xp_other_value = XPath('other/@value')
            xp_other_custom = XPath('other/@b:custom')
            xp_other_custom.register_namespace(
                'b', 'http://www.example.com/schemas/extras/1.0')

            def parse_node(self, response, selector):
                yield {
                    'loc': selector.xpath(self.xp_loc_text).extract(),
                    'updated': selector.xpath(self.xp_updated_text).extract(),
                    'other': selector.xpath(self.xp_other_value).extract(),
                    'custom': selector.xpath(self.xp_other_custom).extract(),
                }

        for iterator in ('iternodes', 'xml'):
            spider = _XMLSpider('example', iterator=iterator)
            output = list(spider.parse(response))
            self.assertEqual(len(output), 2, iterator)
            self.assertEqual(output, [
                {'loc': [u'http://www.example.com/Special-Offers.html'],
                 'updated': [u'2009-08-16'],
                 'custom': [u'fuu'],
                 'other': [u'bar']},
                {'loc': [],
                 'updated': [u'2009-08-16'],
                 'other': [u'foo'],
                 'custom': []},
            ], iterator)

    def test_register_defaultnamespace(self):
        body = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns:im="http://itunes.apple.com/rss" xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
    <id>https://itunes.apple.com/us/rss/topaudiobooks/limit=10/xml</id>
    <title>iTunes Store: Top Audiobooks</title>
    <updated>2013-11-24T12:41:07-07:00</updated>
    <link rel="alternate" type="text/html" href="https://itunes.apple.com/WebObjects/MZStore.woa/wa/viewTop?cc=us&amp;id=38&amp;popId=8"/>
    <link rel="self" href="https://itunes.apple.com/us/rss/topaudiobooks/limit=10/xml"/>
    <icon>http://itunes.apple.com/favicon.ico</icon>
    <author>
        <name>iTunes Store</name>
        <uri>http://www.apple.com/itunes/</uri>
    </author>
    <rights>Copyright 2008 Apple Inc.</rights>
    <entry>
        <updated>2013-11-24T12:41:07-07:00</updated>
        <id im:id="387391500">https://itunes.apple.com/us/audiobook/mockingjay-final-book-hunger/id387391500?uo=2</id>
        <title>Mockingjay: The Final Book of the Hunger Games (Unabridged) - Suzanne Collins</title>
        <im:name>Mockingjay: The Final Book of the Hunger Games (Unabridged)</im:name>
        <link rel="alternate" type="text/html" href="https://itunes.apple.com/us/audiobook/mockingjay-final-book-hunger/id387391500?uo=2"/>
        <im:contentType term="Audiobook" label="Audiobook"/>
        <category im:id="50000044" term="Kids &amp; Young Adults" scheme="https://itunes.apple.com/us/genre/audiobooks-kids-young-adults/id50000044?uo=2" label="Kids &amp; Young Adults"/>
        <link title="Preview" rel="enclosure" type="audio/x-m4a" href="http://a390.phobos.apple.com/us/r30/Music4/v4/51/99/a7/5199a7b9-db39-e5ab-3438-4a76328eb2d5/mzaf_2857127299462152824.plus.aac.p.m4a" im:assetType="preview"><im:duration>30000</im:duration></link>
        <im:artist href="https://itunes.apple.com/us/artist/suzanne-collins/id110188933?mt=11&amp;uo=2">Suzanne Collins</im:artist>
        <im:price amount="17.95000" currency="USD">$17.95</im:price>
        <im:image height="55">http://a1385.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.55x55-70.jpg</im:image>
        <im:image height="60">http://a107.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.60x60-50.jpg</im:image>
        <im:image height="170">http://a1562.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.170x170-75.jpg</im:image>
        <rights>&#8471; &#169; 2010 Scholastic Audio</rights>
        <im:releaseDate label="August 24, 2010">2010-08-24T00:00:00-07:00</im:releaseDate>
    </entry>
    <entry>
        <updated>2013-11-24T12:41:07-07:00</updated>
        <id im:id="329920607">https://itunes.apple.com/us/audiobook/catching-fire-hunger-games/id329920607?uo=2</id>
        <title>Catching Fire: Hunger Games, Book 2 (Unabridged) - Suzanne Collins</title>
        <im:name>Catching Fire: Hunger Games, Book 2 (Unabridged)</im:name>
        <link rel="alternate" type="text/html" href="https://itunes.apple.com/us/audiobook/catching-fire-hunger-games/id329920607?uo=2"/>
        <im:contentType term="Audiobook" label="Audiobook"/>
        <category im:id="50000044" term="Kids &amp; Young Adults" scheme="https://itunes.apple.com/us/genre/audiobooks-kids-young-adults/id50000044?uo=2" label="Kids &amp; Young Adults"/>
        <link title="Preview" rel="enclosure" type="audio/x-m4a" href="http://a109.phobos.apple.com/us/r30/Music4/v4/6b/c6/f9/6bc6f9f9-60a4-b8d5-1227-b96995c74f08/mzaf_1215338369218175103.plus.aac.p.m4a" im:assetType="preview"><im:duration>30000</im:duration></link>
        <im:artist href="https://itunes.apple.com/us/artist/suzanne-collins/id110188933?mt=11&amp;uo=2">Suzanne Collins</im:artist>
        <im:price amount="24.95000" currency="USD">$24.95</im:price>
        <im:image height="55">http://a451.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.55x55-70.jpg</im:image>
        <im:image height="60">http://a1525.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.60x60-50.jpg</im:image>
        <im:image height="170">http://a1364.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.170x170-75.jpg</im:image>
        <rights>&#8471; &#169; 2009 Scholastic Audio</rights>
        <im:releaseDate label="September 1, 2009">2009-09-01T00:00:00-07:00</im:releaseDate>
    </entry>
</feed>"""
        response = XmlResponse(url='http://example.com/sitemap.xml', body=body)

        class _XMLSpider(self.spider_class):
            itertag = 'entry'
            itertag_ns_prefix = 'atom'
            itertag_ns_name = 'http://www.w3.org/2005/Atom'
            namespaces = (
                ('im', "http://itunes.apple.com/rss"),
                ('atom', 'http://www.w3.org/2005/Atom'),
            )

            def parse_node(self, response, selector):
                yield {
                    'updated': selector.xpath('atom:updated/text()').extract(),
                    'contentType': selector.xpath('im:contentType/@term').extract(),
                    'releaseDate': selector.xpath('im:releaseDate/@label').extract(),
                }

        for iterator in ('iternodes', 'xml'):
            spider = _XMLSpider('example', iterator=iterator)
            output = list(spider.parse(response))
            self.assertEqual(len(output), 2, iterator)
            self.assertEqual(output, [
                {'contentType': [u'Audiobook'],
                'releaseDate': [u'August 24, 2010'],
                'updated': [u'2013-11-24T12:41:07-07:00']},
                {'contentType': [u'Audiobook'],
                'releaseDate': [u'September 1, 2009'],
                'updated': [u'2013-11-24T12:41:07-07:00']},
            ], iterator)


    def test_register_defaultnamespace_compiled(self):
        body = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns:im="http://itunes.apple.com/rss" xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
    <id>https://itunes.apple.com/us/rss/topaudiobooks/limit=10/xml</id>
    <title>iTunes Store: Top Audiobooks</title>
    <updated>2013-11-24T12:41:07-07:00</updated>
    <link rel="alternate" type="text/html" href="https://itunes.apple.com/WebObjects/MZStore.woa/wa/viewTop?cc=us&amp;id=38&amp;popId=8"/>
    <link rel="self" href="https://itunes.apple.com/us/rss/topaudiobooks/limit=10/xml"/>
    <icon>http://itunes.apple.com/favicon.ico</icon>
    <author>
        <name>iTunes Store</name>
        <uri>http://www.apple.com/itunes/</uri>
    </author>
    <rights>Copyright 2008 Apple Inc.</rights>
    <entry>
        <updated>2013-11-24T12:41:07-07:00</updated>
        <id im:id="387391500">https://itunes.apple.com/us/audiobook/mockingjay-final-book-hunger/id387391500?uo=2</id>
        <title>Mockingjay: The Final Book of the Hunger Games (Unabridged) - Suzanne Collins</title>
        <im:name>Mockingjay: The Final Book of the Hunger Games (Unabridged)</im:name>
        <link rel="alternate" type="text/html" href="https://itunes.apple.com/us/audiobook/mockingjay-final-book-hunger/id387391500?uo=2"/>
        <im:contentType term="Audiobook" label="Audiobook"/>
        <category im:id="50000044" term="Kids &amp; Young Adults" scheme="https://itunes.apple.com/us/genre/audiobooks-kids-young-adults/id50000044?uo=2" label="Kids &amp; Young Adults"/>
        <link title="Preview" rel="enclosure" type="audio/x-m4a" href="http://a390.phobos.apple.com/us/r30/Music4/v4/51/99/a7/5199a7b9-db39-e5ab-3438-4a76328eb2d5/mzaf_2857127299462152824.plus.aac.p.m4a" im:assetType="preview"><im:duration>30000</im:duration></link>
        <im:artist href="https://itunes.apple.com/us/artist/suzanne-collins/id110188933?mt=11&amp;uo=2">Suzanne Collins</im:artist>
        <im:price amount="17.95000" currency="USD">$17.95</im:price>
        <im:image height="55">http://a1385.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.55x55-70.jpg</im:image>
        <im:image height="60">http://a107.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.60x60-50.jpg</im:image>
        <im:image height="170">http://a1562.phobos.apple.com/us/r30/Music/ac/3e/30/mzi.ihhqvuls.170x170-75.jpg</im:image>
        <rights>&#8471; &#169; 2010 Scholastic Audio</rights>
        <im:releaseDate label="August 24, 2010">2010-08-24T00:00:00-07:00</im:releaseDate>
    </entry>
    <entry>
        <updated>2013-11-24T12:41:07-07:00</updated>
        <id im:id="329920607">https://itunes.apple.com/us/audiobook/catching-fire-hunger-games/id329920607?uo=2</id>
        <title>Catching Fire: Hunger Games, Book 2 (Unabridged) - Suzanne Collins</title>
        <im:name>Catching Fire: Hunger Games, Book 2 (Unabridged)</im:name>
        <link rel="alternate" type="text/html" href="https://itunes.apple.com/us/audiobook/catching-fire-hunger-games/id329920607?uo=2"/>
        <im:contentType term="Audiobook" label="Audiobook"/>
        <category im:id="50000044" term="Kids &amp; Young Adults" scheme="https://itunes.apple.com/us/genre/audiobooks-kids-young-adults/id50000044?uo=2" label="Kids &amp; Young Adults"/>
        <link title="Preview" rel="enclosure" type="audio/x-m4a" href="http://a109.phobos.apple.com/us/r30/Music4/v4/6b/c6/f9/6bc6f9f9-60a4-b8d5-1227-b96995c74f08/mzaf_1215338369218175103.plus.aac.p.m4a" im:assetType="preview"><im:duration>30000</im:duration></link>
        <im:artist href="https://itunes.apple.com/us/artist/suzanne-collins/id110188933?mt=11&amp;uo=2">Suzanne Collins</im:artist>
        <im:price amount="24.95000" currency="USD">$24.95</im:price>
        <im:image height="55">http://a451.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.55x55-70.jpg</im:image>
        <im:image height="60">http://a1525.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.60x60-50.jpg</im:image>
        <im:image height="170">http://a1364.phobos.apple.com/us/r30/Music/d2/83/27/mzi.mywamvuu.170x170-75.jpg</im:image>
        <rights>&#8471; &#169; 2009 Scholastic Audio</rights>
        <im:releaseDate label="September 1, 2009">2009-09-01T00:00:00-07:00</im:releaseDate>
    </entry>
</feed>"""
        response = XmlResponse(url='http://example.com/sitemap.xml', body=body)

        class _XMLSpider(self.spider_class):
            itertag = 'entry'
            itertag_ns_prefix = 'atom'
            itertag_ns_name = 'http://www.w3.org/2005/Atom'
            namespaces = (
                ('im', "http://itunes.apple.com/rss"),
                ('atom', 'http://www.w3.org/2005/Atom'),
            )

            xp_update_text = XPath('atom:updated/text()')
            xp_update_text.register_namespace(
                'atom', 'http://www.w3.org/2005/Atom')

            xp_contentype_term = XPath('im:contentType/@term', namespaces={
                'im': "http://itunes.apple.com/rss"
            })

            xp_releasedate_label = XPath('im:releaseDate/@label')
            xp_releasedate_label.register_namespace(
                'im', "http://itunes.apple.com/rss")

            def parse_node(self, response, selector):
                yield {
                    'updated': selector.xpath(self.xp_update_text).extract(),
                    'contentType': selector.xpath(self.xp_contentype_term).extract(),
                    'releaseDate': selector.xpath(self.xp_releasedate_label).extract(),
                }

        for iterator in ('iternodes', 'xml'):
            spider = _XMLSpider('example', iterator=iterator)
            output = list(spider.parse(response))
            self.assertEqual(len(output), 2, iterator)
            self.assertEqual(output, [
                {'contentType': [u'Audiobook'],
                'releaseDate': [u'August 24, 2010'],
                'updated': [u'2013-11-24T12:41:07-07:00']},
                {'contentType': [u'Audiobook'],
                'releaseDate': [u'September 1, 2009'],
                'updated': [u'2013-11-24T12:41:07-07:00']},
            ], iterator)


class CSVFeedSpiderTest(BaseSpiderTest):

    spider_class = CSVFeedSpider


class CrawlSpiderTest(BaseSpiderTest):

    spider_class = CrawlSpider


class SitemapSpiderTest(BaseSpiderTest):

    spider_class = SitemapSpider

    BODY = "SITEMAP"
    f = StringIO()
    g = gzip.GzipFile(fileobj=f, mode='w+b')
    g.write(BODY)
    g.close()
    GZBODY = f.getvalue()

    def test_get_sitemap_body(self):
        spider = self.spider_class("example.com")

        r = XmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = HtmlResponse(url="http://www.example.com/", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), None)

        r = Response(url="http://www.example.com/favicon.ico", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), None)

        r = Response(url="http://www.example.com/sitemap", body=self.GZBODY, headers={"content-type": "application/gzip"})
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = TextResponse(url="http://www.example.com/sitemap.xml", body=self.BODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

        r = Response(url="http://www.example.com/sitemap.xml.gz", body=self.GZBODY)
        self.assertEqual(spider._get_sitemap_body(r), self.BODY)

if __name__ == '__main__':
    unittest.main()
