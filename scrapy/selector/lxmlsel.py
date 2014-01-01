"""
XPath selectors based on lxml
"""
from .unified import Selector, SelectorList


__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector',
           'XPathSelectorList']


class XPathSelector(Selector):
    __slots__ = ()
    _default_type = 'html'

    def __init__(self, *a, **kw):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('%s is deprecated, instantiate scrapy.selector.Selector '
                      'instead' % type(self).__name__,
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(XPathSelector, self).__init__(*a, **kw)

    def css(self, *a, **kw):
        raise RuntimeError('.css() method not available for %s, '
                           'instantiate scrapy.selector.Selector '
                           'instead' % type(self).__name__)


class XmlXPathSelector(XPathSelector):
    __slots__ = ()
    _default_type = 'xml'


class HtmlXPathSelector(XPathSelector):
    __slots__ = ()
    _default_type = 'html'


class XPathSelectorList(SelectorList):

    def __init__(self, *a, **kw):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('XPathSelectorList is deprecated, instantiate '
                      'scrapy.selector.SelectorList instead',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(XPathSelectorList, self).__init__(*a, **kw)
