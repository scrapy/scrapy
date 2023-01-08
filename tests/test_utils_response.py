# flake8: noqa  TODO: remove this line

import unittest
import warnings
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import HtmlResponse, Response, TextResponse, XmlResponse
from scrapy.http.headers import Headers
from scrapy.responsetypes import ResponseTypes
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes
from scrapy.utils.response import (
    get_meta_refresh,
    get_response_class,
    open_in_browser,
    response_httprepr,
    response_status_message,
)


__doctests__ = ['scrapy.utils.response']


# Scenarios that work the same with the previously-used, deprecated
# scrapy.responsetypes.responsetypes.from_args
PRE_XTRACTMIME_SCENARIOS = (
    # Even if the body is binary, if the Content-Type says it is text, we
    # interpret it as text, as long as the Content-Type is not one of the 4
    # affected by the Apache bug.
    #
    # https://mimesniff.spec.whatwg.org/#interpreting-the-resource-metadata
    *(
        (
            {
                'body': b'\x00\x01\xff',
                'headers': Headers({'Content-Type': [content_type]}),
            },
            TextResponse,
        )
        for content_type in (
            'text/json',
            # text/plain variants *not* affected by the Apache bug
            'text/plain; charset=Iso-8859-1',
            'text/plain; charset=utf-8',
            'text/plain; charset=windows-1252',
        )
    ),

    # JavaScript MIME types should trigger a TextResponse.
    #
    # https://mimesniff.spec.whatwg.org/#javascript-mime-type
    *(
        (
            {'headers': Headers({'Content-Type': [content_type]})},
            TextResponse,
        )
        for content_type in (
            'application/javascript',
            'application/x-javascript',
            'text/ecmascript',
            'text/javascript',
            'text/javascript1.0',
            'text/javascript1.1',
            'text/javascript1.2',
            'text/javascript1.3',
            'text/javascript1.4',
            'text/javascript1.5',
            'text/jscript',
            'text/livescript',
            'text/x-ecmascript',
            'text/x-javascript',
        )
    ),

    # JSON MIME types should trigger a TextResponse.
    #
    # https://mimesniff.spec.whatwg.org/#json-mime-type
    *(
        (
            {'headers': Headers({'Content-Type': [content_type]})},
            TextResponse,
        )
        for content_type in (
            'application/json',
            'text/json',
        )
    ),

    # Compressed content should be of type Response until uncompressed.
    *(
        (
            {
                'headers': Headers(
                    {
                        'Content-Encoding': ['zip'],
                        'Content-Type': [content_type],
                    }
                )
            },
            Response,
        )
        for content_type in (
            'text/html',
            'text/xml',
            'text/plain',
        )
    ),

    *(
        (
            {
                'headers': Headers(
                    {'Content-Type': [mime_type]}
                ),
            },
            load_object(class_path),
        )
        for mime_type, class_path in ResponseTypes.CLASSES.items()
    ),
    (
        {
            'url': 'http://www.example.com/data.csv',
        },
        TextResponse,
    ),
    (
        {
            'url': 'http://www.example.com/item/',
            'headers': Headers({'Content-Type': ['text/html; charset=utf-8']}),
        },
        HtmlResponse,
    ),
    (
        {
            'url': 'http://www.example.com/page/',
            'headers': Headers(
                {
                    'Content-Disposition': [
                        'attachment; filename="data.xml.gz"',
                    ]
                }
            ),
            'body': b'\x01\x02',
        },
        Response,
    ),
    (
        {'body': b'Some plain\0 text data with\0 tabs and null bytes\0'},
        TextResponse,
    ),
    (
        {
            'body': b'\x03\x02\xdf\xdd\x23',
            'headers': Headers({'Content-Encoding': 'UTF-8'}),
        },
        Response,
    ),
    (
        {
            'body': b'\x00\x01\xff',
            'url': '://www.example.com/item/',
            'headers': Headers({'Content-Type': ['text/plain']}),
        },
        TextResponse,
    ),
    ({'url': 'http://www.example.com/item/file.html'}, HtmlResponse),
    ({'body': b'<html><head><title>Hello</title></head>'}, HtmlResponse),
    ({'body': b'<?xml version="1.0" encoding="utf-8"'}, XmlResponse),
    (
        {'body': b'Some plain text data\1\2 with tabs and\n null bytes\0'},
        Response,
    ),
    # https://codersblock.com/blog/the-smallest-valid-html5-page/
    ({'body': b'<!DOCTYPE html>\n<title>.</title>'}, HtmlResponse),
    (
        {
            'body': b'\x01\x02',
            'headers': Headers({'Content-Type': ['application/pdf']}),
        },
        Response,
    ),
    (
        {'headers': Headers({'Content-Type': ['application/x-json']})},
        TextResponse,
    ),
    (
        {'headers': Headers({'Content-Type': ['application/x-javascript']})},
        TextResponse,
    ),
    (
        {
            'headers': Headers(
                {'Content-Type': ['application/json-amazonui-streaming']}
            )
        },
        TextResponse,
    ),
    (
        {
            'headers': Headers(
                {'Content-Disposition': ['attachment; filename="data.xml.gz"']}
            ),
            'url': 'http://www.example.com/page/',
        },
        Response,
    ),
    ({'headers': Headers({'Content-Type': ['application/pdf']})}, Response),
    (
        {
            'url': 'http://www.example.com/page/file.html',
            'headers': Headers({'Content-Type': 'application/octet-stream'}),
        },
        HtmlResponse,
    ),
    (
        {
            'url': 'http://www.example.com/item/file.xml',
            'headers': Headers({'Content-Type': 'application/octet-stream'}),
        },
        XmlResponse,
    ),
    (
        {
            'url': 'http://www.example.com/item/file.html',
            'headers': Headers({'Content-Type': 'application/octet-stream'}),
        },
        HtmlResponse,
    ),
    ({'url': 'http://www.example.com/item/file.pdf'}, Response),
    ({'filename': 'file.pdf'}, Response),
    (
        {
            'body': b'<!DOCTYPE html>\n<title>.</title>',
            'url': 'http://www.example.com',
        },
        HtmlResponse,
    ),
)

