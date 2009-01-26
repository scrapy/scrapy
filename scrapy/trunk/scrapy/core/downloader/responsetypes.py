"""
This module implements a class which returns the appropiate Response class
based on different criterias.

"""

import mimetypes

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

    def from_headers(self, headers):
        """Return the most appropiate Response class by looking at the HTTP
        headers"""
        if 'Content-Type' in headers:
            return self.from_content_type(headers['Content-type'][0])
        else:
            return Response

    def from_filename(self, filename):
        """Return the most appropiate Response class from a file name"""
        return self.from_mimetype(mimetypes.guess_type(filename)[0])

    def from_url(self, url):
        """Return the most appropiate Response class from a URL"""
        return self.from_mimetype(mimetypes.guess_type(url)[0])

    def from_body(self, body):
        """Try to guess the appropiate response based on the body content. 
        
        This method is a bit magic and could be improved in the future, but
        it's not meant to be used except for special cases where response types
        cannot be guess using more straightforward methods.

        """
        chunk = body[:5000]
        if isbinarytext(chunk):
            return self.from_mimetype('application/octet-stream')
        elif "<html>" in chunk.lower():
            return self.from_mimetype('text/html')
        elif "<?xml" in chunk.lower():
            return self.from_mimetype('text/xml')
        else:
            return self.from_mimetype('text')

responsetypes = ResponseTypes()
