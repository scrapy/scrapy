import pickle
import re
import unittest
from typing import Optional

from packaging.version import Version
from pytest import mark
from w3lib import __version__ as w3lib_version

from scrapy.http import HtmlResponse, XmlResponse
from scrapy.link import Link
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from tests import get_testdata


# a hack to skip base class tests in pytest
class Base:
    class LinkExtractorTestCase(unittest.TestCase):
        extractor_cls: Optional[type] = None

        def setUp(self):
            body = get_testdata("link_extractor", "linkextractor.html")
            self.response = HtmlResponse(url="http://example.com/index", body=body)

        def test_urls_type(self):
            """Test that the resulting urls are str objects"""
            lx = self.extractor_cls()
            self.assertTrue(
                all(
                    isinstance(link.url, str)
                    for link in lx.extract_links(self.response)
                )
            )

        def test_extract_all_links(self):
            lx = self.extractor_cls()
            page4_url = "http://example.com/page%204.html"

            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com", text=""),
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                    Link(url="http://www.google.com/something", text=""),
                    Link(url="http://example.com/innertag.html", text="inner tag"),
                    Link(url=page4_url, text="href with whitespaces"),
                ],
            )

        def test_extract_filter_allow(self):
            lx = self.extractor_cls(allow=("sample",))
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                ],
            )

        def test_extract_filter_allow_with_duplicates(self):
            lx = self.extractor_cls(allow=("sample",), unique=False)
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html",
                        text="sample 3 repetition",
                    ),
                    Link(
                        url="http://example.com/sample3.html",
                        text="sample 3 repetition",
                    ),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                ],
            )

        def test_extract_filter_allow_with_duplicates_canonicalize(self):
            lx = self.extractor_cls(allow=("sample",), unique=False, canonicalize=True)
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html",
                        text="sample 3 repetition",
                    ),
                    Link(
                        url="http://example.com/sample3.html",
                        text="sample 3 repetition",
                    ),
                    Link(
                        url="http://example.com/sample3.html",
                        text="sample 3 repetition with fragment",
                    ),
                ],
            )

        def test_extract_filter_allow_no_duplicates_canonicalize(self):
            lx = self.extractor_cls(allow=("sample",), unique=True, canonicalize=True)
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                ],
            )

        def test_extract_filter_allow_and_deny(self):
            lx = self.extractor_cls(allow=("sample",), deny=("3",))
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

        def test_extract_filter_allowed_domains(self):
            lx = self.extractor_cls(allow_domains=("google.com",))
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://www.google.com/something", text=""),
                ],
            )

        def test_extraction_using_single_values(self):
            """Test the extractor's behaviour among different situations"""

            lx = self.extractor_cls(allow="sample")
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                ],
            )

            lx = self.extractor_cls(allow="sample", deny="3")
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

            lx = self.extractor_cls(allow_domains="google.com")
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://www.google.com/something", text=""),
                ],
            )

            lx = self.extractor_cls(deny_domains="example.com")
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://www.google.com/something", text=""),
                ],
            )

        def test_nofollow(self):
            """Test the extractor's behaviour for links with rel='nofollow'"""

            html = b"""<html><head><title>Page title<title>
            <body>
            <div class='links'>
            <p><a href="/about.html">About us</a></p>
            </div>
            <div>
            <p><a href="/follow.html">Follow this link</a></p>
            </div>
            <div>
            <p><a href="/nofollow.html" rel="nofollow">Dont follow this one</a></p>
            </div>
            <div>
            <p><a href="/nofollow2.html" rel="blah">Choose to follow or not</a></p>
            </div>
            <div>
            <p><a href="http://google.com/something" rel="external nofollow">External link not to follow</a></p>
            </div>
            </body></html>"""
            response = HtmlResponse("http://example.org/somepage/index.html", body=html)

            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.org/about.html", text="About us"),
                    Link(url="http://example.org/follow.html", text="Follow this link"),
                    Link(
                        url="http://example.org/nofollow.html",
                        text="Dont follow this one",
                        nofollow=True,
                    ),
                    Link(
                        url="http://example.org/nofollow2.html",
                        text="Choose to follow or not",
                    ),
                    Link(
                        url="http://google.com/something",
                        text="External link not to follow",
                        nofollow=True,
                    ),
                ],
            )

        def test_matches(self):
            url1 = "http://lotsofstuff.com/stuff1/index"
            url2 = "http://evenmorestuff.com/uglystuff/index"

            lx = self.extractor_cls(allow=(r"stuff1",))
            self.assertTrue(lx.matches(url1))
            self.assertFalse(lx.matches(url2))

            lx = self.extractor_cls(deny=(r"uglystuff",))
            self.assertTrue(lx.matches(url1))
            self.assertFalse(lx.matches(url2))

            lx = self.extractor_cls(allow_domains=("evenmorestuff.com",))
            self.assertFalse(lx.matches(url1))
            self.assertTrue(lx.matches(url2))

            lx = self.extractor_cls(deny_domains=("lotsofstuff.com",))
            self.assertFalse(lx.matches(url1))
            self.assertTrue(lx.matches(url2))

            lx = self.extractor_cls(
                allow=["blah1"],
                deny=["blah2"],
                allow_domains=["blah1.com"],
                deny_domains=["blah2.com"],
            )
            self.assertTrue(lx.matches("http://blah1.com/blah1"))
            self.assertFalse(lx.matches("http://blah1.com/blah2"))
            self.assertFalse(lx.matches("http://blah2.com/blah1"))
            self.assertFalse(lx.matches("http://blah2.com/blah2"))

        def test_restrict_xpaths(self):
            lx = self.extractor_cls(restrict_xpaths=('//div[@id="subwrapper"]',))
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

        def test_restrict_xpaths_encoding(self):
            """Test restrict_xpaths with encodings"""
            html = b"""<html><head><title>Page title<title>
            <body><p><a href="item/12.html">Item 12</a></p>
            <div class='links'>
            <p><a href="/about.html">About us\xa3</a></p>
            </div>
            <div>
            <p><a href="/nofollow.html">This shouldn't be followed</a></p>
            </div>
            </body></html>"""
            response = HtmlResponse(
                "http://example.org/somepage/index.html",
                body=html,
                encoding="windows-1252",
            )

            lx = self.extractor_cls(restrict_xpaths="//div[@class='links']")
            self.assertEqual(
                lx.extract_links(response),
                [Link(url="http://example.org/about.html", text="About us\xa3")],
            )

        def test_restrict_xpaths_with_html_entities(self):
            html = b'<html><body><p><a href="/&hearts;/you?c=&euro;">text</a></p></body></html>'
            response = HtmlResponse(
                "http://example.org/somepage/index.html",
                body=html,
                encoding="iso8859-15",
            )
            links = self.extractor_cls(restrict_xpaths="//p").extract_links(response)
            self.assertEqual(
                links, [Link(url="http://example.org/%E2%99%A5/you?c=%A4", text="text")]
            )

        def test_restrict_xpaths_concat_in_handle_data(self):
            """html entities cause SGMLParser to call handle_data hook twice"""
            body = b"""<html><body><div><a href="/foo">&gt;\xbe\xa9&lt;\xb6\xab</a></body></html>"""
            response = HtmlResponse("http://example.org", body=body, encoding="gb18030")
            lx = self.extractor_cls(restrict_xpaths="//div")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.org/foo",
                        text=">\u4eac<\u4e1c",
                        fragment="",
                        nofollow=False,
                    )
                ],
            )

        def test_restrict_css(self):
            lx = self.extractor_cls(restrict_css=("#subwrapper a",))
            self.assertEqual(
                lx.extract_links(self.response),
                [Link(url="http://example.com/sample2.html", text="sample 2")],
            )

        def test_restrict_css_and_restrict_xpaths_together(self):
            lx = self.extractor_cls(
                restrict_xpaths=('//div[@id="subwrapper"]',),
                restrict_css=("#subwrapper + a",),
            )
            self.assertEqual(
                list(lx.extract_links(self.response)),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                ],
            )

        def test_area_tag_with_unicode_present(self):
            body = b"""<html><body>\xbe\xa9<map><area href="http://example.org/foo" /></map></body></html>"""
            response = HtmlResponse("http://example.org", body=body, encoding="utf-8")
            lx = self.extractor_cls()
            lx.extract_links(response)
            lx.extract_links(response)
            lx.extract_links(response)
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.org/foo",
                        text="",
                        fragment="",
                        nofollow=False,
                    )
                ],
            )

        def test_encoded_url(self):
            body = b"""<html><body><div><a href="?page=2">BinB</a></body></html>"""
            response = HtmlResponse(
                "http://known.fm/AC%2FDC/", body=body, encoding="utf8"
            )
            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://known.fm/AC%2FDC/?page=2",
                        text="BinB",
                        fragment="",
                        nofollow=False,
                    ),
                ],
            )

        def test_encoded_url_in_restricted_xpath(self):
            body = b"""<html><body><div><a href="?page=2">BinB</a></body></html>"""
            response = HtmlResponse(
                "http://known.fm/AC%2FDC/", body=body, encoding="utf8"
            )
            lx = self.extractor_cls(restrict_xpaths="//div")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://known.fm/AC%2FDC/?page=2",
                        text="BinB",
                        fragment="",
                        nofollow=False,
                    ),
                ],
            )

        def test_ignored_extensions(self):
            # jpg is ignored by default
            html = b"""<a href="page.html">asd</a> and <a href="photo.jpg">"""
            response = HtmlResponse("http://example.org/", body=html)
            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.org/page.html", text="asd"),
                ],
            )

            # override denied extensions
            lx = self.extractor_cls(deny_extensions=["html"])
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.org/photo.jpg"),
                ],
            )

        def test_process_value(self):
            """Test restrict_xpaths with encodings"""
            html = b"""
<a href="javascript:goToPage('../other/page.html','photo','width=600,height=540,scrollbars'); return false">Text</a>
<a href="/about.html">About us</a>
            """
            response = HtmlResponse(
                "http://example.org/somepage/index.html",
                body=html,
                encoding="windows-1252",
            )

            def process_value(value):
                m = re.search(r"javascript:goToPage\('(.*?)'", value)
                if m:
                    return m.group(1)

            lx = self.extractor_cls(process_value=process_value)
            self.assertEqual(
                lx.extract_links(response),
                [Link(url="http://example.org/other/page.html", text="Text")],
            )

        def test_base_url_with_restrict_xpaths(self):
            html = b"""<html><head><title>Page title<title><base href="http://otherdomain.com/base/" />
            <body><p><a href="item/12.html">Item 12</a></p>
            </body></html>"""
            response = HtmlResponse("http://example.org/somepage/index.html", body=html)
            lx = self.extractor_cls(restrict_xpaths="//p")
            self.assertEqual(
                lx.extract_links(response),
                [Link(url="http://otherdomain.com/base/item/12.html", text="Item 12")],
            )

        def test_attrs(self):
            lx = self.extractor_cls(attrs="href")
            page4_url = "http://example.com/page%204.html"

            self.assertEqual(
                lx.extract_links(self.response),
                [
                    Link(url="http://example.com", text=""),
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                    Link(url="http://www.google.com/something", text=""),
                    Link(url="http://example.com/innertag.html", text="inner tag"),
                    Link(url=page4_url, text="href with whitespaces"),
                ],
            )

            lx = self.extractor_cls(
                attrs=("href", "src"), tags=("a", "area", "img"), deny_extensions=()
            )
            self.assertEqual(
                lx.extract_links(self.response),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample2.jpg", text=""),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                    Link(url="http://www.google.com/something", text=""),
                    Link(url="http://example.com/innertag.html", text="inner tag"),
                    Link(url=page4_url, text="href with whitespaces"),
                ],
            )

            lx = self.extractor_cls(attrs=None)
            self.assertEqual(
                lx.extract_links(self.response),
                [
                    Link(url="http://example.com", text=""),
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample3.html", text="sample 3 text"),
                    Link(
                        url="http://example.com/sample3.html#foo",
                        text="sample 3 repetition with fragment",
                    ),
                    Link(url="http://www.google.com/something", text=""),
                    Link(url="http://example.com/innertag.html", text="inner tag"),
                    Link(url=page4_url, text="href with whitespaces"),
                ],
            )

            html = b"""<html>
                <head>
                    <base href="http://example.com">
                    <title>Sample page with links for testing LinkExtractor</title>
                </head>
                <body>
                    <div id="wrapper">
                    <div id="subwrapper">
                        <area href="sample1.html" alt="sample1">
                        <a href="sample2.html">sample 2<img src="sample2.jpg" alt="sample2"></a>
                    </div>
                    <a href="http://example.com/sample3.html" title="sample 3" ping="http://example.com/sample3_1.html" >sample 3 text</a>
                    <a href="sample3.html">sample 3 repetition</a>
                    <a href="sample3.html">sample 3 repetition</a>
                    <a href="sample3.html#foo">sample 3 repetition with fragment</a>
                    <a href="http://www.google.com/something"></a>
                    <a href="http://example.com/innertag.html"><strong>inner</strong> tag</a>
                    <a href="page%204.html">href with whitespaces</a>
                    </div>
                </body>
                </html>
            """
            response = HtmlResponse("http://example.org/somepage/index.html", body=html)

            lx = self.extractor_cls(tags=("a",), deny_attrs="href")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample%203", text="sample 3 text"),
                    Link(url="http://example.com/sample3_1.html", text="sample 3 text"),
                ],
            )

            html = b"""<html>
                <head>
                    <base href="http://example.com">
                    <title>Sample page with links for testing LinkExtractor</title>
                </head>
                <body>
                    <div id="wrapper">
                    <div id="subwrapper">
                        <area href="sample1.html" alt="sample1" ping="http://example.com/sample1_1.html">
                        <a href="sample2.html">sample 2<img src="sample2.jpg" alt="sample2"></a>
                    </div>
                    </div>
                </body>
                </html>
            """
            response = HtmlResponse("http://example.org/somepage/index.html", body=html)

            lx = self.extractor_cls(deny_tags="a", deny_attrs="ping")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com", text=""),
                    Link(url="http://example.com/sample1.html", text=""),
                ],
            )

        def test_tags(self):
            html = (
                b'<html><area href="sample1.html"></area>'
                b'<a href="sample2.html">sample 2</a><img src="sample2.jpg"/></html>'
            )
            response = HtmlResponse("http://example.com/index.html", body=html)

            lx = self.extractor_cls(tags=None)
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

            lx = self.extractor_cls(tags="area")
            self.assertEqual(
                lx.extract_links(response),
                [Link(url="http://example.com/sample1.html", text="")],
            )

            lx = self.extractor_cls(tags="a")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                ],
            )

            lx = self.extractor_cls(
                tags=("a", "img"), attrs=("href", "src"), deny_extensions=()
            )
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample2.html", text="sample 2"),
                    Link(url="http://example.com/sample2.jpg", text=""),
                ],
            )

            lx = self.extractor_cls(attrs=("href",), deny_tags="a")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(url="http://example.com/sample1.html", text=""),
                ],
            )

        def test_tags_attrs(self):
            html = b"""
            <html><body>
            <div id="item1" data-url="get?id=1"><a href="#">Item 1</a></div>
            <div id="item2" data-url="get?id=2"><a href="#">Item 2</a></div>
            </body></html>
            """
            response = HtmlResponse("http://example.com/index.html", body=html)

            lx = self.extractor_cls(tags="div", attrs="data-url")
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.com/get?id=1",
                        text="Item 1",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/get?id=2",
                        text="Item 2",
                        fragment="",
                        nofollow=False,
                    ),
                ],
            )

            lx = self.extractor_cls(tags=("div",), attrs=("data-url",))
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.com/get?id=1",
                        text="Item 1",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/get?id=2",
                        text="Item 2",
                        fragment="",
                        nofollow=False,
                    ),
                ],
            )

        def test_xhtml(self):
            xhtml = b"""
    <?xml version="1.0"?>
    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    <head>
        <title>XHTML document title</title>
    </head>
    <body>
        <div class='links'>
        <p><a href="/about.html">About us</a></p>
        </div>
        <div>
        <p><a href="/follow.html">Follow this link</a></p>
        </div>
        <div>
        <p><a href="/nofollow.html" rel="nofollow">Dont follow this one</a></p>
        </div>
        <div>
        <p><a href="/nofollow2.html" rel="blah">Choose to follow or not</a></p>
        </div>
        <div>
        <p><a href="http://google.com/something" rel="external nofollow">External link not to follow</a></p>
        </div>
    </body>
    </html>
            """

            response = HtmlResponse("http://example.com/index.xhtml", body=xhtml)

            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.com/about.html",
                        text="About us",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/follow.html",
                        text="Follow this link",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/nofollow.html",
                        text="Dont follow this one",
                        fragment="",
                        nofollow=True,
                    ),
                    Link(
                        url="http://example.com/nofollow2.html",
                        text="Choose to follow or not",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://google.com/something",
                        text="External link not to follow",
                        nofollow=True,
                    ),
                ],
            )

            response = XmlResponse("http://example.com/index.xhtml", body=xhtml)

            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="http://example.com/about.html",
                        text="About us",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/follow.html",
                        text="Follow this link",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.com/nofollow.html",
                        text="Dont follow this one",
                        fragment="",
                        nofollow=True,
                    ),
                    Link(
                        url="http://example.com/nofollow2.html",
                        text="Choose to follow or not",
                        fragment="",
                        nofollow=False,
                    ),
                    Link(
                        url="http://google.com/something",
                        text="External link not to follow",
                        nofollow=True,
                    ),
                ],
            )

        def test_link_wrong_href(self):
            html = b"""
            <a href="http://example.org/item1.html">Item 1</a>
            <a href="http://[example.org/item2.html">Item 2</a>
            <a href="http://example.org/item3.html">Item 3</a>
            """
            response = HtmlResponse("http://example.org/index.html", body=html)
            lx = self.extractor_cls()
            self.assertEqual(
                list(lx.extract_links(response)),
                [
                    Link(
                        url="http://example.org/item1.html",
                        text="Item 1",
                        nofollow=False,
                    ),
                    Link(
                        url="http://example.org/item3.html",
                        text="Item 3",
                        nofollow=False,
                    ),
                ],
            )

        def test_ftp_links(self):
            body = b"""
            <html><body>
            <div><a href="ftp://www.external.com/">An Item</a></div>
            </body></html>"""
            response = HtmlResponse(
                "http://www.example.com/index.html", body=body, encoding="utf8"
            )
            lx = self.extractor_cls()
            self.assertEqual(
                lx.extract_links(response),
                [
                    Link(
                        url="ftp://www.external.com/",
                        text="An Item",
                        fragment="",
                        nofollow=False,
                    ),
                ],
            )

        def test_pickle_extractor(self):
            lx = self.extractor_cls()
            self.assertIsInstance(pickle.loads(pickle.dumps(lx)), self.extractor_cls)

        def test_link_extractor_aggregation(self):
            """When a parameter like restrict_css is used, the underlying
            implementation calls its internal link extractor once per selector
            matching the specified restrictions, and then aggregates the
            extracted links.

            Test that aggregation respects the unique and canonicalize
            parameters.
            """
            # unique=True (default), canonicalize=False (default)
            lx = self.extractor_cls(restrict_css=("div",))
            response = HtmlResponse(
                "https://example.com",
                body=b"""
                    <div>
                        <a href="/a">a1</a>
                        <a href="/b?a=1&b=2">b1</a>
                    </div>
                    <div>
                        <a href="/a">a2</a>
                        <a href="/b?b=2&a=1">b2</a>
                    </div>
                """,
            )
            actual = lx.extract_links(response)
            self.assertEqual(
                actual,
                [
                    Link(url="https://example.com/a", text="a1"),
                    Link(url="https://example.com/b?a=1&b=2", text="b1"),
                    Link(url="https://example.com/b?b=2&a=1", text="b2"),
                ],
            )

            # unique=True (default), canonicalize=True
            lx = self.extractor_cls(restrict_css=("div",), canonicalize=True)
            response = HtmlResponse(
                "https://example.com",
                body=b"""
                    <div>
                        <a href="/a">a1</a>
                        <a href="/b?a=1&b=2">b1</a>
                    </div>
                    <div>
                        <a href="/a">a2</a>
                        <a href="/b?b=2&a=1">b2</a>
                    </div>
                """,
            )
            actual = lx.extract_links(response)
            self.assertEqual(
                actual,
                [
                    Link(url="https://example.com/a", text="a1"),
                    Link(url="https://example.com/b?a=1&b=2", text="b1"),
                ],
            )

            # unique=False, canonicalize=False (default)
            lx = self.extractor_cls(restrict_css=("div",), unique=False)
            response = HtmlResponse(
                "https://example.com",
                body=b"""
                    <div>
                        <a href="/a">a1</a>
                        <a href="/b?a=1&b=2">b1</a>
                    </div>
                    <div>
                        <a href="/a">a2</a>
                        <a href="/b?b=2&a=1">b2</a>
                    </div>
                """,
            )
            actual = lx.extract_links(response)
            self.assertEqual(
                actual,
                [
                    Link(url="https://example.com/a", text="a1"),
                    Link(url="https://example.com/b?a=1&b=2", text="b1"),
                    Link(url="https://example.com/a", text="a2"),
                    Link(url="https://example.com/b?b=2&a=1", text="b2"),
                ],
            )

            # unique=False, canonicalize=True
            lx = self.extractor_cls(
                restrict_css=("div",), unique=False, canonicalize=True
            )
            response = HtmlResponse(
                "https://example.com",
                body=b"""
                    <div>
                        <a href="/a">a1</a>
                        <a href="/b?a=1&b=2">b1</a>
                    </div>
                    <div>
                        <a href="/a">a2</a>
                        <a href="/b?b=2&a=1">b2</a>
                    </div>
                """,
            )
            actual = lx.extract_links(response)
            self.assertEqual(
                actual,
                [
                    Link(url="https://example.com/a", text="a1"),
                    Link(url="https://example.com/b?a=1&b=2", text="b1"),
                    Link(url="https://example.com/a", text="a2"),
                    Link(url="https://example.com/b?a=1&b=2", text="b2"),
                ],
            )


