import unittest
from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

import pytest
from xtractmime import BINARY_BYTES, RESOURCE_HEADER_BUFFER_LENGTH

from scrapy.http import HtmlResponse, JsonResponse, Response, TextResponse, XmlResponse
from scrapy.http.headers import Headers
from scrapy.responsetypes import ResponseTypes
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes
from scrapy.utils.response import (
    _get_encoding_or_mime_type_from_headers,
    get_meta_refresh,
    get_response_class,
    open_in_browser,
    response_status_message,
)

__doctests__ = ["scrapy.utils.response"]


# https://mimesniff.spec.whatwg.org/#interpreting-the-resource-metadata
PRE_XTRACTMIME_HTML_STARTS = (
    b"<!DOCTYPE HTML",
    b"<HTML",
)
POST_XTRACTMIME_HTML_STARTS = (
    b"<HEAD",
    b"<SCRIPT",
    b"<IFRAME",
    b"<H1",
    b"<DIV",
    b"<FONT",
    b"<TABLE",
    b"<A",
    b"<STYLE",
    b"<TITLE",
    b"<B",
    b"<BODY",
    b"<BR",
    b"<P",
    b"<!--",
)

NON_BINARY_ASCII_BYTES = (
    byte for byte in (bytes([byte]) for byte in range(128)) if byte not in BINARY_BYTES
)

# https://mimesniff.spec.whatwg.org/#whitespace-byte
WHITESPACE_BYTES = (
    b"\t",
    b"\n",
    b"\x0C",
    b"\r",
    b" ",
)


def odd_capitalize(value: bytes) -> bytes:
    """Make odd bytes lowecase and even bytes uppercase.

    >>> odd_capitalize(b'foobar')
    b'fOoBaR'
    """
    return b"".join(
        bytes([byte]).lower() if index % 2 == 0 else bytes([byte]).upper()
        for index, byte in enumerate(value)
    )


