"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""

from __future__ import annotations

import os
import re
import tempfile
import webbrowser
from io import StringIO
from mimetypes import MimeTypes
from pkgutil import get_data
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from warnings import warn
from weakref import WeakKeyDictionary

from twisted.web import http
from w3lib import html
from xtractmime import RESOURCE_HEADER_BUFFER_LENGTH as BODY_LIMIT
from xtractmime import extract_mime
from xtractmime.mimegroups import (
    is_html_mime_type,
    is_javascript_mime_type,
    is_json_mime_type,
    is_xml_mime_type,
)

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import (
    Headers,
    HtmlResponse,
    JsonResponse,
    Response,
    TextResponse,
    XmlResponse,
)
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

_ENCODING_MIME_TYPE_MAP = {
    b"br": b"application/brotli",
    b"compress": b"application/x-compress",
    b"deflate": b"application/zip",
    b"gzip": b"application/gzip",
    b"zstd": b"application/zstd",
}
_ENCODING_MIME_TYPES = {*_ENCODING_MIME_TYPE_MAP.values()}
_MIME_TYPES = MimeTypes()
_mime_overrides = get_data("scrapy", "mime.types") or b""
_MIME_TYPES.readfp(StringIO(_mime_overrides.decode()))

_metaref_cache: WeakKeyDictionary[Response, tuple[None, None] | tuple[float, str]] = (
    WeakKeyDictionary()
)


def _is_compressed_mime_type(mime_type: bytes) -> bool:
    return mime_type in _ENCODING_MIME_TYPES


def _is_other_text_mime_type(mime_type: bytes) -> bool:
    return (
        mime_type.startswith(b"text/")
        or mime_type == b"application/x-javascript"
        or is_javascript_mime_type(mime_type)
    )


def _get_encoding_or_mime_type_from_headers(
    headers: Headers,
) -> tuple[bytes | None, bytes | None]:
    if b"Content-Encoding" in headers:
        encodings = [
            item.strip()
            for item in b",".join(headers.getlist(b"Content-Encoding")).split(b",")
            if item.strip().lower() != b"identity"
        ]
        if encodings:
            return encodings[-1], None
    if (
        b"Content-Type" in headers
        and headers[b"Content-Type"]
        and headers[b"Content-Type"].split(b";")[0].strip().lower()
        not in (
            b"",
            b"unknown/unknown",
            b"application/unknown",
            b"*/*",
        )
    ):
        return None, headers[b"Content-Type"]
    content_disposition = headers.get(b"Content-Disposition")
    if content_disposition:
        path = (
            content_disposition.split(b";")[-1].split(b"=")[-1].strip(b"\"'").decode()
        )
        encoding, mime_type = _get_encoding_or_mime_type_from_path(path)
        if encoding:
            return encoding, None
        return None, mime_type
    return None, None


def _get_mime_type_from_encoding(encoding: bytes) -> bytes:
    return _ENCODING_MIME_TYPE_MAP.get(encoding) or b"application/" + encoding


def _get_encoding_or_mime_type_from_path(
    path: str,
) -> tuple[bytes | None, bytes | None]:
    mimetype, encoding = _MIME_TYPES.guess_type(path, strict=False)
    if encoding:
        return encoding.encode(), None
    if mimetype:
        return None, mimetype.encode()
    return None, None


def _get_response_class_from_mime_type(mime_type: bytes | None) -> type[Response]:
    if not mime_type:
        return Response
    if is_html_mime_type(mime_type):
        return HtmlResponse
    if is_xml_mime_type(mime_type):
        return XmlResponse
    if is_json_mime_type(mime_type) or (
        mime_type
        in (
            b"application/x-json",
            b"application/json-amazonui-streaming",
        )
    ):
        return JsonResponse
    if _is_other_text_mime_type(mime_type):
        return TextResponse
    return Response


def get_base_url(response: TextResponse) -> str:
    """Return the base url of the given response, joined with the response url"""
    warn(
        (
            "scrapy.utils.response.get_base_url is deprecated, use "
            "scrapy.http.TextResponse.base_url instead."
        ),
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return response.base_url


def get_meta_refresh(
    response: TextResponse,
    ignore_tags: Iterable[str] = ("script", "noscript"),
) -> tuple[None, None] | tuple[float, str]:
    """Parse the http-equiv refresh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.text[0:4096]
        _metaref_cache[response] = html.get_meta_refresh(
            text, response.base_url, response.encoding, ignore_tags=ignore_tags
        )
    return _metaref_cache[response]


def get_response_class(
    *,
    url: str | None = None,
    body: bytes | None = None,
    declared_mime_types: Sequence[bytes] | None = None,
    http_headers: Headers | None = None,
) -> type[Response]:
    """Guess the most appropriate Response class based on the given
    arguments."""
    mime_type = next(iter(declared_mime_types or []), None)
    encoding = None  # as in compression (e.g. gzip), not charset
    if http_headers:
        encoding, header_mime_type = _get_encoding_or_mime_type_from_headers(
            http_headers
        )
        if encoding is None and mime_type is None:
            mime_type = header_mime_type
    if url is not None:
        url_parts = urlparse(url)
        http_origin = url_parts.scheme in ("http", "https")
        if not http_origin and not encoding:
            encoding, path_mime_type = _get_encoding_or_mime_type_from_path(
                url_parts.path
            )
            if encoding is None and mime_type is None:
                mime_type = path_mime_type
    else:
        http_origin = True
    body = (body or b"")[:BODY_LIMIT]
    if encoding:
        content_types = (_get_mime_type_from_encoding(encoding),)
    elif mime_type:
        content_types = (mime_type,)
    else:
        content_types = None
    mime_type = extract_mime(
        body,
        content_types=content_types,
        http_origin=http_origin,
    )
    cls = _get_response_class_from_mime_type(mime_type)
    if cls is not Response or not content_types or encoding or not http_origin:
        return cls
    # In scenarios where there was a declared Content-Type, no
    # Content-Encoding, HTTP/HTTPS was used, and xtractmime determined the
    # output to be binary, repeat MIME extraction ignoring the declared
    # Content-Type, so that the body is taken into account.
    mime_type = extract_mime(
        body,
        http_origin=http_origin,
    )
    return _get_response_class_from_mime_type(mime_type)


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
    # XXX: this implementation is a bit dirty and could be improved
    body = response.body
    if isinstance(response, HtmlResponse):
        if b"<base" not in _remove_html_comments(body):
            repl = rf'\g<0><base href="{response.url}">'
            body = re.sub(rb"<head(?:[^<>]*?>)", to_bytes(repl), body, count=1)
        ext = ".html"
    elif isinstance(response, TextResponse):
        ext = ".txt"
    else:
        raise TypeError(f"Unsupported response type: {response.__class__.__name__}")
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc(f"file://{fname}")
