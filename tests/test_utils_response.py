from __future__ import annotations

from pathlib import Path
from time import process_time
from urllib.parse import urlparse

import pytest

from scrapy.http import HtmlResponse, Response, TextResponse
from scrapy.utils.python import to_bytes
from scrapy.utils.response import (
    get_base_url,
    get_meta_refresh,
    open_in_browser,
    response_status_message,
)


def _read_browser_output(burl: str) -> bytes:
    path = urlparse(burl).path
    if not path or not Path(path).exists():
        path = burl.replace("file://", "")
    return Path(path).read_bytes()


def test_open_in_browser():
    url = "http://www.example.com/some/page.html"
    body = (
        b"<html> <head> <title>test page</title> </head> <body>test body</body> </html>"
    )

    def browser_open(burl: str) -> bool:
        bbody = _read_browser_output(burl)
        assert b'<base href="' + to_bytes(url) + b'">' in bbody
        return True

    response = HtmlResponse(url, body=body)
    assert open_in_browser(response, _openfunc=browser_open), "Browser not called"

    resp = Response(url, body=body)
    with pytest.raises(TypeError):
        open_in_browser(resp, _openfunc=browser_open)  # type: ignore[arg-type]


def test_get_meta_refresh():
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
    r4 = HtmlResponse(
        "http://www.example.com",
        body=b"""
    <html>
    <head><title>Dummy</title>
    <base href="http://www.another-domain.com/base/path/">
    <meta http-equiv="refresh" content="5;url=target.html"</head>
    <body>blahablsdfsal&amp;</body>
    </html>""",
    )
    assert get_meta_refresh(r1) == (5.0, "http://example.org/newpage")
    assert get_meta_refresh(r2) == (None, None)
    assert get_meta_refresh(r3) == (None, None)
    assert get_meta_refresh(r4) == (
        5.0,
        "http://www.another-domain.com/base/path/target.html",
    )


def test_get_base_url():
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


def test_response_status_message():
    assert response_status_message(200) == "200 OK"
    assert response_status_message(404) == "404 Not Found"
    assert response_status_message(573) == "573 Unknown Status"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            b"""
    <html>
        <head><title>Dummy</title></head>
        <body><p>Hello world.</p></body>
    </html>""",
            id="Simple",
        ),
        pytest.param(
            b"""
    <html>
        <head id="foo"><title>Dummy</title></head>
        <body>Hello world.</body>
    </html>""",
            id="<head> with attrs",
        ),
        pytest.param(
            b"""
    <html>
        <head><title>Dummy</title></head>
        <body>
            <header>Hello header</header>
            <p>Hello world.</p>
        </body>
    </html>""",
            id="Misleading tag",
        ),
        pytest.param(
            b"""
    <html>
        <!-- <head>Dummy comment</head> -->
        <head><title>Dummy</title></head>
        <body><p>Hello world.</p></body>
    </html>""",
            id="Misleading comment",
        ),
        pytest.param(
            b"""
    <html>
        <!--[if IE]>
        <head><title>IE head</title></head>
        <![endif]-->
        <!--[if !IE]>-->
        <head><title>Standard head</title></head>
        <!--<![endif]-->
        <body><p>Hello world.</p></body>
    </html>""",
            id="Conditional comment",
        ),
        pytest.param(
            b"""
    <html>
        <body><p>Hello world.</p></body>
    </html>""",
            id="No <head>",
        ),
        pytest.param(
            b"<p>Hello world.</p>",
            id="No <html>",
        ),
        pytest.param(
            b"""<!DOCTYPE html>
    <html>
        <head><title>Dummy</title></head>
        <body><p>Hello world.</p></body>
    </html>""",
            id="Doctype",
        ),
        pytest.param(
            b"""
    <!-- <head><base href="http://example.org"></head> -->
    <p>Hello world.</p>""",
            id="Only commented-out <head> and <base>",
        ),
    ],
)
def test_inject_base_url(body: bytes) -> None:
    url = "http://www.example.com"

    def check_base_url(burl):
        bbody = _read_browser_output(burl)
        base_tag = b'<base href="' + to_bytes(url) + b'">'
        assert bbody.count(base_tag) == 1
        index = bbody.index(base_tag)
        # The base tag is not commented out.
        assert bbody.rfind(b"<!--", 0, index) <= bbody.rfind(b"-->", 0, index)
        # The base tag comes after the doctype declaration, if any.
        assert b"<!DOCTYPE" not in bbody[index:]
        return True

    resp = HtmlResponse(url, body=body)
    assert open_in_browser(resp, _openfunc=check_base_url)


