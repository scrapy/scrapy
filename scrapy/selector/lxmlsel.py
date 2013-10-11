"""
XPath selectors based on lxml
"""
from .unified import Selector, SelectorList


__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector',
           'XPathSelectorList']


class XPathSelector(Selector):
    __slots__ = ()
    default_contenttype = 'xml'


class XmlXPathSelector(XPathSelector):
    __slots__ = ()
    default_contenttype = 'xml'


class HtmlXPathSelector(XPathSelector):
    __slots__ = ()
    default_contenttype = 'html'


class XPathSelectorList(SelectorList):

    def __init__(self, *a, **kw):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('XPathSelectorList is deprecated, use '
                      'scrapy.selector.SelectorList instead',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(XPathSelectorList, self).__init__(*a, **kw)
