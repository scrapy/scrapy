from twisted.trial import unittest

from scrapy.contrib.loader.processor import MapCompose
from scrapy.item import Item, Field
from scrapy.http import HtmlResponse

try:
    import lxml
except ImportError:
    lxml = False


class TestItem(Item):
    name = Field()


if lxml:
    from scrapy.contrib_exp.loader.lxmlloader import LxmlItemLoader

    class TestLxmlItemLoader(LxmlItemLoader):
        default_item_class = TestItem


class LxmlItemLoaderTest(unittest.TestCase):
    response = HtmlResponse(url="", body='<html><body><div id="id">marta</div><p>paragraph</p></body></html>')

    def setUp(self):
        if not lxml:
            raise unittest.SkipTest("lxml is not available")

    def test_constructor_with_response(self):
        l = TestLxmlItemLoader(response=self.response)
        self.assert_(l.tree)

    def test_add_xpath(self):
        l = TestLxmlItemLoader(response=self.response)
        l.add_xpath('name', '//div')
        self.assertEqual(l.get_output_value('name'), [u'<div id="id">marta</div>'])

    def test_add_xpath_text(self):
        l = TestLxmlItemLoader(response=self.response)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'marta'])

    def test_replace_xpath(self):
        l = TestLxmlItemLoader(response=self.response)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'marta'])
        l.replace_xpath('name', '//p/text()')
        self.assertEqual(l.get_output_value('name'), [u'paragraph'])

    def test_add_css(self):
        l = TestLxmlItemLoader(response=self.response)
        l.add_css('name', '#id')
        self.assertEqual(l.get_output_value('name'), [u'<div id="id">marta</div>'])

    def test_replace_css(self):
        l = TestLxmlItemLoader(response=self.response)
        l.add_css('name', '#id')
        self.assertEqual(l.get_output_value('name'), [u'<div id="id">marta</div>'])
        l.replace_css('name', 'p')
        self.assertEqual(l.get_output_value('name'), [u'<p>paragraph</p>'])


if __name__ == "__main__":
    unittest.main()

