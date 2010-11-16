"""
Selectors tests, specific for lxml backend
"""

from scrapy.http import TextResponse, XmlResponse
has_lxml = True
try:
    from scrapy.selector.lxmlsel import XmlXPathSelector, HtmlXPathSelector, \
        XPathSelector
except ImportError:
    has_lxml = False
from scrapy.utils.test import libxml2debug
from scrapy.tests import test_selector

class LxmlXPathSelectorTestCase(test_selector.XPathSelectorTestCase):

    if has_lxml:
        xs_cls = XPathSelector
        hxs_cls = HtmlXPathSelector
        xxs_cls = XmlXPathSelector
    else:
        skip = "lxml not available"

    # XXX: this test was disabled because lxml behaves inconsistently when
    # handling null bytes between different 2.2.x versions, but it may be due
    # to differences in libxml2 too. it's also unclear what should be the
    # proper behaviour (pablo - 26 oct 2010)
    #@libxml2debug
    #def test_null_bytes(self):
    #    hxs = HtmlXPathSelector(text='<root>la\x00la</root>')
    #    self.assertEqual(hxs.extract(),
    #                     u'<html><body><root>la</root></body></html>')
    #
    #    xxs = XmlXPathSelector(text='<root>la\x00la</root>')
    #    self.assertEqual(xxs.extract(),
    #                     u'<root>la</root>')
