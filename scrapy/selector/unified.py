"""
selectors.Selector wrapper for compatability
"""
from scrapy.http import XmlResponse
from scrapy.utils.trackref import object_ref
from scrapy.selector.lxmldocument import LxmlDocument

from selectors import Selector as BaseSelector, SelectorList
from selectors.common import _ctgroup


__all__ = ['Selector', 'SelectorList']


def _st(response, st):
    if st is None:
        return 'xml' if isinstance(response, XmlResponse) else 'html'
    elif st in ('xml', 'html'):
        return st
    else:
        raise ValueError('Invalid type: %s' % st)


class Selector(BaseSelector, object_ref):

    # this is needed because it's not inherited
    __slots__ = ['response', 'text', 'namespaces', 'type',
                 '_expr', '_root', '__weakref__',
                 '_parser', '_csstranslator', '_tostring_method']

    _default_type = None

    def __init__(self, response=None, **kwargs):
        type = _st(response, kwargs.get('type', None) or self._default_type)

        kwargs.update(type=type)
        super(Selector, self).__init__(**kwargs)

        self.response = response
        if response is not None:
            parser = _ctgroup[type]['_parser']
            self._root = LxmlDocument(response, parser)
