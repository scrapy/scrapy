import unittest

from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots, xml_to_dict

class SitemapTest(unittest.TestCase):

    def test_sitemap(self):
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.google.com/schemas/sitemap/0.84">
  <url>
    <loc>http://www.example.com/</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>daily</changefreq>
    <priority>1</priority>
  </url>
  <url>
    <loc>http://www.example.com/Special-Offers.html</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>""")
        assert s.type == 'urlset'
        self.assertEqual(list(s),
            [{'priority': '1', 'loc': 'http://www.example.com/', 'lastmod': '2009-08-16', 'changefreq': 'daily'}, {'priority': '0.8', 'loc': 'http://www.example.com/Special-Offers.html', 'lastmod': '2009-08-16', 'changefreq': 'weekly'}])

    def test_sitemap_index(self):
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <sitemap>
      <loc>http://www.example.com/sitemap1.xml.gz</loc>
      <lastmod>2004-10-01T18:23:17+00:00</lastmod>
   </sitemap>
   <sitemap>
      <loc>http://www.example.com/sitemap2.xml.gz</loc>
      <lastmod>2005-01-01</lastmod>
   </sitemap>
</sitemapindex>""")
        assert s.type == 'sitemapindex'
        self.assertEqual(list(s), [{'loc': 'http://www.example.com/sitemap1.xml.gz', 'lastmod': '2004-10-01T18:23:17+00:00'}, {'loc': 'http://www.example.com/sitemap2.xml.gz', 'lastmod': '2005-01-01'}])

    def test_sitemap_strip(self):
        """Assert we can deal with trailing spaces inside <loc> tags - we've
        seen those
        """
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.google.com/schemas/sitemap/0.84">
  <url>
    <loc> http://www.example.com/</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>daily</changefreq>
    <priority>1</priority>
  </url>
  <url>
    <loc> http://www.example.com/2</loc>
    <lastmod />
  </url>
</urlset>
""")
        self.assertEqual(list(s),
            [{'priority': '1', 'loc': 'http://www.example.com/', 'lastmod': '2009-08-16', 'changefreq': 'daily'},
             {'loc': 'http://www.example.com/2'},
            ])

    def test_sitemap_wrong_ns(self):
        """We have seen sitemaps with wrongs ns. Presumably, Google still works
        with these, though is not 100% confirmed"""
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.google.com/schemas/sitemap/0.84">
  <url xmlns="">
    <loc> http://www.example.com/</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>daily</changefreq>
    <priority>1</priority>
  </url>
  <url xmlns="">
    <loc> http://www.example.com/2</loc>
    <lastmod />
  </url>
