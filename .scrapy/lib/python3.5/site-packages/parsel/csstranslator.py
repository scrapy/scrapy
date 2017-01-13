from cssselect import GenericTranslator as OriginalGenericTranslator
from cssselect import HTMLTranslator as OriginalHTMLTranslator
from cssselect.xpath import XPathExpr as OriginalXPathExpr
from cssselect.xpath import _unicode_safe_getattr, ExpressionError
from cssselect.parser import FunctionalPseudoElement


class XPathExpr(OriginalXPathExpr):

    textnode = False
    attribute = None

    @classmethod
    def from_xpath(cls, xpath, textnode=False, attribute=None):
        x = cls(path=xpath.path, element=xpath.element, condition=xpath.condition)
        x.textnode = textnode
        x.attribute = attribute
        return x

    def __str__(self):
        path = super(XPathExpr, self).__str__()
        if self.textnode:
            if path == '*':
                path = 'text()'
            elif path.endswith('::*/*'):
                path = path[:-3] + 'text()'
            else:
                path += '/text()'

        if self.attribute is not None:
            if path.endswith('::*/*'):
                path = path[:-2]
            path += '/@%s' % self.attribute

        return path

    def join(self, combiner, other):
        super(XPathExpr, self).join(combiner, other)
        self.textnode = other.textnode
        self.attribute = other.attribute
        return self


class TranslatorMixin(object):
    """This mixin adds support to CSS pseudo elements via dynamic dispatch.

    Currently supported pseudo-elements are ``::text`` and ``::attr(ATTR_NAME)``.
    """

    def xpath_element(self, selector):
        xpath = super(TranslatorMixin, self).xpath_element(selector)
        return XPathExpr.from_xpath(xpath)

    def xpath_pseudo_element(self, xpath, pseudo_element):
        """
        Dispatch method that transforms XPath to support pseudo-element
        """
        if isinstance(pseudo_element, FunctionalPseudoElement):
            method = 'xpath_%s_functional_pseudo_element' % (
                pseudo_element.name.replace('-', '_'))
            method = _unicode_safe_getattr(self, method, None)
            if not method:
                raise ExpressionError(
                    "The functional pseudo-element ::%s() is unknown"
                    % pseudo_element.name)
            xpath = method(xpath, pseudo_element)
        else:
            method = 'xpath_%s_simple_pseudo_element' % (
                pseudo_element.replace('-', '_'))
            method = _unicode_safe_getattr(self, method, None)
            if not method:
                raise ExpressionError(
                    "The pseudo-element ::%s is unknown"
                    % pseudo_element)
            xpath = method(xpath)
        return xpath

    def xpath_attr_functional_pseudo_element(self, xpath, function):
        """Support selecting attribute values using ::attr() pseudo-element
        """
        if function.argument_types() not in (['STRING'], ['IDENT']):
            raise ExpressionError(
                "Expected a single string or ident for ::attr(), got %r"
                % function.arguments)
        return XPathExpr.from_xpath(xpath,
                                    attribute=function.arguments[0].value)

    def xpath_text_simple_pseudo_element(self, xpath):
        """Support selecting text nodes using ::text pseudo-element"""
        return XPathExpr.from_xpath(xpath, textnode=True)


class GenericTranslator(TranslatorMixin, OriginalGenericTranslator):
    pass


class HTMLTranslator(TranslatorMixin, OriginalHTMLTranslator):
    pass
