"""
This module defines the Link object used in Link extractors.

For actual link extractors implementation see scrapy.contrib.linkextractor, or
its documentation in: docs/topics/link-extractors.rst
"""

class Link(object):
    """Link objects represent an extracted link by the LinkExtractor.
    At the moment, it contains just the url and link text.
    """

    __slots__ = ['url', 'text']

    def __init__(self, url, text=''):
        self.url = url
        self.text = text

    def __eq__(self, other):
        return self.url == other.url and self.text == other.text
    
    def __hash__(self):
        return hash(self.url) ^ hash(self.text)

    def __repr__(self):
        return '<Link url=%r text=%r >' % (self.url, self.text)

