from pathlib import Path
from time import process_time
from urllib.parse import urlparse

import pytest

from scrapy.http import HtmlResponse, Response, TextResponse
from scrapy.utils.python import to_bytes
from scrapy.utils.response import (
    _remove_html_comments,
    get_base_url,
    get_meta_refresh,
    open_in_browser,
    response_status_message,
)


class TestResponseUtils:
    dummy_response = TextResponse(url="http://example.org/", body=b"dummy_response")

    def test_open_in_browser(self):
        url = "http:///www.example.com/some/page.html"
        body = b"<html> <head> <title>test page</title> </head> <body>test body</body> </html>"

        def browser_open(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace("file://", "")
            bbody = Path(path).read_bytes()
            assert b'<base href="' + to_bytes(url) + b'">' in bbody
            return True

        response = HtmlResponse(url, body=body)
        assert open_in_browser(response, _openfunc=browser_open), "Browser not called"

        resp = Response(url, body=body)
        with pytest.raises(TypeError):
            open_in_browser(resp, debug=True)  # pylint: disable=unexpected-keyword-arg

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
        assert get_meta_refresh(r1) == (5.0, "http://example.org/newpage")
        assert get_meta_refresh(r2) == (None, None)
        assert get_meta_refresh(r3) == (None, None)

    def test_get_base_url(self):
        resp = HtmlResponse(
            "http://www.example.com",
            body=b"""
        <html>
        <head><base href="http://www.example.com/img/" target="_blank"></head>
        <body>blahablsdfsal&amp;</body>
        </html>""",
        )
        assert get_base_url(resp) == "http://www.example.com/img/"

        resp2 = HtmlResponse(
            "http://www.example.com",
            body=b"""
        <html><body>blahablsdfsal&amp;</body></html>""",
        )
        assert get_base_url(resp2) == "http://www.example.com"

    def test_response_status_message(self):
        assert response_status_message(200) == "200 OK"
        assert response_status_message(404) == "404 Not Found"
        assert response_status_message(573) == "573 Unknown Status"

    def test_inject_base_url(self):
        url = "http://www.example.com"

        def check_base_url(burl):
            path = urlparse(burl).path
            if not path or not Path(path).exists():
                path = burl.replace("file://", "")
            bbody = Path(path).read_bytes()
            assert bbody.count(b'<base href="' + to_bytes(url) + b'">') == 1
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
        assert open_in_browser(r2, _openfunc=check_base_url), (
            "Inject base url with argumented head"
        )
        assert open_in_browser(r3, _openfunc=check_base_url), (
            "Inject unique base url with misleading tag"
        )
        assert open_in_browser(r4, _openfunc=check_base_url), (
            "Inject unique base url with misleading comment"
        )
        assert open_in_browser(r5, _openfunc=check_base_url), (
            "Inject unique base url with conditional comment"
        )

    def test_open_in_browser_redos_comment(self):
        MAX_CPU_TIME = 0.02

        # Exploit input from
        # https://makenowjust-labs.github.io/recheck/playground/
        # for /<!--.*?-->/ (old pattern to remove comments).
        body = b"-><!--\x00" * 25_000 + b"->\n<!---->"

        response = HtmlResponse("https://example.com", body=body)

        start_time = process_time()

        open_in_browser(response, lambda url: True)

        end_time = process_time()
        assert end_time - start_time < MAX_CPU_TIME

    def test_open_in_browser_redos_head(self):
        MAX_CPU_TIME = 0.02

        # Exploit input from
        # https://makenowjust-labs.github.io/recheck/playground/
        # for /(<head(?:>|\s.*?>))/ (old pattern to find the head element).
        body = b"<head\t" * 8_000

        response = HtmlResponse("https://example.com", body=body)

        start_time = process_time()

        open_in_browser(response, lambda url: True)

        end_time = process_time()
        assert end_time - start_time < MAX_CPU_TIME


@pytest.mark.parametrize(
    ("input_body", "output_body"),
    [
        (
            b"a<!--",
            b"a",
        ),
        (
            b"a<!---->b",
            b"ab",
        ),
        (
            b"a<!--b-->c",
            b"ac",
        ),
        (
            b"a<!--b-->c<!--",
            b"ac",
        ),
        (
            b"a<!--b-->c<!--d",
            b"ac",
        ),
        (
            b"a<!--b-->c<!---->d",
            b"acd",
        ),
        (
            b"a<!--b--><!--c-->d",
            b"ad",
        ),
    ],
)
def test_remove_html_comments(input_body, output_body):
    assert _remove_html_comments(input_body) == output_body, (
        f"{_remove_html_comments(input_body)=} == {output_body=}"
    )
