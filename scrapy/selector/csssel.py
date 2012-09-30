from lxml.etree import XPath
from scrapy.selector import HtmlXPathSelector, XmlXPathSelector
from cssselect import GenericTranslator, HTMLTranslator

class CSSSelectorMixin(object):
    translator = GenericTranslator()
    _collect_string_content = XPath("string()")

    def text_content(self):
        return self._collect_string_content(self._root)

    def get(self, key, default=None):
        return self._root.get(key, default)

class XmlCSSSelector(XmlXPathSelector, CSSSelectorMixin):
    def select(self, css):
        return super(self.__class__, self).select(self.translator.css_to_xpath(css))

class HtmlCSSSelector(HtmlXPathSelector, CSSSelectorMixin):
    translator = HTMLTranslator()

    def select(self, css):
        return super(self.__class__, self).select(self.translator.css_to_xpath(css))
