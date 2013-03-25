"""
XPath selectors

To select the backend explicitly use the SCRAPY_SELECTORS_BACKEND environment
variable.

Two backends are currently available: lxml (default) and libxml2.

"""
import os


backend = os.environ.get('SCRAPY_SELECTORS_BACKEND')
if backend == 'libxml2':
    from scrapy.selector.libxml2sel import *
elif backend == 'lxml':
    from scrapy.selector.lxmlsel import *
else:
    try:
        import lxml
    except ImportError:
        import libxml2
        from scrapy.selector.libxml2sel import *
    else:
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
