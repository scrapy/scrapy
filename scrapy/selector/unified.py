"""
XPath selectors based on lxml
"""

import warnings
from parsel import Selector as _ParselSelector
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


class SelectorList(_ParselSelector.selectorlist_cls, object_ref):
    """
    The :class:`SelectorList` class is a subclass of the builtin ``list``
    class, which provides a few additional methods.
    """
    @deprecated(use_instead='.extract()')
    def extract_unquoted(self):
        return [x.extract_unquoted() for x in self]

    @deprecated(use_instead='.xpath()')
    def x(self, xpath):
        return self.select(xpath)

    @deprecated(use_instead='.xpath()')
    def select(self, xpath):
        return self.xpath(xpath)


class Selector(_ParselSelector, object_ref):
    """
    An instance of :class:`Selector` is a wrapper over response to select
    certain parts of its content.

    ``response`` is an :class:`~scrapy.http.HtmlResponse` or an
    :class:`~scrapy.http.XmlResponse` object that will be used for selecting
    and extracting data.

    ``text`` is a unicode string or utf-8 encoded text for cases when a
    ``response`` isn't available. Using ``text`` and ``response`` together is
    undefined behavior.

    ``type`` defines the selector type, it can be ``"html"``, ``"xml"``
    or ``None`` (default).

    If ``type`` is ``None``, the selector automatically chooses the best type
    based on ``response`` type (see below), or defaults to ``"html"`` in case it
    is used together with ``text``.

    If ``type`` is ``None`` and a ``response`` is passed, the selector type is
    inferred from the response type as follows:

    * ``"html"`` for :class:`~scrapy.http.HtmlResponse` type
    * ``"xml"`` for :class:`~scrapy.http.XmlResponse` type
    * ``"html"`` for anything else

    Otherwise, if ``type`` is set, the selector type will be forced and no
    detection will occur.
    """

    __slots__ = ['response']
    selectorlist_cls = SelectorList

    def __init__(self, response=None, text=None, type=None, root=None, _root=None, **kwargs):
        if not(response is None or text is None):
           raise ValueError('%s.__init__() received both response and text'
                            % self.__class__.__name__)

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
            text = response.text
            kwargs.setdefault('base_url', response.url)

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