# Scenarios that work differently with the previously-used, deprecated
# scrapy.responsetypes.responsetypes.from_args
POST_XTRACTMIME_SCENARIOS = (
    # A known Apache bug may cause a server to send files with Content-Type set
    # to "text/plain", "text/plain; charset=ISO-8859-1",
    # "text/plain; charset=iso-8859-1", or "text/plain; charset=UTF-8",
    # regardless of the actual file content.
    #
    # They should be treated as binary if their content is binary, and as
    # text/plain otherwise.
    #
    # https://mimesniff.spec.whatwg.org/#interpreting-the-resource-metadata
    *(
        (
            {
                'body': b'\x00\x01\xff',
                'headers': Headers({'Content-Type': [content_type]}),
            },
            Response,
        )
        for content_type in (
            'text/plain',
            'text/plain; charset=ISO-8859-1',
            'text/plain; charset=iso-8859-1',
            'text/plain; charset=UTF-8',
        )
    ),

    # If the body is empty, it contains no binary data bytes, hence body-based
    # MIME type detection must interpret the result as text.
    #
    # https://mimesniff.spec.whatwg.org/#identifying-a-resource-with-an-unknown-mime-type
    ({}, TextResponse),
    ({'url': '/tmp/temp^'}, TextResponse),

    # Body-based PDF detection
    #
    # https://mimesniff.spec.whatwg.org/#identifying-a-resource-with-an-unknown-mime-type
    ({'body': b'%PDF-1.4'}, Response),

    # JavaScript MIME types should trigger a TextResponse.
    #
    # https://mimesniff.spec.whatwg.org/#javascript-mime-type
    *(
        (
            {'headers': Headers({'Content-Type': [content_type]})},
            TextResponse,
        )
        for content_type in (
            'application/ecmascript',
            'application/x-ecmascript',
        )
    ),

    # JSON MIME types should trigger a TextResponse.
    #
    # https://mimesniff.spec.whatwg.org/#json-mime-type
    *(
        (
            {'headers': Headers({'Content-Type': [content_type]})},
            TextResponse,
        )
        for content_type in (
            'application/foo+json',
            'application/ld+json',
        )
    ),


    # Compressed content should be of type Response until uncompressed.
    #
    # When it comes to compression, we trust the encoding from the following
    # sources, in the following order:
    #
    # 1,  Content-Encoding HTTP header
    #
    # 2.  File extension of the file name of the Content-Disposition HTTP
    #     header.
    #
    # 3.  File extension of the file name if the resource comes through a
    #     file-based protocol (FTP, local file system).
    #(
        #{
            #'url': 'file.html',
            #'body': b'<!DOCTYPE html>\n<title>.</title>',
            #'headers': Headers(
                #{
                    #'Content-Disposition': [
                        #'attachment; filename="file.html"'
                    #],
                    #'Content-Encoding': ['zip'],
                    #'Content-Type': ['text/html'],
                #}
            #),
        #},
        #Response,
    #),
    #(
        #{
            #'url': 'file.html',
            #'body': b'<!DOCTYPE html>\n<title>.</title>',
            #'headers': Headers(
                #{
                    #'Content-Disposition': [
                        #'attachment; filename="file.html.zip"'
                    #],
                    #'Content-Type': ['text/html'],
                #}
            #),
        #},
        #Response,
    #),
    #(
        #{
            #'url': 'file.html.zip',
            #'body': b'<!DOCTYPE html>\n<title>.</title>',
        #},
        #Response,
    #),

    # HTTP headers take priority over local file extensions.
    #(
        #{
            #'url': 'file.html.zip',
            #'body': b'<!DOCTYPE html>\n<title>.</title>',
            #'headers': Headers(
                #{
                    #'Content-Type': ['text/html'],
                #}
            #),
        #},
        #HtmlResponse,
    #),

    (
        {
            'body': b'Some plain text',
            'headers': Headers({'Content-Type': 'application/octet-stream'}),
        },
        Response,
    ),
    ({'body': b'\x0c\x1b'}, TextResponse),
    ({'body': b'this is not <html>'}, TextResponse),
    ({'body': b'this is not <?xml'}, TextResponse),
    (
        {
            'url': 'http://www.example.com/item/file.xml',
            'headers': Headers(
                {
                    'Content-Disposition': [
                        'attachment; filename="data.xml.gz"'
                    ],
                    'Content-Type': 'application/octet-stream',
                }
            ),
        },
        Response,
    ),
)


