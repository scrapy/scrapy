"""
This module defines the Link object used in Link extractors.

For actual link extractors implementation see scrapy.contrib.linkextractor, or
its documentation in: docs/ref/link-extractors.rst
"""

class Link(object):
    """Link objects represent an extracted link by the LinkExtractor.
    At the moment, it contains just the url and link text.
    """

    __slots__ = 'url', 'text'

    def __init__(self, url, text=''):
        self.url = url
        self.text = text

    def __eq__(self, other):
        return self.url == other.url and self.text == other.text

    def __repr__(self):
        return '<Link url=%r text=%r >' % (self.url, self.text)


# FIXME: code below is for backwards compatibility and should be removed before
# the 0.7 release

import warnings

from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor, BaseSgmlLinkExtractor

class LinkExtractor(BaseSgmlLinkExtractor):
    
    def __init__(self, *args, **kwargs):
        warnings.warn("scrapy.link.LinkExtractor is deprecated, use scrapy.contrib.linkextractors.sgml.BaseSgmlLinkExtractor instead",
            DeprecationWarning, stacklevel=2)
        BaseSgmlLinkExtractor.__init__(self, *args, **kwargs)

class RegexLinkExtractor(SgmlLinkExtractor):

    def __init__(self, *args, **kwargs):
        warnings.warn("scrapy.link.RegexLinkExtractor is deprecated, use scrapy.contrib.linkextractors.sgml.SgmlLinkExtractor instead",
            DeprecationWarning, stacklevel=2)
        SgmlLinkExtractor.__init__(self, *args, **kwargs)

