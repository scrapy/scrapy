"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

from __future__ import annotations

import os
import re
import tempfile
import webbrowser
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from twisted.web import http
from w3lib import html

from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from scrapy.http import Response, TextResponse

_baseurl_cache: WeakKeyDictionary[Response, str] = WeakKeyDictionary()


def get_base_url(response: TextResponse) -> str:
    """Return the base url of the given response, joined with the response url"""
    if response not in _baseurl_cache:
        text = response.text[0:4096]
        _baseurl_cache[response] = html.get_base_url(
            text, response.url, response.encoding
        )
    return _baseurl_cache[response]


_metaref_cache: WeakKeyDictionary[Response, tuple[None, None] | tuple[float, str]] = (
    WeakKeyDictionary()
)


def get_meta_refresh(
    response: TextResponse,
    ignore_tags: Iterable[str] = ("script", "noscript"),
) -> tuple[None, None] | tuple[float, str]:
    """Parse the http-equiv refresh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.text[0:4096]
        _metaref_cache[response] = html.get_meta_refresh(
            text, response.url, response.encoding, ignore_tags=ignore_tags
        )
    return _metaref_cache[response]


def response_status_message(status: bytes | float | str) -> str:
    """Return status code plus status text descriptive message"""
    status_int = int(status)
    message = http.RESPONSES.get(status_int, "Unknown Status")
    return f"{status_int} {to_unicode(message)}"


def _remove_html_comments(body: bytes) -> bytes:
    start = body.find(b"<!--")
    while start != -1:
        end = body.find(b"-->", start + 1)
        if end == -1:
            return body[:start]
        body = body[:start] + body[end + 3 :]
        start = body.find(b"<!--")
    return body


def open_in_browser(
    response: TextResponse,
    _openfunc: Callable[[str], Any] = webbrowser.open,
) -> Any:
    """Open *response* in a local web browser, adjusting the `base tag`_ for
    external links to work, e.g. so that images and styles are displayed.

    .. _base tag: https://www.w3schools.com/tags/tag_base.asp

    For example:

    .. code-block:: python

        from scrapy.utils.response import open_in_browser


        def parse_details(self, response):
            if "item name" not in response.body:
                open_in_browser(response)
    """
    from scrapy.http import HtmlResponse, TextResponse

    body = response.body
    if isinstance(response, HtmlResponse):
        ext = ".html"
        if b"<base" not in body:
            _remove_html_comments(body)
            base_tag = f'<base href="{response.url}">'

            # Try to insert after <head> tag first (existing behavior)
            head_match = re.search(rb"<head(?:[^<>]*?>)", body)
            if head_match:
                repl = rf"\0{base_tag}"
                body = re.sub(rb"<head(?:[^<>]*?>)", to_bytes(repl), body, count=1)
            else:
                # No head tag found, try to insert at beginning of body
                body_match = re.search(rb"<body(?:[^<>]*?>)", body)
                if body_match:
                    repl = rf"\0<head>{base_tag}</head>"
                    body = re.sub(rb"<body(?:[^<>]*?>)", to_bytes(repl), body, count=1)
                else:
                    # If no body tag, try finding html tag
                    html_match = re.search(rb"<html(?:[^<>]*?>)", body)
                    if html_match:
                        repl = rf"\0<head>{base_tag}</head>"
                        body = re.sub(
                            rb"<html(?:[^<>]*?>)", to_bytes(repl), body, count=1
                        )
                    else:
                        # As a last resort, prepend to document
                        body = to_bytes(f"<head>{base_tag}</head>") + body
            ext = ".html"
    elif isinstance(response, TextResponse):
        ext = ".txt"
    else:
        raise TypeError(f"Unsupported response type: {response.__class__.__name__}")
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc(f"file://{fname}")
