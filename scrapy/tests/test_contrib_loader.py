import unittest

from scrapy.contrib.loader import ItemLoader, XPathItemLoader
from scrapy.contrib.loader.processor import ApplyConcat, Join, Identity, Compose
from scrapy.newitem import Item, Field
from scrapy.xpath import HtmlXPathSelector
from scrapy.http import HtmlResponse

# test items

class NameItem(Item):
    name = Field()

class TestItem(NameItem):
    url = Field()
    summary = Field()

# test item loaders

class NameItemLoader(ItemLoader):
    default_item_class = TestItem

class TestItemLoader(NameItemLoader):
    name_in = ApplyConcat(lambda v: v.title())

class DefaultedItemLoader(NameItemLoader):
    default_input_processor = ApplyConcat(lambda v: v[:-1])

# test processors

def processor_with_args(value, other=None, loader_context=None):
    if 'key' in loader_context:
        return loader_context['key']
    return value

class ItemLoaderTest(unittest.TestCase):

    def test_load_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = u'lala'
        ip = ItemLoader(item=i)
        ip.add_value('name', u'marta')
        item = ip.load_item()
        assert item is i
        self.assertEqual(item['summary'], u'lala')
        self.assertEqual(item['name'], [u'marta'])

    def test_load_item_using_custom_loader(self):
        ip = TestItemLoader()
        ip.add_value('name', u'marta')
        item = ip.load_item()
        self.assertEqual(item['name'], [u'Marta'])

    def test_add_value(self):
        ip = TestItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])
        ip.add_value('name', u'pepe')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta', u'Pepe'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta', u'Pepe'])

    def test_replace_value(self):
        ip = TestItemLoader()
        ip.replace_value('name', u'marta')
        self.assertEqual(ip.get_collected_values('name'), [u'Marta'])
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])
        ip.replace_value('name', u'pepe')
        self.assertEqual(ip.get_collected_values('name'), [u'Pepe'])
        self.assertEqual(ip.get_output_value('name'), [u'Pepe'])

    def test_apply_concat_filter(self):
        def filter_world(x):
            return None if x == 'world' else x

        proc = ApplyConcat(filter_world, str.upper)
        self.assertEqual(proc(['hello', 'world', 'this', 'is', 'scrapy']),
                         ['HELLO', 'THIS', 'IS', 'SCRAPY'])

    def test_map_concat_filter_multiple_functions(self):
        class TestItemLoader(NameItemLoader):
            name_in = ApplyConcat(lambda v: v.title(), lambda v: v[:-1])

        ip = TestItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Mart'])
        item = ip.load_item()
        self.assertEqual(item['name'], [u'Mart'])

    def test_default_input_processor(self):
        ip = DefaultedItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mart'])

    def test_inherited_default_input_processor(self):
        class InheritDefaultedItemLoader(DefaultedItemLoader):
            pass

        ip = InheritDefaultedItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mart'])

    def test_input_processor_inheritance(self):
        class ChildItemLoader(TestItemLoader):
            url_in = ApplyConcat(lambda v: v.lower())

        ip = ChildItemLoader()
        ip.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(ip.get_output_value('url'), [u'http://scrapy.org'])
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])

        class ChildChildItemLoader(ChildItemLoader):
            url_in = ApplyConcat(lambda v: v.upper())
            summary_in = ApplyConcat(lambda v: v)

        ip = ChildChildItemLoader()
        ip.add_value('url', u'http://scrapy.org')
        self.assertEqual(ip.get_output_value('url'), [u'HTTP://SCRAPY.ORG'])
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'Marta'])

    def test_empty_map_concat(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = ApplyConcat()

        ip = IdentityDefaultedItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'marta'])

    def test_identity_input_processor(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = Identity()

        ip = IdentityDefaultedItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'marta'])

    def test_extend_custom_input_processors(self):
        class ChildItemLoader(TestItemLoader):
            name_in = ApplyConcat(TestItemLoader.name_in, unicode.swapcase)

        ip = ChildItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'mARTA'])

    def test_extend_default_input_processors(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            name_in = ApplyConcat(DefaultedItemLoader.default_input_processor, unicode.swapcase)

        ip = ChildDefaultedItemLoader()
        ip.add_value('name', u'marta')
        self.assertEqual(ip.get_output_value('name'), [u'MART'])

    def test_output_processor_using_function(self):
        ip = TestItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = u" ".join

        ip = TakeFirstItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar Ta')

    def test_output_processor_using_classes(self):
        ip = TestItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join()

        ip = TakeFirstItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar Ta')

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join("<br>")

        ip = TakeFirstItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), u'Mar<br>Ta')

    def test_default_output_processor(self):
        ip = TestItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

        class LalaItemLoader(TestItemLoader):
            default_output_processor = Identity()

        ip = LalaItemLoader()
        ip.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ip.get_output_value('name'), [u'Mar', u'Ta'])

    def test_loader_context_on_declaration(self):
        class ChildItemLoader(TestItemLoader):
            url_in = ApplyConcat(processor_with_args, key=u'val')

        ip = ChildItemLoader()
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_loader_context_on_instantiation(self):
        class ChildItemLoader(TestItemLoader):
            url_in = ApplyConcat(processor_with_args)

        ip = ChildItemLoader(key=u'val')
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_loader_context_on_assign(self):
        class ChildItemLoader(TestItemLoader):
            url_in = ApplyConcat(processor_with_args)

        ip = ChildItemLoader()
        ip.context['key'] = u'val'
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['val'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['val'])

    def test_item_passed_to_input_processor_functions(self):
        def processor(value, loader_context):
            return loader_context['item']['name']

        class ChildItemLoader(TestItemLoader):
            url_in = ApplyConcat(processor)

        it = TestItem(name='marta')
        ip = ChildItemLoader(item=it)
        ip.add_value('url', u'text')
        self.assertEqual(ip.get_output_value('url'), ['marta'])
        ip.replace_value('url', u'text2')
        self.assertEqual(ip.get_output_value('url'), ['marta'])

    def test_add_value_on_unknown_field(self):
        ip = TestItemLoader()
        self.assertRaises(KeyError, ip.add_value, 'wrong_field', [u'lala', u'lolo'])

    def test_compose_processor(self):
        class TestItemLoader(NameItemLoader):
            name_out = Compose(lambda v: v[0], lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()
        il.add_value('name', [u'marta', u'other'])
        self.assertEqual(il.get_output_value('name'), u'Mart')
        item = il.load_item()
        self.assertEqual(item['name'], u'Mart')


class TestXPathItemLoader(XPathItemLoader):
    default_item_class = TestItem
    name_in = ApplyConcat(lambda v: v.title())

class XPathItemLoaderTest(unittest.TestCase):

    def test_constructor_errors(self):
        self.assertRaises(RuntimeError, XPathItemLoader)

    def test_constructor_with_selector(self):
        sel = HtmlXPathSelector(text=u"<html><body><div>marta</div></body></html>")
        l = TestXPathItemLoader(selector=sel)
        self.assert_(l.selector is sel)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_constructor_with_response(self):
        response = HtmlResponse(url="", body="<html><body><div>marta</div></body></html>")
        l = TestXPathItemLoader(response=response)
        self.assert_(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_add_xpath_re(self):
        response = HtmlResponse(url="", body="<html><body><div>marta</div></body></html>")
        l = TestXPathItemLoader(response=response)
        l.add_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), [u'Ma'])


if __name__ == "__main__":
    unittest.main()

