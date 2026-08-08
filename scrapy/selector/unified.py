from __future__ import annotations

from typing import Any, Literal

from parsel import Selector as _ParselSelector

from scrapy.http import HtmlResponse, TextResponse, XmlResponse
from scrapy.utils.python import to_bytes
from scrapy.utils.response import get_base_url
from scrapy.utils.trackref import object_ref

__all__ = ["Selector", "SelectorList"]

_NOT_SET = object()


SelectorType = Literal["html", "xml", "json", "text"]


def _response_from_text(text: str | bytes, st: SelectorType | None) -> TextResponse:
    rt: type[TextResponse] = XmlResponse if st == "xml" else HtmlResponse
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

    ``type`` defines the selector type, it can be ``"html"``, ``"xml"``,
    ``"json"``, ``"text"`` or ``None`` (default). It's passed to
    :class:`parsel.Selector` and its meaning is defined there. However, when
    ``type`` is ``None``, it is set to ``"xml"`` for an
    :class:`~scrapy.http.XmlResponse` and to ``"html"`` otherwise before
    passing it to :class:`parsel.Selector`.

    .. note:: JSON selector support requires ``parsel`` 1.8.0 or higher. With
       older versions setting ``type`` to ``"json"`` or ``"text"`` is not
       supported.
    """

    __slots__ = ["response"]
    selectorlist_cls = SelectorList

    def __init__(
        self,
        response: TextResponse | None = None,
        text: str | None = None,
        type: SelectorType | None = None,  # noqa: A002
        root: Any | None = _NOT_SET,
        **kwargs: Any,
    ):
        if response is not None and text is not None:
            raise ValueError(
                f"{self.__class__.__name__}.__init__() received both response and text"
            )

        if type is None:
            type = "xml" if isinstance(response, XmlResponse) else "html"  # noqa: A001

        if text is not None:
            response = _response_from_text(text, type)

        if response is not None:
            text = response.text
            kwargs.setdefault("base_url", get_base_url(response))

        self.response = response

        if root is not _NOT_SET:
            kwargs["root"] = root

        super().__init__(text=text, type=type, **kwargs)
