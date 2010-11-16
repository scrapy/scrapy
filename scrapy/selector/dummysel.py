"""
Dummy selectors
"""

from .list import XPathSelectorList as XPathSelectorList

__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
    'XPathSelectorList']

class XPathSelector(object):

    def __init__(self, *a, **kw):
        pass

    def _raise(self, *a, **kw):
        raise RuntimeError("No selectors backend available. " \
            "Please install libxml2 or lxml")

    select = re = extract = register_namespace = __nonzero__ = _raise

XmlXPathSelector = XPathSelector
HtmlXPathSelector = XPathSelector
