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
            text, get_base_url(response), response.encoding, ignore_tags=ignore_tags
        )
    return _metaref_cache[response]


def response_status_message(status: bytes | float | str) -> str:
    """Return status code plus status text descriptive message"""
    status_int = int(status)
    message = http.RESPONSES.get(status_int, "Unknown Status")
    return f"{status_int} {to_unicode(message)}"


_DOCTYPE_RE = re.compile(rb"\s*<!doctype[^<>]*>", re.IGNORECASE)


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
            if "item name" not in response.text:
                open_in_browser(response)

    On the Windows Subsystem for Linux, set the ``BROWSER`` environment
    variable to `wslview <https://github.com/wslutilities/wslu>`_ to open the
    response in a Windows browser, which cannot read Linux paths otherwise.
    """
    # circular imports
    from scrapy.http import HtmlResponse, TextResponse  # noqa: PLC0415

    body = response.body
    if isinstance(response, HtmlResponse):
        # Web browsers move a base tag that precedes the head element into it,
        # so the head element does not need to be found, which is not always
        # possible. The base tag must come after the doctype declaration, if
        # any, to keep the browser out of quirks mode. It takes precedence over
        # any base tag of the response, and matches it when there is one.
        doctype = _DOCTYPE_RE.match(body)
        index = doctype.end() if doctype else 0
        base_tag = to_bytes(f'<base href="{get_base_url(response)}">')
        body = body[:index] + base_tag + body[index:]
        ext = ".html"
    elif isinstance(response, TextResponse):
        ext = ".txt"
    else:
        raise TypeError(f"Unsupported response type: {response.__class__.__name__}")
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc(f"file://{fname}")
