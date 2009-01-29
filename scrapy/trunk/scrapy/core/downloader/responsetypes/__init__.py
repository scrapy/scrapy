"""
This module implements a class which returns the appropiate Response class
based on different criterias.

"""

from os.path import abspath, dirname, join
from mimetypes import MimeTypes

from scrapy.http import Response
from scrapy.utils.misc import load_class
from scrapy.utils.python import isbinarytext
from scrapy.conf import settings

class ResponseTypes(object):

    CLASSES = {
        'text/html': 'scrapy.http.HtmlResponse',
        'application/xml': 'scrapy.http.XmlResponse',
        'text/xml': 'scrapy.http.XmlResponse',
        'text': 'scrapy.http.TextResponse',
    }

    def __init__(self):
        self.CLASSES.update(settings.get('RESPONSE_CLASSES', {}))
        self.classes = {}
        mimefile = join(abspath(dirname(__file__)), 'mime.types')
        self.mimetypes = MimeTypes([mimefile])
        for mimetype, cls in self.CLASSES.iteritems():
            self.classes[mimetype] = load_class(cls)

    def from_mimetype(self, mimetype):
        """Return the most appropiate Response class for the given mimetype"""
        return self.classes.get(mimetype, self.classes.get(mimetype.split('/')[0], Response))

    def from_content_type(self, content_type):
        """Return the most appropiate Response class from an HTTP Content-Type
        header """
        mimetype = content_type.split(';')[0].strip().lower()
        return self.from_mimetype(mimetype)

    def from_content_disposition(self, content_disposition):
        try:
            filename = content_disposition.split(';')[1].split('=')[1]
            filename = filename.strip('"\'')
            return self.from_filename(filename)
        except IndexError:
            return Response

    def from_headers(self, headers):
        """Return the most appropiate Response class by looking at the HTTP
        headers"""
        cls = Response
        if 'Content-Type' in headers:
            cls = self.from_content_type(headers['Content-type'][0])
        if cls is Response and 'Content-Disposition' in headers:
            cls = self.from_content_disposition(headers['Content-Disposition'][0])
        return cls

    def from_filename(self, filename):
        """Return the most appropiate Response class from a file name"""
        mimetype, encoding = self.mimetypes.guess_type(filename)
        if mimetype and not encoding:
            return self.from_mimetype(mimetype)
        else:
            return Response

    def from_url(self, url):
        """Return the most appropiate Response class from a URL"""
        return self.from_mimetype(self.mimetypes.guess_type(url)[0])

    def from_body(self, body):
        """Try to guess the appropiate response based on the body content.
        This method is a bit magic and could be improved in the future, but
        it's not meant to be used except for special cases where response types
        cannot be guess using more straightforward methods."""
        chunk = body[:5000]
        if isbinarytext(chunk):
            return self.from_mimetype('application/octet-stream')
        elif "<html>" in chunk.lower():
            return self.from_mimetype('text/html')
        elif "<?xml" in chunk.lower():
            return self.from_mimetype('text/xml')
        else:
            return self.from_mimetype('text')

    def from_args(self, headers=None, url=None, filename=None, body=None):
        """Guess the most appropiate Response class based on the given arguments"""
        cls = Response
        if headers is not None:
            cls = self.from_headers(headers)
        if cls is Response and url is not None:
            cls = self.from_url(url)
        if cls is Response and filename is not None:
            cls = self.from_filename(filename)
        if cls is Response and body is not None:
            cls = self.from_body(body)
        return cls

responsetypes = ResponseTypes()
