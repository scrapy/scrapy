"""
This module implements a class which returns the appropriate Response class
based on different criteria.
"""
from mimetypes import MimeTypes
from pkgutil import get_data
from io import StringIO
from urllib.parse import urlparse
from warnings import warn

from xtractmime import (
    RESOURCE_HEADER_BUFFER_LENGTH,
    extract_mime,
    is_binary_data,
)
from xtractmime.mimegroups import (
    is_html_mime_type,
    is_javascript_mime_type,
    is_json_mime_type,
    is_xml_mime_type,
)

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import HtmlResponse, Response, TextResponse, XmlResponse
from scrapy.utils.misc import load_object
from scrapy.utils.python import binary_is_text, to_bytes, to_unicode


_CONTENT_ENCODING_MIME_TYPES = {
    'br': b'application/brotli',
    'deflate': b'application/zip',
    'gzip': b'application/gzip',
}
_MIME_TYPES = MimeTypes()
_MIME_TYPES.readfp(StringIO(get_data('scrapy', 'mime.types').decode()))


def _is_other_text_mime_type(mime_type):
    value = (
        mime_type.startswith(b'text/')
        or is_json_mime_type(mime_type)
        or is_javascript_mime_type(mime_type)
        or mime_type in (
            b'application/x-json',
            b'application/json-amazonui-streaming',
            b'application/x-javascript',
        )
    )
    return value


_PRIORITIZED_MIME_TYPE_CHECKERS = (
    is_html_mime_type,
    is_xml_mime_type,
    _is_other_text_mime_type,
)


def _content_type_from_metadata(*, headers=None, url_path=None, filename=None):
    if headers and b'Content-Type' in headers:
        content_type_mime_type = headers.getlist(b'Content-Type')[-1]
    else:
        content_type_mime_type = None

    if headers and b'Content-Disposition' in headers:
        _filename = (
            headers.get(b"Content-Disposition")
            .split(b";")[-1]
            .split(b"=")[-1]
            .strip(b"\"'")
            .decode()
        )
        content_disposition_mime_type = _mime_type_from_path(_filename)
    else:
        content_disposition_mime_type = None

    filename_mime_type = _mime_type_from_path(filename) if filename else None
    url_mime_type = _mime_type_from_path(url_path) if url_path else None

    candidate_mime_types = tuple(
        mime_type
        for mime_type in (
            content_type_mime_type,
            content_disposition_mime_type,
            filename_mime_type,
            url_mime_type,
        )
        if mime_type is not None
    )
    for mime_type_checker in _PRIORITIZED_MIME_TYPE_CHECKERS:
        for candidate_mime_type in candidate_mime_types:
            if mime_type_checker(candidate_mime_type):
                return candidate_mime_type
    return (
        content_type_mime_type
        or content_disposition_mime_type
        or filename_mime_type
        or url_mime_type
    )


def _mime_type_from_path(path):
    mimetype, encoding = _MIME_TYPES.guess_type(path, strict=False)
    encoding_mime_type = _CONTENT_ENCODING_MIME_TYPES.get(encoding, None)
    if encoding_mime_type:
        return encoding_mime_type
    if mimetype:
        return mimetype.encode()
    return None


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


def _response_type_from_mime_type(mime_type):
    if not mime_type:
        return Response
    if is_html_mime_type(mime_type):
        return HtmlResponse
    if is_xml_mime_type(mime_type):
        return XmlResponse
    if _is_other_text_mime_type(mime_type):
        return TextResponse
    return Response