def _assert_open_in_browser_is_fast(body: bytes) -> None:
    # The exploit inputs are large enough that a vulnerable implementation
    # needs seconds to go through them, while a safe one stays in the low
    # milliseconds even on a slow interpreter.
    max_cpu_time = 0.2

    response = HtmlResponse("https://example.com", body=body)
    start_time = process_time()
    open_in_browser(response, lambda url: True)
    end_time = process_time()
    assert end_time - start_time < max_cpu_time


def test_open_in_browser_redos_comment():
    # Exploit input from
    # https://makenowjust-labs.github.io/recheck/playground/
    # for /<!--.*?-->/ (old pattern to remove comments).
    _assert_open_in_browser_is_fast(b"-><!--\x00" * 250_000 + b"->\n<!---->")


def test_open_in_browser_redos_head():
    # Exploit input from
    # https://makenowjust-labs.github.io/recheck/playground/
    # for /(<head(?:>|\s.*?>))/ (old pattern to find the head element).
    _assert_open_in_browser_is_fast(b"<head\t" * 80_000)


def test_open_in_browser_preserves_html_comments():
    url = "http://www.example.com"
    body = (
        b"<html>"
        b"<!-- preserved comment -->"
        b"<head><title>Real</title></head>"
        b"<body>content</body>"
        b"</html>"
    )

    def check(burl):
        bbody = _read_browser_output(burl)
        assert b"<!-- preserved comment -->" in bbody
        return True

    response = HtmlResponse(url, body=body)
    assert open_in_browser(response, _openfunc=check)


@pytest.mark.parametrize(
    ("base_tag", "expected_base_url"),
    [
        (b'<base href="http://real.com/">', b"http://real.com/"),
        (b'<BASE HREF="http://real.com/">', b"http://real.com/"),
        (b'<base href="/img/">', b"http://www.example.com/img/"),
        (b'<base target="_blank">', b"http://www.example.com/page.html"),
    ],
)
def test_open_in_browser_keeps_base_url_of_response(
    base_tag: bytes, expected_base_url: bytes
):
    url = "http://www.example.com/page.html"
    body = b"<html><head>" + base_tag + b"<title>T</title></head><body>hi</body></html>"

    def check(burl):
        bbody = _read_browser_output(burl)
        assert bbody.startswith(b'<base href="' + expected_base_url + b'">')
        return True

    response = HtmlResponse(url, body=body)
    assert open_in_browser(response, _openfunc=check)


def test_open_in_browser_injects_base_when_only_in_comment():
    url = "http://www.example.com"
    body = (
        b"<html>"
        b"<!-- <base href='http://other.com'> -->"
        b"<head><title>Real</title></head>"
        b"<body>content</body>"
        b"</html>"
    )

    def check(burl):
        bbody = _read_browser_output(burl)
        assert b'<base href="' + to_bytes(url) + b'">' in bbody
        return True

    response = HtmlResponse(url, body=body)
    assert open_in_browser(response, _openfunc=check)


def test_open_in_browser_injects_base_before_head_contents():
    url = "http://www.example.com"
    body = (
        b"<html>"
        b"<!--<head>comment head</head>-->"
        b"<head><title>Actual</title></head>"
        b"<body>hello</body>"
        b"</html>"
    )

    def check(burl):
        bbody = _read_browser_output(burl)
        assert bbody.count(b'<base href="' + to_bytes(url) + b'">') == 1
        base_pos = bbody.find(b'<base href="' + to_bytes(url) + b'">')
        title_pos = bbody.find(b"<title>Actual</title>")
        assert base_pos < title_pos
        return True

    response = HtmlResponse(url, body=body)
    assert open_in_browser(response, _openfunc=check)


def test_open_in_browser_text_response_uses_txt_extension():
    response = TextResponse("http://www.example.com", body=b"plain text content")

    def check(burl):
        assert burl.endswith(".txt")
        return True

    assert open_in_browser(response, _openfunc=check)


def test_open_in_browser_raises_for_unsupported_response_type():
    response = Response("http://www.example.com", body=b"binary")
    with pytest.raises(TypeError):
        open_in_browser(response, _openfunc=lambda _: True)  # type: ignore[arg-type]
