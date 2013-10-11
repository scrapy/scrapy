from .unified import Selector


class CSSSelector(Selector):

    default_contenttype = 'html'

    def select(self, css):
        return self.css(css)


HtmlCSSSelector = CSSSelector


class XmlCSSSelector(CSSSelector):
    default_contenttype = 'xml'