# Scenarios that work the same with the previously-used, deprecated
# scrapy.responsetypes.responsetypes.from_args
PRE_XTRACTMIME_SCENARIOS = (
    # Content-Type determines the type for the HTTP protocol.
    *(
        (
            {
                "url": f"{protocol}://example.com/foo",
                "headers": Headers(
                    {"Content-Type": content_type + content_type_parameters}
                ),
            },
            response_class,
        )
        for protocol in ("http", "https")
        # Make sure that MIME parameters do not break response class choice.
        for content_type_parameters in ("", "; foo=bar")
        for content_type, response_class in (
            ("text/plain", TextResponse),
            ("text/html", HtmlResponse),
            ("text/xml", XmlResponse),
            *(
                (mime_type, load_object(class_path))
                for mime_type, class_path in ResponseTypes.CLASSES.items()
                if mime_type
                not in (
                    # “Note that XHTML is best parsed as XML”
                    # https://lxml.de/parsing.html
                    "application/xhtml+xml",
                    "application/vnd.wap.xhtml+xml",
                )
            ),
            # JavaScript MIME types should trigger a TextResponse.
            #
            # https://mimesniff.spec.whatwg.org/#javascript-mime-type
            *(
                (mime_type, TextResponse)
                for mime_type in (
                    "application/javascript",
                    "application/x-javascript",
                    "text/ecmascript",
                    "text/javascript",
                    "text/javascript1.0",
                    "text/javascript1.1",
                    "text/javascript1.2",
                    "text/javascript1.3",
                    "text/javascript1.4",
                    "text/javascript1.5",
                    "text/jscript",
                    "text/livescript",
                    "text/x-ecmascript",
                    "text/x-javascript",
                    # Unofficial
                    "application/x-javascript",
                )
            ),
            # JSON MIME types should trigger a JsonResponse.
            #
            # https://mimesniff.spec.whatwg.org/#json-mime-type
            *(
                (mime_type, JsonResponse)
                for mime_type in (
                    "application/json",
                    # Unofficial
                    "application/json-amazonui-streaming",
                    "application/x-json",
                )
            ),
        )
    ),
    # Content-Type triumphs body, except for:
    #
    # -   Binary content mislabeled as plain text due to an Apache bug
    #     https://mimesniff.spec.whatwg.org/#check-for-apache-bug-flag
    #     https://mimesniff.spec.whatwg.org/#rules-for-text-or-binary
    #
    # -   Feeds mislabeled as HTML
    #     https://mimesniff.spec.whatwg.org/#rules-for-distinguishing-if-a-resource-is-a-feed-or-html
    *(
        (
            {
                "body": body,
                "headers": Headers({"Content-Type": [content_type]}),
            },
            response_class,
        )
        for body, content_type, response_class in (
            *(
                (b"\x00\x01\xff", content_type, TextResponse)
                for content_type in (
                    # text/plain variants *not* affected by the Apache bug
                    "text/plain; charset=Iso-8859-1",
                    "text/plain; charset=utf-8",
                    "text/plain; charset=windows-1252",
                )
            ),
        )
    ),
    # Content-Type triumphs Content-Disposition.
    *(
        (
            {
                "url": f"{protocol}://example.com/a",
                "headers": Headers(
                    {
                        "Content-Disposition": [
                            f'attachment; filename="a.{file_extension}"',
                        ],
                        "Content-Type": [content_type],
                    }
                ),
            },
            response_class,
        )
        for protocol in ("http", "https")
        for file_extension, content_type, response_class in (
            ("html", "application/json", JsonResponse),
            ("xml", "application/json", JsonResponse),
        )
    ),
    # Compressed content should be of type Response until uncompressed.
    (
        {
            "headers": Headers(
                {
                    "Content-Encoding": ["zip"],
                    "Content-Type": ["text/html"],
                }
            )
        },
        Response,
    ),
    # We take the file extension of URL paths into account, except for HTTP
    # responses, because “they are unreliable and easily spoofed”.
    #
    # https://mimesniff.spec.whatwg.org/#interpreting-the-resource-metadata
    *(
        (
            {"url": f"{protocol}://example.com/a.{extension}"},
            response_class,
        )
        for protocol in ("file", "ftp")
        for extension, response_class in (
            ("gz", Response),
            ("html", HtmlResponse),
            ("json", JsonResponse),
            ("pdf", Response),
            ("txt", TextResponse),
            ("xml", XmlResponse),
        )
    ),
    # Unlike in a web browser, where an attachment Content-Disposition header
    # causes the response to be downloaded, and hence MIME sniffing becomes
    # irrelevant, in Scrapy those responses are handled the same as any, and
    # hence we take the file extension from Content-Disposition into account
    # to choose a response class, as a fallback when there is no Content-Type.
    *(
        (
            {
                "url": f"{protocol}://example.com/a",
                "headers": Headers(
                    {
                        "Content-Disposition": [
                            'attachment; filename="a.xml"',
                        ]
                    }
                ),
            },
            XmlResponse,
        )
        for protocol in ("http", "https")
    ),
    *(
        (
            {
                "url": f"{protocol}://example.com/a",
                "headers": Headers(
                    {
                        "Content-Disposition": [
                            'attachment; filename="a.html"',
                        ],
                        "Content-Type": "text/xml",
                    }
                ),
            },
            XmlResponse,
        )
        for protocol in ("http", "https")
    ),
    *(
        (
            {
                "url": f"{protocol}://example.com/a",
                "body": b"<?xml",
                "headers": Headers(
                    {
                        "Content-Disposition": [
                            'attachment; filename="a.html"',
                        ],
                    }
                ),
            },
            HtmlResponse,
        )
        for protocol in ("http", "https")
    ),
    # Without anything else, the body determines the response class.
    *(
        ({"body": body}, response_class)
        for body, response_class in (
            (b"<html><head><title>Hello</title></head>", HtmlResponse),
            (b'<?xml version="1.0" encoding="utf-8"', XmlResponse),
            # https://codersblock.com/blog/the-smallest-valid-html5-page/
            (b"<!DOCTYPE html>\n<title>.</title>", HtmlResponse),
            # https://mimesniff.spec.whatwg.org/#identifying-a-resource-with-an-unknown-mime-type
            *(
                (prefix + start + b">", HtmlResponse)
                for prefix in (
                    b"",
                    *(byte for byte in WHITESPACE_BYTES if byte != b"\x0c"),
                )
                for start in (
                    set_case(start)
                    for set_case in (bytes.lower, bytes.upper, odd_capitalize)
                    for start in PRE_XTRACTMIME_HTML_STARTS
                )
            ),
            *(
                (prefix + b"<?xml", XmlResponse)
                for prefix in (
                    b"",
                    *(byte for byte in WHITESPACE_BYTES if byte != b"\x0c"),
                )
            ),
            (b"\xfe\xffab", TextResponse),
            (b"\xff\xfeab", TextResponse),
            (b"\xef\xbb\xbfa", TextResponse),
            (b"\x00\x00\x01\x00", Response),
            (b"\x00\x00\x02\x00", Response),
            (b"\x89PNG\r\n\x1a\n", Response),
            (b"MThd\x00\x00\x00\x06", Response),
            (b"\x00\x00\x00\x0cftypmp4a", Response),
            (b"\x00\x00\x00\x14ftypabcdefghmp4a", Response),
            (
                # https://github.com/mathiasbynens/small/blob/267b39f682598eebb0dafe7590b1504be79b5cad/webm.webm
                (
                    b"\x1aE\xdf\xa3@ B\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B"
                    b"\xf3\x81\x08B\x82@\x04webm"
                ),
                Response,
            ),
            (
                # https://github.com/mathiasbynens/small/blob/267b39f682598eebb0dafe7590b1504be79b5cad/mp3.mp3
                (
                    b"\xff\xe3\x18\xc4\x00\x00\x00\x03H\x00\x00\x00\x00LAME3.9"
                    b"8.2\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                    b"\x00\x00\x00\x00\x00\x00\x00\x00"
                ),
                Response,
            ),
            (b"\x1f\x8b\x08", Response),
            (b"PK\x03\x04", Response),
            (b"Rar \x1a\x07\x00", Response),
            # A body is considered binary if its header (first 1445 bytes)
            # contains any binary data byte.
            *((byte, Response) for byte in BINARY_BYTES[1:]),
            *(
                (byte, TextResponse)
                for byte in NON_BINARY_ASCII_BYTES
                if byte not in (b"\x0c", b"\x1b")
            ),
            *(
                (b"a" * (RESOURCE_HEADER_BUFFER_LENGTH - 1) + byte, Response)
                for byte in BINARY_BYTES[1:]
            ),
            (b"a" * RESOURCE_HEADER_BUFFER_LENGTH + BINARY_BYTES[0], TextResponse),
        )
    ),
    # A Content-Type whose essence is "unknown/unknown", "application/unknown",
    # or "*/*" has the same effect as no Content-Type being defined.
    #
    # https://mimesniff.spec.whatwg.org/#mime-type-sniffing-algorithm
    *(
        (
            {
                "body": b"<?xml",
                "headers": Headers(
                    {"Content-Type": [content_type + content_type_suffix]}
                ),
            },
            XmlResponse,
        )
        for content_type_suffix in ("", "; foo=bar")
        for content_type in (
            "unknown/unknown",
            "application/unknown",
            "*/*",
        )
    ),
    *(
        (
            {
                "url": f"{protocol}://example.com/a",
                "headers": Headers(
                    {
                        "Content-Disposition": [
                            'attachment; filename="a.xml"',
                        ],
                        "Content-Type": [content_type + content_type_suffix],
                    }
                ),
            },
            XmlResponse,
        )
        for protocol in ("http", "https")
        for content_type_suffix in ("", "; foo=bar")
        for content_type in (
            "unknown/unknown",
            "application/unknown",
            "*/*",
        )
    ),
    # Content triumphs Content-Type when using HTTP or HTTPS and the
    # Content-Type is unknown or binary while the content is plain text. This
    # is a conscious divergence from the MIME Sniffing Standard for a better
    # web scraping experience.
    *(
        (
            {
                "url": f"{protocol}://example.com/foo",
                "headers": Headers({"Content-Type": content_type}),
                "body": body,
            },
            TextResponse,
        )
        for protocol in ("http", "https")
        for body in (
            b"",
            b"a",
            b"var a = 'b';",
            b'{"a": "b"}',
            b'.a {b: "c"}',
        )
        for content_type in (
            "application/octet-stream",
            "application/pdf",
            "application/custom",
            "application/bad-custom-json",  # Should end in +json
            "application/bad-custom-text",  # Should start with text/
            "application/bad-custom-xml",  # Should end in +xml
        )
    ),
)

