from cssselect import GenericTranslator, HTMLTranslator
from cssselect.xpath import _unicode, _unicode_safe_getattr, XPathExpr, ExpressionError
from cssselect.parser import FunctionalPseudoElement


class ScrapyXPathExpr(XPathExpr):

    textnode = False
    attribute = None

    @classmethod
    def from_xpath(cls, xpath, textnode=False, attribute=None):
        x = cls(path=xpath.path, element=xpath.element, condition=xpath.condition)
        x.textnode = textnode
        x.attribute = attribute
        return x

    def __str__(self):
        path = super(ScrapyXPathExpr, self).__str__()
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
        super(ScrapyXPathExpr, self).join(combiner, other)
        self.textnode = other.textnode
        self.attribute = other.attribute
        return self


class TranslatorMixin(object):

    def xpath_element(self, selector):
        xpath = super(TranslatorMixin, self).xpath_element(selector)
        return ScrapyXPathExpr.from_xpath(xpath)

    def xpath_pseudo_element(self, xpath, pseudo_element):
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
        if function.argument_types() not in (['STRING'], ['IDENT']):
            raise ExpressionError(
                "Expected a single string or ident for ::attr(), got %r"
                % function.arguments)
        return ScrapyXPathExpr.from_xpath(xpath,
            attribute=function.arguments[0].value)

    def xpath_text_simple_pseudo_element(self, xpath):
        """Support selecting text nodes using ::text pseudo-element"""
        return ScrapyXPathExpr.from_xpath(xpath, textnode=True)

    def xpath_sibling_predicate(self, xpexpr, axis, count):
        predicate = "%s::%s" % (axis, _unicode(xpexpr.element))
        if xpexpr.condition:
            predicate += "[%s]" % xpexpr.condition
        return "count(%s)=%d" % (predicate, count)

    def xpath_first_pseudo(self, xpath):
        """Support selecting first child nodes using :first pseudo-class"""
        xpexpr = ScrapyXPathExpr.from_xpath(xpath)
        predicate = self.xpath_sibling_predicate(xpexpr, "preceding-sibling", 0)
        xpexpr.add_condition(predicate)
        return xpexpr

    def xpath_last_pseudo(self, xpath):
        """Support selecting last child nodes using :last pseudo-class"""
        xpexpr = ScrapyXPathExpr.from_xpath(xpath)
        predicate = self.xpath_sibling_predicate(xpexpr, "following-sibling", 0)
        xpexpr.add_condition(predicate)
        return xpexpr

    def xpath_nth_function(self, xpath, function):
        """Support selecting n-th child nodes using ::nth(N) pseudo-class"""
        if function.argument_types() not in (['NUMBER'],):
            raise ExpressionError(
                "Expected a single number for ::nth(), got %r"
                % function.arguments)
        xpexpr = ScrapyXPathExpr.from_xpath(xpath)
        predicate = self.xpath_sibling_predicate(xpexpr, "preceding-sibling",
            int(function.arguments[0].value)-1)
        xpexpr.add_condition(predicate)
        return xpexpr


class ScrapyGenericTranslator(TranslatorMixin, GenericTranslator):
    pass


class ScrapyHTMLTranslator(TranslatorMixin, HTMLTranslator):
    pass

