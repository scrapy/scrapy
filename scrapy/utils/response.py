"""
This module provides some useful functions for working with
scrapy.http.Response objects
"""
import os
import re
import tempfile
import webbrowser
from io import StringIO
from mimetypes import MimeTypes
from pkgutil import get_data
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple, Type, Union
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

import scrapy
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


def _is_compressed_mime_type(mime_type):
    return mime_type in _ENCODING_MIME_TYPES


def _is_other_text_mime_type(mime_type):
    return (
        mime_type.startswith(b"text/")
        or mime_type == b"application/x-javascript"
        or is_javascript_mime_type(mime_type)
    )


def _get_encoding_or_mime_type_from_headers(
    headers: Headers,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    if b"Content-Encoding" in headers:
        encodings = [
            item.strip()
            for item in b",".join(headers.getlist(b"Content-Encoding")).split(b",")
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
    if b"Content-Disposition" in headers and headers[b"Content-Disposition"]:
        path = (
            headers[b"Content-Disposition"]
            .split(b";")[-1]
            .split(b"=")[-1]
            .strip(b"\"'")
            .decode()
        )
        encoding, mime_type = _get_encoding_or_mime_type_from_path(path)
        if encoding:
            return encoding, None
        return None, mime_type
    return None, None


def _get_mime_type_from_encoding(encoding):
    return _ENCODING_MIME_TYPE_MAP.get(encoding, None) or b"application/" + encoding


def _get_encoding_or_mime_type_from_path(path):
    mimetype, encoding = _MIME_TYPES.guess_type(path, strict=False)
    if encoding:
        return encoding.encode(), None
    if mimetype:
        return None, mimetype.encode()
    return None, None


def _get_response_class_from_mime_type(mime_type):
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
        _metaref_cache[response] = html.get_meta_refresh(
            text, response.url, response.encoding, ignore_tags=ignore_tags
        )
    return _metaref_cache[response]


def get_response_class(
    *,
    url: Optional[str] = None,
    body: Optional[bytes] = None,
    declared_mime_types: Optional[Sequence[bytes]] = None,
    http_headers: Optional[Headers] = None,
) -> Type[Response]:
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
    return _get_response_class_from_mime_type(mime_type)


def response_status_message(status: Union[bytes, float, int, str]) -> str:
    """Return status code plus status text descriptive message"""
    status_int = int(status)
    message = http.RESPONSES.get(status_int, "Unknown Status")
    return f"{status_int} {to_unicode(message)}"


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
