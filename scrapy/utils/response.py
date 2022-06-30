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
from typing import (
    Any,
    Callable,
    Iterable,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)
from urllib.parse import urlparse
from warnings import warn
from weakref import WeakKeyDictionary

from twisted.web import http
from w3lib import html
from xtractmime import (
    RESOURCE_HEADER_BUFFER_LENGTH as BODY_LIMIT,
    extract_mime,
    is_binary_data,
)
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
    Response,
    TextResponse,
    XmlResponse,
)
from scrapy.utils.decorators import deprecated
from scrapy.utils.python import to_bytes, to_unicode


_baseurl_cache: "WeakKeyDictionary[Response, str]" = WeakKeyDictionary()
_CONTENT_ENCODING_MIME_TYPES = {
    'br': b'application/brotli',
    'deflate': b'application/zip',
    'gzip': b'application/gzip',
}
_MIME_TYPES = MimeTypes()
_mime_overrides = get_data('scrapy', 'mime.types') or b''
_MIME_TYPES.readfp(StringIO(_mime_overrides.decode()))



def _is_html_mime_type(mime_type):
    if mime_type in {
        b'application/xhtml+xml',
        b'application/vnd.wap.xhtml+xml',
    }:
        return True
    return is_html_mime_type(mime_type)


def _is_other_text_mime_type(mime_type):
    return (
        mime_type.startswith(b'text/')
        or is_json_mime_type(mime_type)
        or is_javascript_mime_type(mime_type)
        or mime_type in (
            b'application/x-json',
            b'application/json-amazonui-streaming',
            b'application/x-javascript',
        )
    )


_PRIORITIZED_MIME_TYPE_CHECKERS = (
    _is_html_mime_type,
    is_xml_mime_type,
    _is_other_text_mime_type,
)


def _get_best_mime_type(mime_types):
    candidate_mime_types = tuple(
        mime_type
        for mime_type in mime_types
        if mime_type is not None
    )
    for mime_type_checker in _PRIORITIZED_MIME_TYPE_CHECKERS:
        for candidate_mime_type in candidate_mime_types:
            if mime_type_checker(candidate_mime_type):
                return candidate_mime_type
    return mime_types[0]


def _get_http_header_mime_types(headers: Headers) -> Sequence[bytes]:
    mime_types = []
    if b'Content-Type' in headers:
        mime_types.append(headers[b'Content-Type'].split(b';')[0])
    if b'Content-Disposition' in headers:
        path = (
            headers.get(b"Content-Disposition")
            .split(b";")[-1]
            .split(b"=")[-1]
            .strip(b"\"'")
            .decode()
        )
        mime_types.append(_get_mime_type_from_path(path))
    return mime_types


def _get_mime_type_from_path(path):
    mimetype, encoding = _MIME_TYPES.guess_type(path, strict=False)
    encoding_mime_type = _CONTENT_ENCODING_MIME_TYPES.get(encoding, None)
    if encoding_mime_type:
        return encoding_mime_type
    if mimetype:
        return mimetype.encode()
    return None


def _get_response_class_from_mime_type(mime_type):
    if not mime_type:
        return Response
    if _is_html_mime_type(mime_type):
        return HtmlResponse
    if is_xml_mime_type(mime_type):
        return XmlResponse
    if _is_other_text_mime_type(mime_type):
        return TextResponse
    return Response


def _remove_nul_byte_from_text(text):
    """Return the text with removed null byte (b'\x00') if there are no other
    binary bytes in the text, otherwise return the text as-is.

    Based on https://github.com/scrapy/scrapy/issues/2481
    """
    for index in range(len(text)):
        if (
            text[index:index + 1] != b'\x00'
            and is_binary_data(text[index:index + 1])
        ):
            return text

    return text.replace(b'\x00', b'')


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


_metaref_cache: "WeakKeyDictionary[Response, Union[Tuple[None, None], Tuple[float, str]]]" = WeakKeyDictionary()


def get_meta_refresh(
    response: "scrapy.http.response.text.TextResponse",
    ignore_tags: Optional[Iterable[str]] = ('script', 'noscript'),
) -> Union[Tuple[None, None], Tuple[float, str]]:
    """Parse the http-equiv refrsh parameter from the given response"""
    if response not in _metaref_cache:
        text = response.text[0:4096]
        _metaref_cache[response] = html.get_meta_refresh(
            text, response.url, response.encoding, ignore_tags=ignore_tags)
    return _metaref_cache[response]


def get_response_class(
    *,
    url: str = None,
    body: bytes = None,
    declared_mime_types: Sequence[bytes] = None,
    http_headers: Headers = None,
) -> Type[Response]:
    """Guess the most appropriate Response class based on the given
    arguments."""
    mime_types = list(declared_mime_types or [])
    if http_headers:
        mime_types.extend(_get_http_header_mime_types(http_headers))
    if url is not None:
        url_parts = urlparse(url)
        http_origin = url_parts.scheme in ("http", "https")
        mime_types.append(_get_mime_type_from_path(url_parts.path))
    else:
        http_origin = True
    body = _remove_nul_byte_from_text((body or b'')[:BODY_LIMIT])
    if mime_types:
        best_mime_type = _get_best_mime_type(mime_types)
        content_types = (best_mime_type,) if best_mime_type else best_mime_type
    else:
        content_types = None
    mime_type = extract_mime(
        body,
        content_types=content_types,
        http_origin=http_origin,
    )
    return _get_response_class_from_mime_type(mime_type)


def response_status_message(status: Union[bytes, float, int, str]) -> str:
    """Return status code plus status text descriptive message
    """
    status_int = int(status)
    message = http.RESPONSES.get(status_int, "Unknown Status")
    return f'{status_int} {to_unicode(message)}'


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
        to_bytes(http.RESPONSES.get(response.status, b'')),
        b"\r\n",
    ]
    if response.headers:
        values.extend([response.headers.to_string(), b"\r\n"])
    values.extend([b"\r\n", response.body])
    return b"".join(values)


def open_in_browser(
    response: Union["scrapy.http.response.html.HtmlResponse", "scrapy.http.response.text.TextResponse"],
    _openfunc: Callable[[str], Any] = webbrowser.open,
) -> Any:
    """Open the given response in a local web browser, populating the <base>
    tag for external links to work
    """
    from scrapy.http import HtmlResponse, TextResponse
    # XXX: this implementation is a bit dirty and could be improved
    body = response.body
    if isinstance(response, HtmlResponse):
        if b'<base' not in body:
            repl = fr'\1<base href="{response.url}">'
            body = re.sub(b"<!--.*?-->", b"", body, flags=re.DOTALL)
            body = re.sub(rb"(<head(?:>|\s.*?>))", to_bytes(repl), body)
        ext = '.html'
    elif isinstance(response, TextResponse):
        ext = '.txt'
    else:
        raise TypeError("Unsupported response type: "
                        f"{response.__class__.__name__}")
    fd, fname = tempfile.mkstemp(ext)
    os.write(fd, body)
    os.close(fd)
    return _openfunc(f"file://{fname}")
