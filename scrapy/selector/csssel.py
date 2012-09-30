from scrapy.selector import HtmlXPathSelector, XmlXPathSelector
from cssselect import GenericTranslator, HTMLTranslator

class XmlCSSSelector(XmlXPathSelector):
    translator = GenericTranslator()
    def select(self, css):
        return super(XMLCSSSelector, self).select(self.translator.css_to_xpath(css))

class HtmlCSSSelector(HtmlXPathSelector):
    translator = HTMLTranslator()
    def select(self, css):
        return super(HtmlCSSSelector, self).select(self.translator.css_to_xpath(css))
