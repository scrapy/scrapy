"""
XPath selectors based on lxml
"""

from scrapy.utils.trackref import object_ref
from scrapy.utils.python import to_bytes
from scrapy.http import HtmlResponse, XmlResponse
from scrapy.utils.decorators import deprecated
from parsel import Selector as ParselSelector, SelectorList
from parsel.unified import _ctgroup
from .lxmldocument import LxmlDocument


__all__ = ['Selector', 'SelectorList']


def _st(response, st):
    if st is None:
        return 'xml' if isinstance(response, XmlResponse) else 'html'
    elif st in ('xml', 'html'):
        return st
    else:
        raise ValueError('Invalid type: %s' % st)


def _response_from_text(text, st):
    rt = XmlResponse if st == 'xml' else HtmlResponse
    return rt(url='about:blank', encoding='utf-8',
              body=to_bytes(text, 'utf-8'))


class Selector(ParselSelector, object_ref):

    __slots__ = ['response']

    def __init__(self, response=None, text=None, type=None, root=None, **kwargs):
        st = _st(response, type or self._default_type)
        root = kwargs.get('root', root)

        self._parser = _ctgroup[st]['_parser']

        if text is not None:
            response = _response_from_text(text, st)

        if response is not None:
            root = LxmlDocument(response, self._parser)

        self.response = response
        text = response.body_as_unicode() if response else None
        super(Selector, self).__init__(text=text, type=st, root=root, **kwargs)

    # Deprecated api
    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)

    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return self.extract()

