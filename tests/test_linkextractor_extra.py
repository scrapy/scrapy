import unittest

from scrapy.http import HtmlResponse
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor


class LxmlLinkExtractorExtraTest(unittest.TestCase):
    def test_all_tags(self):
        html = """
        <html>
            <body>
                <a href="page1.html">Link 1</a>
                <div onclick="page2.html">Link 2</div>
                <img src="image.jpg" />
                <link href="style.css" rel="stylesheet" />
            </body>
        </html>
        """
        response = HtmlResponse(url="http://example.com/index.html", body=html, encoding="utf8")

        # By default only 'a' and 'area'
        lx = LxmlLinkExtractor()
        links = lx.extract_links(response)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, "http://example.com/page1.html")

        # With tags=True (and attrs default to 'href')
        # Expect 'a' (href) and 'link' (href)
        lx = LxmlLinkExtractor(tags=True, deny_extensions=[])
        links = lx.extract_links(response)
        self.assertEqual(len(links), 2)
        urls = sorted([l.url for l in links])
        self.assertEqual(urls, ["http://example.com/page1.html", "http://example.com/style.css"])

    def test_all_tags_all_attrs(self):
        html = """
        <html>
            <body>
                <a href="page1.html">Link 1</a>
                <img src="image.jpg" />
            </body>
        </html>
        """
        response = HtmlResponse(url="http://example.com/index.html", body=html, encoding="utf8")

        # tags=True, attrs=True
        # Should pick up href from 'a' and src from 'img'
        lx = LxmlLinkExtractor(tags=True, attrs=True, deny_extensions=[])
        links = lx.extract_links(response)
        self.assertEqual(len(links), 2)
        urls = sorted([l.url for l in links])
        self.assertEqual(urls, ["http://example.com/image.jpg", "http://example.com/page1.html"])

    def test_deny_tags(self):
        html = """
        <html>
            <body>
                <a href="page1.html">Link 1</a>
                <link href="style.css" rel="stylesheet" />
            </body>
        </html>
        """
        response = HtmlResponse(url="http://example.com/index.html", body=html, encoding="utf8")

        # tags=True but deny 'link'
        lx = LxmlLinkExtractor(tags=True, deny_tags='link')
        links = lx.extract_links(response)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, "http://example.com/page1.html")

    def test_deny_attrs(self):
        html = """
        <html>
            <body>
                <a href="page1.html" data-ref="ref1">Link 1</a>
            </body>
        </html>
        """
        response = HtmlResponse(url="http://example.com/index.html", body=html, encoding="utf8")

        # tags=True, attrs=True, but deny 'data-ref'
        lx = LxmlLinkExtractor(tags=True, attrs=True, deny_attrs='data-ref')
        links = lx.extract_links(response)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, "http://example.com/page1.html")
