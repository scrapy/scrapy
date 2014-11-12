"""
This module defines the Link object used in Link extractors.

For actual link extractors implementation see scrapy.contrib.linkextractor, or
its documentation in: docs/topics/link-extractors.rst
"""

import six

class Link(object):
    """Link objects represent an extracted link by the LinkExtractor."""

    __slots__ = ['url', 'text', 'fragment', 'nofollow']

    def __init__(self, url, text='', fragment='', nofollow=False):
        if isinstance(url, six.text_type):
            import warnings
            warnings.warn("Do not instantiate Link objects with unicode urls. "
                "Assuming utf-8 encoding (which could be wrong)")
            url = url.encode('utf-8')
        self.url = url
        self.text = text
        self.fragment = fragment
        self.nofollow = nofollow

    def __eq__(self, other):
        return self.url == other.url and self.text == other.text and \
            self.fragment == other.fragment and self.nofollow == other.nofollow

    def __hash__(self):
        return hash(self.url) ^ hash(self.text) ^ hash(self.fragment) ^ hash(self.nofollow)

    def __repr__(self):
        return 'Link(url=%r, text=%r, fragment=%r, nofollow=%r)' % \
            (self.url, self.text, self.fragment, self.nofollow)

