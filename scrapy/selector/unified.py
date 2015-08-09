"""
XPath selectors based on lxml
"""

import warnings
from parsel import Selector as ParselSelector, SelectorList
from scrapy.utils.trackref import object_ref
from scrapy.utils.python import to_bytes
from scrapy.http import HtmlResponse, XmlResponse
from scrapy.utils.decorators import deprecated
from scrapy.exceptions import ScrapyDeprecationWarning


__all__ = ['Selector', 'SelectorList']


def _st(response, st):
    if st is None:
        return 'xml' if isinstance(response, XmlResponse) else 'html'
    return st


def _response_from_text(text, st):
    rt = XmlResponse if st == 'xml' else HtmlResponse
    return rt(url='about:blank', encoding='utf-8',
              body=to_bytes(text, 'utf-8'))


class Selector(ParselSelector, object_ref):

    __slots__ = ['response']

    def __init__(self, response=None, text=None, type=None, root=None, _root=None, **kwargs):
        st = _st(response, type or self._default_type)

        if _root is not None:
            warnings.warn("Argument `_root` is deprecated, use `root` instead",
                          ScrapyDeprecationWarning, stacklevel=2)
            if root is None:
                root = _root
            else:
                warnings.warn("Ignoring deprecated `_root` argument, using provided `root`")

        if text is not None:
            response = _response_from_text(text, st)

        if response is not None:
            text = response.body_as_unicode()

        self.response = response
        super(Selector, self).__init__(text=text, type=st, root=root, **kwargs)

    # Deprecated api
    @property
    def _root(self):
        warnings.warn("Attribute `_root` is deprecated, use `root` instead",
                      ScrapyDeprecationWarning, stacklevel=2)
        return self.root

    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)

    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return self.extract()