# Scenarios that work differently with the previously-used, deprecated
# scrapy.responsetypes.responsetypes.from_args
POST_XTRACTMIME_SCENARIOS = (
    # Content-Type determines the type for the HTTP protocol.
    *(
        (
            {
                "url": f"{protocol}://example.com/foo",
                "headers": Headers({"Content-Type": content_type}),
            },
            response_class,
        )
        for protocol in ("http", "https")
        # Make sure that MIME parameters do not break response class choice.
        for content_type_parameters in ("", "; foo=bar")
        for content_type, response_class in (
            # “Note that XHTML is best parsed as XML”
            # https://lxml.de/parsing.html
            ("application/xhtml+xml", XmlResponse),
            ("application/vnd.wap.xhtml+xml", XmlResponse),
            # JavaScript MIME types should trigger a TextResponse.
            #
            # https://mimesniff.spec.whatwg.org/#javascript-mime-type
            *(
                (mime_type, TextResponse)
                for mime_type in (
                    "application/ecmascript",
                    "application/x-ecmascript",
                )
            ),
            # JSON MIME types should trigger a TextResponse.
            #
            # https://mimesniff.spec.whatwg.org/#json-mime-type
            *(
                (mime_type, JsonResponse)
                for mime_type in (
                    "application/foo+json",
                    "application/ld+json",
                    "text/json",
                )
            ),
            # XML MIME types should trigger an XmlResponse.
            #
            # https://mimesniff.spec.whatwg.org/#xml-mime-type
            *((mime_type, XmlResponse) for mime_type in ("application/foo+xml",)),
        )
    ),
    # Content-Type triumphs body, except for:
    #
    # -   Binary content mislabeled as plain text due to an Apache bug
    #     https://mimesniff.spec.whatwg.org/#check-for-apache-bug-flag
    #     https://mimesniff.spec.whatwg.org/#rules-for-text-or-binary
    #
    # -   Feeds mislabeled as HTML
    #     https://mimesniff.spec.whatwg.org/#rules-for-distinguishing-if-a-resource-is-a-feed-or-html
    *(
        (
            {
                "body": body,
                "headers": Headers({"Content-Type": [content_type]}),
            },
            response_class,
        )
        for body, content_type, response_class in (
            *(
                (b"\x00\x01\xff", content_type, Response)
                for content_type in (
                    "text/plain",
                    "text/plain; charset=ISO-8859-1",
                    "text/plain; charset=iso-8859-1",
                    "text/plain; charset=UTF-8",
                )
            ),
            (b"\x00\x01\xff", "text/json", JsonResponse),
            *(
                (body, "text/html", XmlResponse)
                for body in (
                    b"<rss",
                    b"<feed",
                    (
                        b"<rdf:RDF "
                        b"... http://purl.org/rss/1.0/ "
                        b"... http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                    ),
                    (
                        b"<rdf:RDF "
                        b"... http://www.w3.org/1999/02/22-rdf-syntax-ns# "
                        b"... http://purl.org/rss/1.0/"
                    ),
                )
            ),
        )
    ),
    # Compressed content should be of type Response until uncompressed.
    (
        {
            "headers": Headers(
                {
                    "Content-Disposition": [
                        'attachment; filename="a.html"',
                    ],
                    "Content-Encoding": ["zip"],
                }
            )
        },
        Response,
    ),
    (
        {
            "body": b"<html>",
            "headers": Headers(
                {
                    "Content-Encoding": ["zip"],
                }
            ),
        },
        Response,
    ),
    # If the body is empty, it contains no binary data bytes, hence body-based
    # MIME type detection must interpret the result as text.
    #
    # https://mimesniff.spec.whatwg.org/#identifying-a-resource-with-an-unknown-mime-type
    ({}, TextResponse),
    # We take the file extension of URL paths into account, except for HTTP
    # responses, because “they are unreliable and easily spoofed”.
    #
    # https://mimesniff.spec.whatwg.org/#interpreting-the-resource-metadata
    *(
        (
            {"url": f"{protocol}://example.com/a.{extension}"},
            response_class,
        )
        for protocol in ("file", "ftp")
        for extension, response_class in (
            # “Note that XHTML is best parsed as XML”
            # https://lxml.de/parsing.html
            ("xhtml", XmlResponse),
        )
    ),
    *(
        (
            {"url": f"{protocol}://example.com/a.html"},
            response_class,
        )
        for protocol, response_class in (
            *((protocol, TextResponse) for protocol in ("http", "https")),
        )
    ),
    # File extension triumphs body.
    (
        {
            "body": b"<html>",
            "headers": Headers(
                {
                    "Content-Disposition": [
                        'attachment; filename="a.gz"',
                    ],
                }
            ),
        },
        Response,
    ),
    (
        {
            "body": b"<html>",
            "url": "file:///a.gz",
        },
        Response,
    ),
    # Without anything else, the body determines the response class.
    *(
        ({"body": body}, response_class)
        for body, response_class in (
            # https://mimesniff.spec.whatwg.org/#identifying-a-resource-with-an-unknown-mime-type
            *(
                (start + b">", HtmlResponse)
                for start in (
                    set_case(start)
                    for set_case in (bytes.lower, bytes.upper, odd_capitalize)
                    for start in POST_XTRACTMIME_HTML_STARTS
                )
            ),
            *(
                (start + b" ", HtmlResponse)
                for start in (
                    set_case(start)
                    for set_case in (bytes.lower, bytes.upper, odd_capitalize)
                    for start in chain(
                        PRE_XTRACTMIME_HTML_STARTS,
                        POST_XTRACTMIME_HTML_STARTS,
                    )
                )
            ),
            *(
                (b"\x0c" + start + b">", HtmlResponse)
                for start in (
                    set_case(start)
                    for set_case in (bytes.lower, bytes.upper, odd_capitalize)
                    for start in PRE_XTRACTMIME_HTML_STARTS
                )
            ),
            (b"\x0c<?xml", XmlResponse),
            (b"%PDF-", Response),
            (b"%!PS-Adobe-", Response),
            (b"BM", Response),
            (b"GIF87a", Response),
            (b"GIF89a", Response),
            (b"RIFFabcdWEBPVP", Response),
            (b"\xff\xd8\xff", Response),
            (b"FORMabcdAIFF", Response),
            (b"ID3", Response),
            (b"OggS\x00", Response),
            (b"RIFFabcdAVI ", Response),
            (b"RIFFabcdWAVE", Response),
            # A body is considered binary if its header (first 1445 bytes)
            # contains any binary data byte.
            (BINARY_BYTES[0], Response),
            *((byte, TextResponse) for byte in (b"\x0c", b"\x1b")),
            (b"a" * (RESOURCE_HEADER_BUFFER_LENGTH - 1) + BINARY_BYTES[0], Response),
            *(
                (b"a" * RESOURCE_HEADER_BUFFER_LENGTH + byte, TextResponse)
                for byte in BINARY_BYTES[1:]
            ),
            # HTML and XML detection does not allow for unexpected content
            # before document start.
            (b"a<html>", TextResponse),
            (b"a<?xml", TextResponse),
        )
    ),
    # Content triumphs Content-Type when using HTTP or HTTPS and the
    # Content-Type is known and binary while the content is plain text. This is
    # a conscious divergence from the MIME Sniffing Standard for a better web
    # scraping experience.
    *(
        (
            {
                "url": (
                    f"{protocol}://example.com/foo"
                    if use_header
                    else f"{protocol}://example.com/foo.{file_extension}"
                ),
                "headers": (
                    Headers({"Content-Type": content_type}) if use_header else Headers()
                ),
                "body": b"\x00",
            },
            Response,
        )
        for protocol, use_header in (
            ("http", True),
            ("https", True),
            ("file", False),
            ("ftp", False),
        )
        for content_type, file_extension in (
            ("application/octet-stream", "bin"),
            ("application/pdf", "pdf"),
        )
    ),
    *(
        (
            {
                "url": f"{protocol}://example.com/foo.{file_extension}",
                "body": body,
            },
            Response,
        )
        for protocol in ("file", "ftp")
        for body in (b"", b"a")
        for file_extension in ("bin", "pdf")
    ),
)


@pytest.mark.parametrize(
    "kwargs,response_class",
    (
        *PRE_XTRACTMIME_SCENARIOS,
        *POST_XTRACTMIME_SCENARIOS,
    ),
)
def test_get_response_class_http(kwargs, response_class):
    kwargs = dict(kwargs)
    if "headers" in kwargs:
        kwargs["http_headers"] = kwargs.pop("headers")
    assert get_response_class(**kwargs) == response_class


@pytest.mark.parametrize(
    "headers,expected",
    (
        *(
            (
                Headers({"Content-Encoding": content_encoding_header}),
                (encoding, None),
            )
            for content_encoding_header, encoding in (
                (["gzip"], b"gzip"),
                (["gzip", "compress"], b"compress"),
                (["deflate, br"], b"br"),
            )
        ),
    ),
)
def test_get_encoding_or_mime_type_from_headers(headers, expected):
    assert _get_encoding_or_mime_type_from_headers(headers) == expected


class ResponseUtilsTest(unittest.TestCase):
    dummy_response = TextResponse(url="http://example.org/", body=b"dummy_response")

    def test_open_in_browser(self):
        url = "http:///www.example.com/some/page.html"
        body = b"<html> <head> <title>test page</title> </head> <body>test body</body> </html>"

        def browser_open(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace("file://", "")
            bbody = Path(path).read_bytes()
            self.assertIn(b'<base href="' + to_bytes(url) + b'">', bbody)
            return True

        response = HtmlResponse(url, body=body)
        assert open_in_browser(response, _openfunc=browser_open), "Browser not called"

        resp = Response(url, body=body)
        self.assertRaises(TypeError, open_in_browser, resp, debug=True)

    def test_get_meta_refresh(self):
        r1 = HtmlResponse(
            "http://www.example.com",
            body=b"""
        <html>
        <head><title>Dummy</title><meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        <body>blahablsdfsal&amp;</body>
        </html>""",
        )
        r2 = HtmlResponse(
            "http://www.example.com",
            body=b"""
        <html>
        <head><title>Dummy</title><noScript>
        <meta http-equiv="refresh" content="5;url=http://example.org/newpage" /></head>
        </noSCRIPT>
        <body>blahablsdfsal&amp;</body>
        </html>""",
        )
        r3 = HtmlResponse(
            "http://www.example.com",
            body=b"""
    <noscript><meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage</noscript>
    <script type="text/javascript">
    if(!checkCookies()){
        document.write('<meta http-equiv="REFRESH" content="0;url=http://www.example.com/newpage">');
    }
    </script>
        """,
        )
        self.assertEqual(get_meta_refresh(r1), (5.0, "http://example.org/newpage"))
        self.assertEqual(get_meta_refresh(r2), (None, None))
        self.assertEqual(get_meta_refresh(r3), (None, None))

    def test_response_status_message(self):
        self.assertEqual(response_status_message(200), "200 OK")
        self.assertEqual(response_status_message(404), "404 Not Found")
        self.assertEqual(response_status_message(573), "573 Unknown Status")

    def test_inject_base_url(self):
        url = "http://www.example.com"

        def check_base_url(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace("file://", "")
            bbody = Path(path).read_bytes()
            self.assertEqual(bbody.count(b'<base href="' + to_bytes(url) + b'">'), 1)
            return True

        r1 = HtmlResponse(
            url,
            body=b"""
        <html>
            <head><title>Dummy</title></head>
            <body><p>Hello world.</p></body>
        </html>""",
        )
        r2 = HtmlResponse(
            url,
            body=b"""
        <html>
            <head id="foo"><title>Dummy</title></head>
            <body>Hello world.</body>
        </html>""",
        )
        r3 = HtmlResponse(
            url,
            body=b"""
        <html>
            <head><title>Dummy</title></head>
            <body>
                <header>Hello header</header>
                <p>Hello world.</p>
            </body>
        </html>""",
        )
        r4 = HtmlResponse(
            url,
            body=b"""
        <html>
            <!-- <head>Dummy comment</head> -->
            <head><title>Dummy</title></head>
            <body><p>Hello world.</p></body>
        </html>""",
        )
        r5 = HtmlResponse(
            url,
            body=b"""
        <html>
            <!--[if IE]>
            <head><title>IE head</title></head>
            <![endif]-->
            <!--[if !IE]>-->
            <head><title>Standard head</title></head>
            <!--<![endif]-->
            <body><p>Hello world.</p></body>
        </html>""",
        )

        assert open_in_browser(r1, _openfunc=check_base_url), "Inject base url"
        assert open_in_browser(
            r2, _openfunc=check_base_url
        ), "Inject base url with argumented head"
        assert open_in_browser(
            r3, _openfunc=check_base_url
        ), "Inject unique base url with misleading tag"
        assert open_in_browser(
            r4, _openfunc=check_base_url
        ), "Inject unique base url with misleading comment"
        assert open_in_browser(
            r5, _openfunc=check_base_url
        ), "Inject unique base url with conditional comment"
