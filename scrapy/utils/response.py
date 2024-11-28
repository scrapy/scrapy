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

# Needed for open_in_browser
from bs4 import BeautifulSoup

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


def response_status_message(status: bytes | float | int | str) -> str:
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


def open_in_browser(html_content, base_url):
    """
    Opens HTML content in default web browser, ensures proper handling of relative
    URLs by injecting <base> tag with given base_url.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # If <head> does not exist, create tag
    head_tag = soup.head
    if head_tag is None:
        head_tag = soup.new_tag('head')
        # Place new <head> tag before <body> tag, or place at start if <body> is not there
        if soup.body:
            soup.body.insert_before(head_tag)
        else:
            soup.insert(0, head_tag)

    # Place <base> tag into <head> section
    base_tag = soup.new_tag('base', href=base_url)
    head_tag.insert(0, base_tag)

    # Save this HTML to temporary file and then open it in the browser
    with open("temp.html", "w", encoding="utf-8") as temp_file:
        temp_file.write(str(soup))
    
    import webbrowser
    webbrowser.open("temp.html")
