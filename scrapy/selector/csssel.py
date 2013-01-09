from cssselect import GenericTranslator, HTMLTranslator
from cssselect.xpath import XPathExpr, ExpressionError
from scrapy.selector import XPathSelector, HtmlXPathSelector, XmlXPathSelector


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

    def xpath_text_pseudo(self, xpath):
        """Support selecting text nodes using :text pseudo-element"""
        return ScrapyXPathExpr.from_xpath(xpath, textnode=True)

    def xpath_attribute_function(self, xpath, function):
        if function.argument_types() not in (['STRING'], ['IDENT']):
            raise ExpressionError(
                "Expected a single string or ident for :contains(), got %r"
                % function.arguments)
        value = function.arguments[0].value
        return ScrapyXPathExpr.from_xpath(xpath, attribute=value)


class ScrapyGenericTranslator(TranslatorMixin, GenericTranslator):
    pass


class ScrapyHTMLTranslator(TranslatorMixin, HTMLTranslator):
    pass


class CSSSelectorMixin(object):

    def select(self, css):
        xpath = self._css2xpath(css)
        return super(CSSSelectorMixin, self).select(xpath)

    def _css2xpath(self, css):
        return self.translator.css_to_xpath(css)


class CSSSelector(CSSSelectorMixin, XPathSelector):
    translator = ScrapyHTMLTranslator()


class HtmlCSSSelector(CSSSelectorMixin, HtmlXPathSelector):
    translator = ScrapyHTMLTranslator()


class XmlCSSSelector(CSSSelectorMixin, XmlXPathSelector):
    translator = ScrapyGenericTranslator()
