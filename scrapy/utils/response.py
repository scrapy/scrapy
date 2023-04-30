"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""
import os
import re
import tempfile
import webbrowser
from typing import Any, Callable, Iterable, Tuple, Union
from weakref import WeakKeyDictionary

from twisted.web import http
from w3lib import html

import scrapy
from scrapy.http.response import Response
from scrapy.utils.decorators import deprecated
from scrapy.utils.python import to_bytes, to_unicode

_baseurl_cache: "WeakKeyDictionary[Response, str]" = WeakKeyDictionary()


def get_base_url(response: "scrapy.http.response.text.TextResponse") -> str:
    """Return the base url of the given response, joined with the response url"""
    if response not in _baseurl_cache:
        text = response.text[0:4096]
        _baseurl_cache[response] = html.get_base_url(
            text, response.url, response.encoding
        )
    return _baseurl_cache[response]


_metaref_cache: "WeakKeyDictionary[Response, Union[Tuple[None, None], Tuple[float, str]]]" = (
    WeakKeyDictionary()
)


def get_meta_refresh(
    response: "scrapy.http.response.text.TextResponse",
    ignore_tags: Iterable[str] = ("script", "noscript"),
) -> Union[Tuple[None, None], Tuple[float, str]]:
    """Parse the http-equiv refresh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.text[0:4096]
        # a w3lib typing bug here, fixed in https://github.com/scrapy/w3lib/pull/211
        _metaref_cache[response] = html.get_meta_refresh(  # type: ignore[assignment]
            text, response.url, response.encoding, ignore_tags=ignore_tags
        )
    return _metaref_cache[response]


def response_status_message(status: Union[bytes, float, int, str]) -> str:
    """Return status code plus status text descriptive message"""
    status_int = int(status)
    message = http.RESPONSES.get(status_int, "Unknown Status")
    return f"{status_int} {to_unicode(message)}"


@deprecated
def response_httprepr(response: Response) -> bytes:
    """Return raw HTTP representation (as bytes) of the given response. This
    is provided only for reference, since it's not the exact stream of bytes
    that was received (that's not exposed by Twisted).
    """
    values = [
        b"HTTP/1.1 ",
        to_bytes(str(response.status)),
        b" ",
        to_bytes(http.RESPONSES.get(response.status, b"")),
        b"\r\n",
    ]
    if response.headers:
        values.extend([response.headers.to_string(), b"\r\n"])
    values.extend([b"\r\n", response.body])
    return b"".join(values)


def open_in_browser(
    response: Union[
        "scrapy.http.response.html.HtmlResponse",
        "scrapy.http.response.text.TextResponse",
    ],
    _openfunc: Callable[[str], Any] = webbrowser.open,
) -> Any:
    """Open the given response in a local web browser, populating the <base>
    tag for external links to work
    """
    from scrapy.http import HtmlResponse, TextResponse

    # XXX: this implementation is a bit dirty and could be improved
    body = response.body
    if isinstance(response, HtmlResponse):
        if b"<base" not in body:
            repl = rf'\1<base href="{response.url}">'
            body = re.sub(b"<!--.*?-->", b"", body, flags=re.DOTALL)
            body = re.sub(rb"(<head(?:>|\s.*?>))", to_bytes(repl), body)
        ext = ".html"
    elif isinstance(response, TextResponse):
        ext = ".txt"
    else:
        raise TypeError("Unsupported response type: " f"{response.__class__.__name__}")
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc(f"file://{fname}")
