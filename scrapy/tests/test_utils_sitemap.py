import unittest

from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots

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
             {'loc': 'http://www.example.com/2', 'lastmod': ''},
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
             {'loc': 'http://www.example.com/2', 'lastmod': ''},
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
             {'loc': 'http://www.example.com/2', 'lastmod': ''},
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

if __name__ == '__main__':
    unittest.main()
