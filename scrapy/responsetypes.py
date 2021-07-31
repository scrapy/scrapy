"""
This module implements a class which returns the appropriate Response class
based on different criteria.
"""
from mimetypes import MimeTypes
from pkgutil import get_data
from io import StringIO
from urllib.parse import urlparse
from warnings import warn

from xtractmime import RESOURCE_HEADER_BUFFER_LENGTH, extract_mime

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.utils.misc import load_object
from scrapy.utils.python import binary_is_text, to_bytes, to_unicode


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
        self.mimetypes = MimeTypes()
        mimedata = get_data('scrapy', 'mime.types').decode('utf8')
        self.mimetypes.readfp(StringIO(mimedata))
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
        mimetype, encoding = self.mimetypes.guess_type(filename)
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
        elif b"<html>" in chunk.lower():
            return self.from_mimetype('text/html')
        elif b"<?xml" in chunk.lower():
            return self.from_mimetype('text/xml')
        else:
            return self.from_mimetype('text')

    def _guess_content_type(self, headers=None, url=None, filename=None):
        if headers and b'Content-Type' in headers:
            return tuple(headers.getlist(b'Content-Type'))

        if headers and b'Content-Disposition' in headers:
            filename = headers.get(b'Content-Disposition').split(b';')[-1].split(b'=')[-1].strip(b'"\'').decode()
        elif url:
            filename = url

        if filename:
            return (self.mimetypes.guess_type(filename)[0].encode(),)

        return None

    def from_args(self, headers=None, url=None, filename=None, body=None):
        """Guess the most appropriate Response class based on
        the given arguments."""
        if not body:
            body = b''

        body = body[:RESOURCE_HEADER_BUFFER_LENGTH].replace(b"\x00", b"")
        cls = Response
        http_origin = not url or urlparse(url).scheme in ("http", "https")
        content_types = self._guess_content_type(headers=headers, url=url, filename=filename)
        mime_type = extract_mime(body, content_types=content_types, http_origin=http_origin)
        cls = self.from_mimetype(mime_type.decode())

        return cls


responsetypes = ResponseTypes()
