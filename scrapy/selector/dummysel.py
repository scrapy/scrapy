"""
Dummy selectors
"""

__all__ = ['HtmlXPathSelector', 'XmlXPathSelector', 'XPathSelector', \
    'XPathSelectorList']

class XPathSelector(object):

    def __init__(self, *a, **kw):
        pass

    def _raise(self, *a, **kw):
        raise RuntimeError("No selectors backend available. " \
            "Please install libxml2 or lxml")

    select = re = exract = register_namespace = __nonzero__ = _raise

class XPathSelectorList(list):

    def _raise(self, *a, **kw):
        raise RuntimeError("No selectors backend available. " \
            "Please install libxml2 or lxml")

    __getslice__ = select = re = extract = extract_unquoted = _raise

XmlXPathSelector = XPathSelector
HtmlXPathSelector = XPathSelector
