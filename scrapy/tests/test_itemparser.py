import unittest

from scrapy.contrib.itemparser import ItemParser, XPathItemParser
from scrapy.contrib.itemparser.parsers import ApplyConcat, Join, Identity
from scrapy.newitem import Item, Field
from scrapy.xpath import HtmlXPathSelector
from scrapy.http import HtmlResponse

# test items

class NameItem(Item):
    name = Field()

class TestItem(NameItem):
    url = Field()
    summary = Field()

# test item parsers

class NameItemParser(ItemParser):
    default_item_class = TestItem

class TestItemParser(NameItemParser):
    name_in = ApplyConcat(lambda v: v.title())

class DefaultedItemParser(NameItemParser):
    default_input_parser = ApplyConcat(lambda v: v[:-1])

# test parsers

def parser_with_args(value, other=None, parser_context=None):
    if 'key' in parser_context:
        return parser_context['key']
    return value

class ItemParserTest(unittest.TestCase):

    def test_populate_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = u'lala'
        ip = ItemParser(item=i)
        ip.add_value('name', u'marta')
        item = ip.populate_item()
        assert item is i
        self.assertEqual(item['summary'], u'lala')
        self.assertEqual(item['name'], [u'marta'])

    def test_populate_item_using_custom_loader(self):
        ip = TestItemParser()
        ip.add_value('name', u'marta')
        item = ip.populate_item()
        self.assertEqual(item['name'], [u'Marta'])

    def test_add_value(self):
        ip = TestItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])
        ip.add_value('name', u'pepe')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta', u'Pepe'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta', u'Pepe'])

    def test_replace_value(self):
        ip = TestItemParser()
        ip.replace_value('name', u'marta')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])
        ip.replace_value('name', u'pepe')
        self.assertEqual(ip.get_collected_values('name'), [u'Pepe'])
        self.assertEqual(ip.get_output_value('name'), [u'Pepe'])

    def test_map_concat_filter(self):
        def filter_world(x):
            return None if x == 'world' else x

        parser = ApplyConcat(filter_world, str.upper)
        self.assertEqual(parser(['hello', 'world', 'this', 'is', 'scrapy']),
                         ['HELLO', 'THIS', 'IS', 'SCRAPY'])

    def test_map_concat_filter_multiple_functions(self):
        class TestItemParser(NameItemParser):
            name_in = ApplyConcat(lambda v: v.title(), lambda v: v[:-1])

        ip = TestItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Mart'])
        item = ip.populate_item()
        self.assertEqual(item['name'], [u'Mart'])

    def test_default_input_parser(self):
        ip = DefaultedItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mart'])

    def test_inherited_default_input_parser(self):
        class InheritDefaultedItemParser(DefaultedItemParser):
            pass

        ip = InheritDefaultedItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mart'])

    def test_input_parser_inheritance(self):
        class ChildItemParser(TestItemParser):
            url_in = ApplyConcat(lambda v: v.lower())

        ip = ChildItemParser()
        ip.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(ip.get_output_value('url'), [u'http://scrapy.org'])
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])

        class ChildChildItemParser(ChildItemParser):
            url_in = ApplyConcat(lambda v: v.upper())
            summary_in = ApplyConcat(lambda v: v)

        ip = ChildChildItemParser()
        ip.add_value('url', u'http://scrapy.org')
        self.assertEqual(ip.get_output_value('url'), [u'HTTP://SCRAPY.ORG'])
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])

    def test_empty_map_concat(self):
        class IdentityDefaultedItemParser(DefaultedItemParser):
            name_in = ApplyConcat()

        ip = IdentityDefaultedItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'marta'])

    def test_identity_input_parser(self):
        class IdentityDefaultedItemParser(DefaultedItemParser):
            name_in = Identity()

        ip = IdentityDefaultedItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'marta'])

    def test_extend_custom_input_parsers(self):
        class ChildItemParser(TestItemParser):
            name_in = ApplyConcat(TestItemParser.name_in, unicode.swapcase)

        ip = ChildItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mARTA'])

    def test_extend_default_input_parsers(self):
        class ChildDefaultedItemParser(DefaultedItemParser):
            name_in = ApplyConcat(DefaultedItemParser.default_input_parser, unicode.swapcase)

        ip = ChildDefaultedItemParser()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'MART'])

    def test_output_parser_using_function(self):
        ip = TestItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemParser(TestItemParser):
            name_out = u" ".join

        ip = TakeFirstItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar Ta')

    def test_output_parser_using_classes(self):
        ip = TestItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemParser(TestItemParser):
            name_out = Join()

        ip = TakeFirstItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar Ta')

        class TakeFirstItemParser(TestItemParser):
            name_out = Join("<br>")

        ip = TakeFirstItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar<br>Ta')

    def test_default_output_parser(self):
        ip = TestItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class LalaItemParser(TestItemParser):
            default_output_parser = Identity()

        ip = LalaItemParser()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

    def test_parser_context_on_declaration(self):
        class ChildItemParser(TestItemParser):
            url_in = ApplyConcat(parser_with_args, key=u'val')

        ip = ChildItemParser()
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_parser_context_on_instantiation(self):
        class ChildItemParser(TestItemParser):
            url_in = ApplyConcat(parser_with_args)

        ip = ChildItemParser(key=u'val')
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_parser_context_on_assign(self):
        class ChildItemParser(TestItemParser):
            url_in = ApplyConcat(parser_with_args)

        ip = ChildItemParser()
        ip.context['key'] = u'val'
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_item_passed_to_input_parser_functions(self):
        def parser(value, parser_context):
            return parser_context['item']['name']

        class ChildItemParser(TestItemParser):
            url_in = ApplyConcat(parser)

        it = TestItem(name='marta')
        ip = ChildItemParser(item=it)
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['marta'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['marta'])

    def test_add_value_on_unknown_field(self):
        ip = TestItemParser()
        self.assertRaises(KeyError, ip.add_value, 'wrong_field', [u'lala', u'lolo'])


class TestXPathItemParser(XPathItemParser):
    default_item_class = TestItem
    name_in = ApplyConcat(lambda v: v.title())

class XPathItemParserTest(unittest.TestCase):

    def test_constructor_errors(self):
        self.assertRaises(RuntimeError, XPathItemParser)

    def test_constructor_with_selector(self):
        sel = HtmlXPathSelector(text=u"<html><body><div>marta</div></body></html>")
        l = TestXPathItemParser(selector=sel)
        self.assert_(l.selector is sel)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_constructor_with_response(self):
        response = HtmlResponse(url="", body="<html><body><div>marta</div></body></html>")
        l = TestXPathItemParser(response=response)
        self.assert_(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_add_xpath_re(self):
        response = HtmlResponse(url="", body="<html><body><div>marta</div></body></html>")
        l = TestXPathItemParser(response=response)
        l.add_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), [u'Ma'])


if __name__ == "__main__":
    unittest.main()

