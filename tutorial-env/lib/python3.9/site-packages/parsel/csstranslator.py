from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional

from cssselect import GenericTranslator as OriginalGenericTranslator
from cssselect import HTMLTranslator as OriginalHTMLTranslator
from cssselect.xpath import XPathExpr as OriginalXPathExpr
from cssselect.xpath import ExpressionError
from cssselect.parser import Element, FunctionalPseudoElement, PseudoElement


if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


class XPathExpr(OriginalXPathExpr):

    textnode: bool = False
    attribute: Optional[str] = None

    @classmethod
    def from_xpath(
        cls,
        xpath: OriginalXPathExpr,
        textnode: bool = False,
        attribute: Optional[str] = None,
    ) -> "Self":
        x = cls(
            path=xpath.path, element=xpath.element, condition=xpath.condition
        )
        x.textnode = textnode
        x.attribute = attribute
        return x

    def __str__(self) -> str:
        path = super().__str__()
        if self.textnode:
            if path == "*":
                path = "text()"
            elif path.endswith("::*/*"):
                path = path[:-3] + "text()"
            else:
                path += "/text()"

        if self.attribute is not None:
            if path.endswith("::*/*"):
                path = path[:-2]
            path += f"/@{self.attribute}"

        return path

    def join(
        self: "Self",
        combiner: str,
        other: OriginalXPathExpr,
        *args: Any,
        **kwargs: Any,
    ) -> "Self":
        if not isinstance(other, XPathExpr):
            raise ValueError(
                f"Expressions of type {__name__}.XPathExpr can ony join expressions"
                f" of the same type (or its descendants), got {type(other)}"
            )
        super().join(combiner, other, *args, **kwargs)
        self.textnode = other.textnode
        self.attribute = other.attribute
        return self


if TYPE_CHECKING:
    # requires Python 3.8
    from typing import Protocol

    # e.g. cssselect.GenericTranslator, cssselect.HTMLTranslator
    class TranslatorProtocol(Protocol):
        def xpath_element(self, selector: Element) -> OriginalXPathExpr:
            pass

        def css_to_xpath(self, css: str, prefix: str = ...) -> str:
            pass


class TranslatorMixin:
    """This mixin adds support to CSS pseudo elements via dynamic dispatch.

    Currently supported pseudo-elements are ``::text`` and ``::attr(ATTR_NAME)``.
    """

    def xpath_element(
        self: "TranslatorProtocol", selector: Element
    ) -> XPathExpr:
        # https://github.com/python/mypy/issues/12344
        xpath = super().xpath_element(selector)  # type: ignore[safe-super]
        return XPathExpr.from_xpath(xpath)

    def xpath_pseudo_element(
        self, xpath: OriginalXPathExpr, pseudo_element: PseudoElement
    ) -> OriginalXPathExpr:
        """
        Dispatch method that transforms XPath to support pseudo-element
        """
        if isinstance(pseudo_element, FunctionalPseudoElement):
            method_name = f"xpath_{pseudo_element.name.replace('-', '_')}_functional_pseudo_element"
            method = getattr(self, method_name, None)
            if not method:
                raise ExpressionError(
                    f"The functional pseudo-element ::{pseudo_element.name}() is unknown"
                )
            xpath = method(xpath, pseudo_element)
        else:
            method_name = f"xpath_{pseudo_element.replace('-', '_')}_simple_pseudo_element"
            method = getattr(self, method_name, None)
            if not method:
                raise ExpressionError(
                    f"The pseudo-element ::{pseudo_element} is unknown"
                )
            xpath = method(xpath)
        return xpath

    def xpath_attr_functional_pseudo_element(
        self, xpath: OriginalXPathExpr, function: FunctionalPseudoElement
    ) -> XPathExpr:
        """Support selecting attribute values using ::attr() pseudo-element"""
        if function.argument_types() not in (["STRING"], ["IDENT"]):
            raise ExpressionError(
                f"Expected a single string or ident for ::attr(), got {function.arguments!r}"
            )
        return XPathExpr.from_xpath(
            xpath, attribute=function.arguments[0].value
        )

    def xpath_text_simple_pseudo_element(
        self, xpath: OriginalXPathExpr
    ) -> XPathExpr:
        """Support selecting text nodes using ::text pseudo-element"""
        return XPathExpr.from_xpath(xpath, textnode=True)


class GenericTranslator(TranslatorMixin, OriginalGenericTranslator):
    @lru_cache(maxsize=256)
    def css_to_xpath(
        self, css: str, prefix: str = "descendant-or-self::"
    ) -> str:
        return super().css_to_xpath(css, prefix)


class HTMLTranslator(TranslatorMixin, OriginalHTMLTranslator):
    @lru_cache(maxsize=256)
    def css_to_xpath(
        self, css: str, prefix: str = "descendant-or-self::"
    ) -> str:
        return super().css_to_xpath(css, prefix)


_translator = HTMLTranslator()


def css2xpath(query: str) -> str:
    "Return translated XPath version of a given CSS query"
    return _translator.css_to_xpath(query)
