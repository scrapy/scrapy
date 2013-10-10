"""
Selectors
"""
from scrapy.selector.lxmlsel import *
from scrapy.selector.csssel import *
from scrapy.selector.list import SelectorList


class XPathSelectorList(SelectorList):

    def __init__(self, *a, **kw):
        import warnings
        from scrapy.exceptions import ScrapyDeprecationWarning
        warnings.warn('XPathSelectorList is deprecated, use '
                      'scrapy.selector.SelectorList instead',
                      category=ScrapyDeprecationWarning, stacklevel=1)
        super(XPathSelectorList, self).__init__(*a, **kw)