@pytest.mark.parametrize(
    'kwargs,response_class',
    (
        *PRE_XTRACTMIME_SCENARIOS,
        *POST_XTRACTMIME_SCENARIOS,
    ),
)
def test_get_response_class_http(kwargs, response_class):
    kwargs = dict(kwargs)
    if 'headers' in kwargs:
        kwargs['http_headers'] = kwargs.pop('headers')
    if 'filename' in kwargs:
        assert 'url' not in kwargs
        kwargs['url'] = kwargs.pop('filename')
    assert get_response_class(**kwargs) == response_class


class ResponseUtilsTest(unittest.TestCase):
    dummy_response = TextResponse(url='http://example.org/', body=b'dummy_response')

    def test_response_httprepr(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)

            r1 = Response("http://www.example.com")
            self.assertEqual(response_httprepr(r1), b'HTTP/1.1 200 OK\r\n\r\n')

            r1 = Response("http://www.example.com", status=404,
                          headers={"Content-type": "text/html"}, body=b"Some body")
            self.assertEqual(response_httprepr(r1),
                             b'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\nSome body')

            r1 = Response("http://www.example.com", status=6666,
                          headers={"Content-type": "text/html"}, body=b"Some body")
            self.assertEqual(response_httprepr(r1),
                             b'HTTP/1.1 6666 \r\nContent-Type: text/html\r\n\r\nSome body')

    def test_open_in_browser(self):
        url = "http:///www.example.com/some/page.html"
        body = b"<html> <head> <title>test page</title> </head> <body>test body</body> </html>"

        def browser_open(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace('file://', '')
            bbody = Path(path).read_bytes()
            self.assertIn(b'<base href="' + to_bytes(url) + b'">', bbody)
            return True
        response = HtmlResponse(url, body=body)
        assert open_in_browser(response, _openfunc=browser_open), "Browser not called"

        resp = Response(url, body=body)
        self.assertRaises(TypeError, open_in_browser, resp, debug=True)

    def test_get_meta_refresh(self):
        r1 = HtmlResponse("http://www.example.com", body=b"""
        <html>
        <head><title>Dummy</title><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r2 = HtmlResponse("http://www.example.com", body=b"""
        <html>
        <head><title>Dummy</title><noScript>
        <meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        </noSCRIPT>
        <body>blahablsdfsal&amp;</body>
        </html>""")
        r3 = HtmlResponse("http://www.example.com", body=b"""
    <noscript><meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage</noscript>
    <script type="text/javascript">
    if(!checkCookies()){
        document.write('<meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage">');
    }
    </script>
        """)
        self.assertEqual(get_meta_refresh(r1), (5.0, 'http://example.org/newpage'))
        self.assertEqual(get_meta_refresh(r2), (None, None))
        self.assertEqual(get_meta_refresh(r3), (None, None))

    def test_response_status_message(self):
        self.assertEqual(response_status_message(200), '200 OK')
        self.assertEqual(response_status_message(404), '404 Not Found')
        self.assertEqual(response_status_message(573), "573 Unknown Status")

    def test_inject_base_url(self):
        url = "http://www.example.com"

        def check_base_url(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace('file://', '')
            bbody = Path(path).read_bytes()
            self.assertEqual(bbody.count(b'<base href="' + to_bytes(url) + b'">'), 1)
            return True

        r1 = HtmlResponse(url, body=b"""
        <html>
            <head><title>Dummy</title></head>
            <body><p>Hello world.</p></body>
        </html>""")
        r2 = HtmlResponse(url, body=b"""
        <html>
            <head id="foo"><title>Dummy</title></head>
            <body>Hello world.</body>
        </html>""")
        r3 = HtmlResponse(url, body=b"""
        <html>
            <head><title>Dummy</title></head>
            <body>
                <header>Hello header</header>
                <p>Hello world.</p>
            </body>
        </html>""")
        r4 = HtmlResponse(url, body=b"""
        <html>
            <!-- <head>Dummy comment</head> -->
            <head><title>Dummy</title></head>
            <body><p>Hello world.</p></body>
        </html>""")
        r5 = HtmlResponse(url, body=b"""
        <html>
            <!--[if IE]>
            <head><title>IE head</title></head>
            <![endif]-->
            <!--[if !IE]>-->
            <head><title>Standard head</title></head>
            <!--<![endif]-->
            <body><p>Hello world.</p></body>
        </html>""")

        assert open_in_browser(r1, _openfunc=check_base_url), "Inject base url"
        assert open_in_browser(r2, _openfunc=check_base_url), "Inject base url with argumented head"
        assert open_in_browser(r3, _openfunc=check_base_url), "Inject unique base url with misleading tag"
        assert open_in_browser(r4, _openfunc=check_base_url), "Inject unique base url with misleading comment"
        assert open_in_browser(r5, _openfunc=check_base_url), "Inject unique base url with conditional comment"