class LxmlLinkExtractorTestCase(Base.LinkExtractorTestCase):
    extractor_cls = LxmlLinkExtractor

    def test_link_wrong_href(self):
        html = b"""
        <a href="http://example.org/item1.html">Item 1</a>
        <a href="http://[example.org/item2.html">Item 2</a>
        <a href="http://example.org/item3.html">Item 3</a>
        """
        response = HtmlResponse("http://example.org/index.html", body=html)
        lx = self.extractor_cls()
        self.assertEqual(
            list(lx.extract_links(response)),
            [
                Link(
                    url="http://example.org/item1.html", text="Item 1", nofollow=False
                ),
                Link(
                    url="http://example.org/item3.html", text="Item 3", nofollow=False
                ),
            ],
        )

    def test_link_restrict_text(self):
        html = b"""
        <a href="http://example.org/item1.html">Pic of a cat</a>
        <a href="http://example.org/item2.html">Pic of a dog</a>
        <a href="http://example.org/item3.html">Pic of a cow</a>
        """
        response = HtmlResponse("http://example.org/index.html", body=html)
        # Simple text inclusion test
        lx = self.extractor_cls(restrict_text="dog")
        self.assertEqual(
            list(lx.extract_links(response)),
            [
                Link(
                    url="http://example.org/item2.html",
                    text="Pic of a dog",
                    nofollow=False,
                ),
            ],
        )
        # Unique regex test
        lx = self.extractor_cls(restrict_text=r"of.*dog")
        self.assertEqual(
            list(lx.extract_links(response)),
            [
                Link(
                    url="http://example.org/item2.html",
                    text="Pic of a dog",
                    nofollow=False,
                ),
            ],
        )
        # Multiple regex test
        lx = self.extractor_cls(restrict_text=[r"of.*dog", r"of.*cat"])
        self.assertEqual(
            list(lx.extract_links(response)),
            [
                Link(
                    url="http://example.org/item1.html",
                    text="Pic of a cat",
                    nofollow=False,
                ),
                Link(
                    url="http://example.org/item2.html",
                    text="Pic of a dog",
                    nofollow=False,
                ),
            ],
        )

    @mark.skipif(
        Version(w3lib_version) < Version("2.0.0"),
        reason=(
            "Before w3lib 2.0.0, w3lib.url.safe_url_string would not complain "
            "about an invalid port value."
        ),
    )
    def test_skip_bad_links(self):
        html = b"""
        <a href="http://example.org:non-port">Why would you do this?</a>
        <a href="http://example.org/item2.html">Good Link</a>
        <a href="http://example.org/item3.html">Good Link 2</a>
        """
        response = HtmlResponse("http://example.org/index.html", body=html)
        lx = self.extractor_cls()
        self.assertEqual(
            list(lx.extract_links(response)),
            [
                Link(
                    url="http://example.org/item2.html",
                    text="Good Link",
                    nofollow=False,
                ),
                Link(
                    url="http://example.org/item3.html",
                    text="Good Link 2",
                    nofollow=False,
                ),
            ],
        )

    def test_link_allowed_is_false_with_empty_url(self):
        bad_link = Link("")
        self.assertFalse(LxmlLinkExtractor()._link_allowed(bad_link))

    def test_link_allowed_is_false_with_bad_url_prefix(self):
        bad_link = Link("htp://should_be_http.example")
        self.assertFalse(LxmlLinkExtractor()._link_allowed(bad_link))

    def test_link_allowed_is_false_with_missing_url_prefix(self):
        bad_link = Link("should_have_prefix.example")
        self.assertFalse(LxmlLinkExtractor()._link_allowed(bad_link))