class ResponseTypes:

    CLASSES = {
        'text/html': 'scrapy.http.HtmlResponse',
        'application/atom+xml': 'scrapy.http.XmlResponse',
        'application/rdf+xml': 'scrapy.http.XmlResponse',
        'application/rss+xml': 'scrapy.http.XmlResponse',
        'application/xhtml+xml': 'scrapy.http.HtmlResponse',
        'application/vnd.wap.xhtml+xml': 'scrapy.http.HtmlResponse',
        'application/xml': 'scrapy.http.XmlResponse',
        'application/json': 'scrapy.http.TextResponse',
        'application/x-json': 'scrapy.http.TextResponse',
        'application/json-amazonui-streaming': 'scrapy.http.TextResponse',
        'application/javascript': 'scrapy.http.TextResponse',
        'application/x-javascript': 'scrapy.http.TextResponse',
        'text/xml': 'scrapy.http.XmlResponse',
        'text/*': 'scrapy.http.TextResponse',
    }

    def __init__(self):
        self.classes = {}
        for mimetype, cls in self.CLASSES.items():
            self.classes[mimetype] = load_object(cls)

    def from_mimetype(self, mimetype):
        """Return the most appropriate Response class for the given mimetype"""
        if mimetype is None:
            return Response
        elif mimetype in self.classes:
            return self.classes[mimetype]
        else:
            basetype = f"{mimetype.split('/')[0]}/*"
            return self.classes.get(basetype, Response)

    def from_content_type(self, content_type, content_encoding=None):
        """Return the most appropriate Response class from an HTTP Content-Type
        header """
        warn('ResponseTypes.from_content_type is deprecated, '
             'please use ResponseTypes.from_args instead', ScrapyDeprecationWarning)
        if content_encoding:
            return Response
        mimetype = to_unicode(content_type).split(';')[0].strip().lower()
        return self.from_mimetype(mimetype)

    def from_content_disposition(self, content_disposition):
        warn('ResponseTypes.from_content_disposition is deprecated, '
             'please use ResponseTypes.from_args instead', ScrapyDeprecationWarning)
        try:
            filename = to_unicode(
                content_disposition, encoding='latin-1', errors='replace'
            ).split(';')[1].split('=')[1].strip('"\'')
            return self.from_filename(filename)
        except IndexError:
            return Response

    def from_headers(self, headers):
        """Return the most appropriate Response class by looking at the HTTP
        headers"""
        warn('ResponseTypes.from_headers is deprecated, '
             'please use ResponseTypes.from_args instead', ScrapyDeprecationWarning)
        cls = Response
        if b'Content-Type' in headers:
            cls = self.from_content_type(
                content_type=headers[b'Content-Type'],
                content_encoding=headers.get(b'Content-Encoding')
            )
        if cls is Response and b'Content-Disposition' in headers:
            cls = self.from_content_disposition(headers[b'Content-Disposition'])
        return cls

    def from_filename(self, filename):
        """Return the most appropriate Response class from a file name"""
        warn('ResponseTypes.from_filename is deprecated, '
             'please use ResponseTypes.from_args instead', ScrapyDeprecationWarning)
        mimetype, encoding = _MIME_TYPES.guess_type(filename)
        if mimetype and not encoding:
            return self.from_mimetype(mimetype)
        else:
            return Response

    def from_body(self, body):
        """Try to guess the appropriate response based on the body content.
        This method is a bit magic and could be improved in the future, but
        it's not meant to be used except for special cases where response types
        cannot be guess using more straightforward methods."""
        warn('ResponseTypes.from_body is deprecated, '
             'please use ResponseTypes.from_args instead', ScrapyDeprecationWarning)
        chunk = body[:5000]
        chunk = to_bytes(chunk)
        if not binary_is_text(chunk):
            return self.from_mimetype('application/octet-stream')
        lowercase_chunk = chunk.lower()
        if b"<html>" in lowercase_chunk:
            return self.from_mimetype('text/html')
        if b"<?xml" in lowercase_chunk:
            return self.from_mimetype('text/xml')
        if b'<!doctype html>' in lowercase_chunk:
            return self.from_mimetype('text/html')
        return self.from_mimetype('text')

    def from_args(self, headers=None, url=None, filename=None, body=None):
        """Guess the most appropriate Response class based on
        the given arguments."""
        body = body or b''
        body = _remove_nul_byte_from_text(body[:RESOURCE_HEADER_BUFFER_LENGTH])
        url_parts = urlparse(url) if url else url
        content_type = _content_type_from_metadata(
            headers=headers,
            url_path=url_parts.path if url_parts else url_parts,
            filename=filename,
        )
        content_types = (content_type,) if content_type else None
        http_origin = not url or url_parts.scheme in ("http", "https")
        mime_type = extract_mime(
            body,
            content_types=content_types,
            http_origin=http_origin,
        )
        return _response_type_from_mime_type(mime_type)


responsetypes = ResponseTypes()