</urlset>
""")
        self.assertEqual(list(s),
            [{'priority': '1', 'loc': 'http://www.example.com/', 'lastmod': '2009-08-16', 'changefreq': 'daily'},
             {'loc': 'http://www.example.com/2'},
            ])

    def test_sitemap_wrong_ns2(self):
        """We have seen sitemaps with wrongs ns. Presumably, Google still works
        with these, though is not 100% confirmed"""
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url xmlns="">
    <loc> http://www.example.com/</loc>
    <lastmod>2009-08-16</lastmod>
    <changefreq>daily</changefreq>
    <priority>1</priority>
  </url>
  <url xmlns="">
    <loc> http://www.example.com/2</loc>
    <lastmod />
  </url>
</urlset>
""")
        assert s.type == 'urlset'
        self.assertEqual(list(s),
            [{'priority': '1', 'loc': 'http://www.example.com/', 'lastmod': '2009-08-16', 'changefreq': 'daily'},
             {'loc': 'http://www.example.com/2'},
            ])

    def test_sitemap_urls_from_robots(self):
        robots = """User-agent: *
Disallow: /aff/
Disallow: /wl/

# Search and shopping refining
Disallow: /s*/*facet
Disallow: /s*/*tags

# Sitemap files
Sitemap: http://example.com/sitemap.xml
Sitemap: http://example.com/sitemap-product-index.xml

# Forums
Disallow: /forum/search/
Disallow: /forum/active/
"""
        self.assertEqual(list(sitemap_urls_from_robots(robots)),
             ['http://example.com/sitemap.xml', 'http://example.com/sitemap-product-index.xml'])

    def test_sitemap_blanklines(self):
        """Assert we can deal with starting blank lines before <xml> tag"""
        s = Sitemap("""\

<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

<!-- cache: cached = yes name = sitemap_jspCache key = sitemap -->
<sitemap>
<loc>http://www.example.com/sitemap1.xml</loc>
<lastmod>2013-07-15</lastmod>
</sitemap>

<sitemap>
<loc>http://www.example.com/sitemap2.xml</loc>
<lastmod>2013-07-15</lastmod>
</sitemap>

<sitemap>
<loc>http://www.example.com/sitemap3.xml</loc>
<lastmod>2013-07-15</lastmod>
</sitemap>

<!-- end cache -->
</sitemapindex>
""")
        self.assertEqual(list(s), [
            {'lastmod': '2013-07-15', 'loc': 'http://www.example.com/sitemap1.xml'},
            {'lastmod': '2013-07-15', 'loc': 'http://www.example.com/sitemap2.xml'},
            {'lastmod': '2013-07-15', 'loc': 'http://www.example.com/sitemap3.xml'},
        ])

    def test_comment(self):
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
        <url>
            <loc>http://www.example.com/</loc>
            <!-- this is a comment on which the parser might raise an exception if implemented incorrectly -->
        </url>
    </urlset>""")

        self.assertEqual(list(s), [
            {'loc': 'http://www.example.com/'}
        ])

    def test_alternate(self):
        s = Sitemap("""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
        <url>
            <loc>http://www.example.com/english/</loc>
            <xhtml:link rel="alternate" hreflang="de"
                href="http://www.example.com/deutsch/"/>
            <xhtml:link rel="alternate" hreflang="de-ch"
                href="http://www.example.com/schweiz-deutsch/"/>
            <xhtml:link rel="alternate" hreflang="en"
                href="http://www.example.com/english/"/>
            <xhtml:link rel="alternate" hreflang="en"/><!-- wrong tag without href -->
        </url>
    </urlset>""")
        
        self.assertEqual(list(s), [
            {'loc': 'http://www.example.com/english/',
             'alternate': ['http://www.example.com/deutsch/', 'http://www.example.com/schweiz-deutsch/', 'http://www.example.com/english/']
            }
        ])

    def test_xml_to_dict(self):
        import lxml.etree
        content = """<url>
        <loc>http://arstechnica.com/gadgets/2013/08/microsoftgoogle-bring-back-the-good-youtube-windows-phone-app/</loc>
        <news:news>
            <news:publication>
                <news:name>Ars Technica</news:name>
                <news:language>en</news:language>
            </news:publication>
            <news:publication_date>2013-08-14T01:00:40+00:00</news:publication_date>
            <news:title>Microsoft/Google bring back the good YouTube Windows Phone app</news:title>
            <news:keywords>Gear &amp; Gadgets</news:keywords>
        </news:news>
        <lastmod>2013-08-14T16:01:19+00:00</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>"""
        parser = lxml.etree.XMLParser(recover=True)
        doc = lxml.etree.XML(content, parser)
        expected = {'priority': '1.0',
                    'loc': 'http://arstechnica.com/gadgets/2013/08/microsoftgoogle-bring-back-the-good-youtube-windows-phone-app/',
                    'lastmod': '2013-08-14T16:01:19+00:00',
                    'changefreq': 'daily',
                    'news:news': {'news:publication':
                                  {'news:name': 'Ars Technica',
                                   'news:language': 'en'},
                                  'news:keywords': 'Gear & Gadgets',
                                  'news:publication_date':
                                  '2013-08-14T01:00:40+00:00',
                                  'news:title': 'Microsoft/Google bring back the good YouTube Windows Phone app'}}
        self.assertEqual(xml_to_dict(doc), expected)

if __name__ == '__main__':
    unittest.main()
