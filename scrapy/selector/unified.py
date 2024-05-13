"""
XPath selectors based on lxml
"""
from typing import Any, Optional, Type, Union

from parsel import Selector as _ParselSelector

from scrapy.http import HtmlResponse, TextResponse, XmlResponse
from scrapy.utils.python import to_bytes
from scrapy.utils.response import get_base_url
from scrapy.utils.trackref import object_ref

__all__ = ["Selector", "SelectorList"]

_NOT_SET = object()


def _st(response: Optional[TextResponse], st: Optional[str]) -> str:
    if st is None:
        return "xml" if isinstance(response, XmlResponse) else "html"
    return st


def _response_from_text(text: Union[str, bytes], st: Optional[str]) -> TextResponse:
    rt: Type[TextResponse] = XmlResponse if st == "xml" else HtmlResponse
    return rt(url="about:blank", encoding="utf-8", body=to_bytes(text, "utf-8"))


class SelectorList(_ParselSelector.selectorlist_cls, object_ref):
    """
    The :class:`SelectorList` class is a subclass of the builtin ``list``
    class, which provides a few additional methods.
    """


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

    ``type`` defines the selector type, it can be ``"html"``, ``"xml"``, ``"json"``
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

    __slots__ = ["response"]
    selectorlist_cls = SelectorList

    def __init__(
        self,
        response: Optional[TextResponse] = None,
        text: Optional[str] = None,
        type: Optional[str] = None,
        root: Optional[Any] = _NOT_SET,
        **kwargs: Any,
    ):
        if response is not None and text is not None:
            raise ValueError(
                f"{self.__class__.__name__}.__init__() received "
                "both response and text"
            )

        st = _st(response, type)

        if text is not None:
            response = _response_from_text(text, st)

        if response is not None:
            text = response.text
            kwargs.setdefault("base_url", get_base_url(response))

        self.response = response

        if root is not _NOT_SET:
            kwargs["root"] = root

        super().__init__(text=text, type=st, **kwargs)
