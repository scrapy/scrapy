from cssselect import GenericTranslator, HTMLTranslator
from scrapy.utils.python import flatten
from scrapy.selector import HtmlXPathSelector, XmlXPathSelector, XPathSelectorList

class CSSSelectorList(XPathSelectorList):
    def xpath(self, xpath):
        return self.__class__(flatten([x.xpath(xpath) for x in self]))

    def get(self, attr):
        return self.__class__(flatten([x.get(attr) for x in self]))

    def text(self, all=False):
        return self.__class__(flatten([x.text(all) for x in self]))

class CSSSelectorMixin(object):
    def select(self, css):
        return CSSSelectorList(super(CSSSelectorMixin, self).select(self.translator.css_to_xpath(css)))

    def xpath(self, xpath):
        return CSSSelectorList(super(CSSSelectorMixin, self).select(xpath))

    def text(self, all=False):
        return self.xpath('string()') if all else self.xpath('text()')

    def get(self, attr):
        return self.xpath('@' + attr)

class XmlCSSSelector(CSSSelectorMixin, XmlXPathSelector):
    translator = GenericTranslator()

class HtmlCSSSelector(CSSSelectorMixin, HtmlXPathSelector):
    translator = HTMLTranslator()
