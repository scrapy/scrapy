"""
This module implements a class which returns the appropriate Response class
based on different criteria.
"""
from mimetypes import MimeTypes
from pkgutil import get_data
from io import StringIO
from urllib.parse import urlparse

from xtractmime import extract_mime

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
        if isinstance(mimetype, bytes):
            mimetype = mimetype.decode()

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
        if content_encoding:
            return Response
        mimetype = to_unicode(content_type).split(';')[0].strip().lower()
        return self.from_mimetype(mimetype)

    def from_content_disposition(self, content_disposition):
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
        mimetype, encoding = self.mimetypes.guess_type(filename)
        if mimetype and not encoding:
            return self.from_mimetype(mimetype)
        else:
            return Response

    def from_args(self, headers=None, url=None, filename=None, body=None):
        """Guess the most appropriate Response class based on
        the given arguments."""
        cls = Response
        if cls is Response and body is not None:
            http_origin = True
            no_sniff = False
            content_types = None

            if url and urlparse(url).scheme not in ("http", "https"):
                http_origin = False

            if headers:
                if b'Content-Type' in headers:
                    content_types = (headers[b'Content-Type'],)

                if b'X-Content-Type-Options' in headers and headers[b'X-Content-Type-Options'] == b"nosniff":
                    no_sniff = True

            mime_type = extract_mime(body, content_types=content_types, http_origin=http_origin, no_sniff=no_sniff)
            cls = self.from_mimetype(mime_type)
        if cls is Response and headers is not None:
            cls = self.from_headers(headers)
        if cls is Response and url is not None:
            cls = self.from_filename(url)
        if cls is Response and filename is not None:
            cls = self.from_filename(filename)
        return cls


responsetypes = ResponseTypes()
