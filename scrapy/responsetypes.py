"""
This module implements a class which returns the appropriate Response class
based on different criteria.
"""
from warnings import catch_warnings, simplefilter, warn

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.utils.misc import load_object
from scrapy.utils.python import binary_is_text, to_bytes, to_unicode
from scrapy.utils.response import _MIME_TYPES


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

    def __new__(cls, *args, **kwargs):
        warn(
            (
                'scrapy.responsetypes.ResponseTypes is deprecated, use '
                'scrapy.utils.response.get_response_class instead'
            ),
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return super().__new__(cls)

    def __init__(self):
        self.classes = {}
        self.mimetypes = _MIME_TYPES
        for mimetype, cls in self.CLASSES.items():
            self.classes[mimetype] = load_object(cls)

    def from_mimetype(self, mimetype):
        """Return the most appropriate Response class for the given mimetype"""
        warn('ResponseTypes.from_mimetype is deprecated, '
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
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
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
        if content_encoding:
            return Response
        mimetype = to_unicode(content_type).split(';')[0].strip().lower()
        return self.from_mimetype(mimetype)

    def from_content_disposition(self, content_disposition):
        warn('ResponseTypes.from_content_disposition is deprecated, '
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
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
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
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
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
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
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
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
        warn('ResponseTypes.from_args is deprecated, '
             'please use scrapy.utils.response.get_response_class instead', ScrapyDeprecationWarning)
        cls = Response
        if headers is not None:
            cls = self.from_headers(headers)
        if cls is Response and url is not None:
            cls = self.from_filename(url)
        if cls is Response and filename is not None:
            cls = self.from_filename(filename)
        if cls is Response and body is not None:
            cls = self.from_body(body)
        return cls


with catch_warnings():
    simplefilter("ignore")
    responsetypes = ResponseTypes()
