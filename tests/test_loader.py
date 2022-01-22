import unittest

import attr
from itemadapter import ItemAdapter
from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst

from scrapy.http import HtmlResponse, Response
from scrapy.item import Item, Field
from scrapy.loader import ItemLoader
from scrapy.selector import Selector


try:
    from dataclasses import make_dataclass, field as dataclass_field
except ImportError:
    make_dataclass = None
    dataclass_field = None


# test items
class NameItem(Item):
    name = Field()


class TestItem(NameItem):
    url = Field()
    summary = Field()


class TestNestedItem(Item):
    name = Field()
    name_div = Field()
    name_value = Field()

    url = Field()
    image = Field()


@attr.s
class AttrsNameItem:
    name = attr.ib(default="")


# test item loaders
class NameItemLoader(ItemLoader):
    default_item_class = TestItem


class NestedItemLoader(ItemLoader):
    default_item_class = TestNestedItem


class TestItemLoader(NameItemLoader):
    name_in = MapCompose(lambda v: v.title())


class DefaultedItemLoader(NameItemLoader):
    default_input_processor = MapCompose(lambda v: v[:-1])


# test processors
def processor_with_args(value, other=None, loader_context=None):
    if 'key' in loader_context:
        return loader_context['key']
    return value


class BasicItemLoaderTest(unittest.TestCase):

    def test_add_value_on_unknown_field(self):
        il = TestItemLoader()
        self.assertRaises(KeyError, il.add_value, 'wrong_field', ['lala', 'lolo'])

    def test_load_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = 'lala'
        il = ItemLoader(item=i)
        il.add_value('name', 'marta')
        item = il.load_item()
        assert item is i
        self.assertEqual(item['summary'], ['lala'])
        self.assertEqual(item['name'], ['marta'])

    def test_load_item_using_custom_loader(self):
        il = TestItemLoader()
        il.add_value('name', 'marta')
        item = il.load_item()
        self.assertEqual(item['name'], ['Marta'])


class InitializationTestMixin:

    item_class = None

    def test_keep_single_value(self):
        """Loaded item should contain values from the initial item"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo']})

    def test_keep_list(self):
        """Loaded item should contain values from the initial item"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo', 'bar']})

    def test_add_value_singlevalue_singlevalue(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        il.add_value('name', 'bar')
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo', 'bar']})

    def test_add_value_singlevalue_list(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        il.add_value('name', ['item', 'loader'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo', 'item', 'loader']})

    def test_add_value_list_singlevalue(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        il.add_value('name', 'qwerty')
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo', 'bar', 'qwerty']})

    def test_add_value_list_list(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        il.add_value('name', ['item', 'loader'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), {'name': ['foo', 'bar', 'item', 'loader']})

    def test_get_output_value_singlevalue(self):
        """Getting output value must not remove value from item"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        self.assertEqual(il.get_output_value('name'), ['foo'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), dict({'name': ['foo']}))

    def test_get_output_value_list(self):
        """Getting output value must not remove value from item"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        self.assertEqual(il.get_output_value('name'), ['foo', 'bar'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(ItemAdapter(loaded_item).asdict(), dict({'name': ['foo', 'bar']}))

    def test_values_single(self):
        """Values from initial item must be added to loader._values"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        self.assertEqual(il._values.get('name'), ['foo'])

    def test_values_list(self):
        """Values from initial item must be added to loader._values"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        self.assertEqual(il._values.get('name'), ['foo', 'bar'])


class InitializationFromDictTest(InitializationTestMixin, unittest.TestCase):
    item_class = dict


class InitializationFromItemTest(InitializationTestMixin, unittest.TestCase):
    item_class = NameItem


class InitializationFromAttrsItemTest(InitializationTestMixin, unittest.TestCase):
    item_class = AttrsNameItem


@unittest.skipIf(not make_dataclass, "dataclasses module is not available")
class InitializationFromDataClassTest(InitializationTestMixin, unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if make_dataclass:
            self.item_class = make_dataclass(
                "TestDataClass",
                [("name", list, dataclass_field(default_factory=list))],
            )


class BaseNoInputReprocessingLoader(ItemLoader):
    title_in = MapCompose(str.upper)
    title_out = TakeFirst()


class NoInputReprocessingItem(Item):
    title = Field()


class NoInputReprocessingItemLoader(BaseNoInputReprocessingLoader):
    default_item_class = NoInputReprocessingItem


class NoInputReprocessingFromItemTest(unittest.TestCase):
    """
    Loaders initialized from loaded items must not reprocess fields (Item instances)
    """
    def test_avoid_reprocessing_with_initial_values_single(self):
        il = NoInputReprocessingItemLoader(item=NoInputReprocessingItem(title='foo'))
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, {'title': 'foo'})
        self.assertEqual(NoInputReprocessingItemLoader(item=il_loaded).load_item(), {'title': 'foo'})

    def test_avoid_reprocessing_with_initial_values_list(self):
        il = NoInputReprocessingItemLoader(item=NoInputReprocessingItem(title=['foo', 'bar']))
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, {'title': 'foo'})
        self.assertEqual(NoInputReprocessingItemLoader(item=il_loaded).load_item(), {'title': 'foo'})

    def test_avoid_reprocessing_without_initial_values_single(self):
        il = NoInputReprocessingItemLoader()
        il.add_value('title', 'FOO')
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, {'title': 'FOO'})
        self.assertEqual(NoInputReprocessingItemLoader(item=il_loaded).load_item(), {'title': 'FOO'})

    def test_avoid_reprocessing_without_initial_values_list(self):
        il = NoInputReprocessingItemLoader()
        il.add_value('title', ['foo', 'bar'])
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, {'title': 'FOO'})
        self.assertEqual(NoInputReprocessingItemLoader(item=il_loaded).load_item(), {'title': 'FOO'})


class TestOutputProcessorItem(unittest.TestCase):
    def test_output_processor(self):

        class TempItem(Item):
            temp = Field()

            def __init__(self, *args, **kwargs):
                super().__init__(self, *args, **kwargs)
                self.setdefault('temp', 0.3)

        class TempLoader(ItemLoader):
            default_item_class = TempItem
            default_input_processor = Identity()
            default_output_processor = Compose(TakeFirst())

        loader = TempLoader()
        item = loader.load_item()
        self.assertIsInstance(item, TempItem)
        self.assertEqual(dict(item), {'temp': 0.3})


class SelectortemLoaderTest(unittest.TestCase):
    response = HtmlResponse(url="", encoding='utf-8', body=b"""
    <html>
    <body>
    <div id="id">marta</div>
    <p>paragraph</p>
    <a href="http://www.scrapy.org">homepage</a>
    <img src="/images/logo.png" width="244" height="65" alt="Scrapy">
    </body>
    </html>
    """)

    def test_init_method(self):
        l = TestItemLoader()
        self.assertEqual(l.selector, None)

    def test_init_method_errors(self):
        l = TestItemLoader()
        self.assertRaises(RuntimeError, l.add_xpath, 'url', '//a/@href')
        self.assertRaises(RuntimeError, l.replace_xpath, 'url', '//a/@href')
        self.assertRaises(RuntimeError, l.get_xpath, '//a/@href')
        self.assertRaises(RuntimeError, l.add_css, 'name', '#name::text')
        self.assertRaises(RuntimeError, l.replace_css, 'name', '#name::text')
        self.assertRaises(RuntimeError, l.get_css, '#name::text')

    def test_init_method_with_selector(self):
        sel = Selector(text="<html><body><div>marta</div></body></html>")
        l = TestItemLoader(selector=sel)
        self.assertIs(l.selector, sel)

        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), ['Marta'])

    def test_init_method_with_selector_css(self):
        sel = Selector(text="<html><body><div>marta</div></body></html>")
        l = TestItemLoader(selector=sel)
        self.assertIs(l.selector, sel)

        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), ['Marta'])
    
    def test_init_method_with_base_response(self):
        """Selector should be None after initialization"""
        response = Response("https://scrapy.org")
        l = TestItemLoader(response=response)
        self.assertIs(l.selector, None)

    def test_init_method_with_response(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)

        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), ['Marta'])

    def test_init_method_with_response_css(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)

        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), ['Marta'])

        l.add_css('url', 'a::attr(href)')
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org'])

        # combining/accumulating CSS selectors and XPath expressions
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), ['Marta', 'Marta'])

        l.add_xpath('url', '//img/@src')
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org', '/images/logo.png'])

    def test_add_xpath_re(self):
        l = TestItemLoader(response=self.response)
        l.add_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), ['Ma'])

    def test_replace_xpath(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), ['Marta'])
        l.replace_xpath('name', '//p/text()')
        self.assertEqual(l.get_output_value('name'), ['Paragraph'])

        l.replace_xpath('name', ['//p/text()', '//div/text()'])
        self.assertEqual(l.get_output_value('name'), ['Paragraph', 'Marta'])

    def test_get_xpath(self):
        l = TestItemLoader(response=self.response)
        self.assertEqual(l.get_xpath('//p/text()'), ['paragraph'])
        self.assertEqual(l.get_xpath('//p/text()', TakeFirst()), 'paragraph')
        self.assertEqual(l.get_xpath('//p/text()', TakeFirst(), re='pa'), 'pa')

        self.assertEqual(l.get_xpath(['//p/text()', '//div/text()']), ['paragraph', 'marta'])

    def test_replace_xpath_multi_fields(self):
        l = TestItemLoader(response=self.response)
        l.add_xpath(None, '//div/text()', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), ['Marta'])
        l.replace_xpath(None, '//p/text()', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), ['Paragraph'])

    def test_replace_xpath_re(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), ['Marta'])
        l.replace_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), ['Ma'])

    def test_add_css_re(self):
        l = TestItemLoader(response=self.response)
        l.add_css('name', 'div::text', re='ma')
        self.assertEqual(l.get_output_value('name'), ['Ma'])

        l.add_css('url', 'a::attr(href)', re='http://(.+)')
        self.assertEqual(l.get_output_value('url'), ['www.scrapy.org'])

    def test_replace_css(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)
        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), ['Marta'])
        l.replace_css('name', 'p::text')
        self.assertEqual(l.get_output_value('name'), ['Paragraph'])

        l.replace_css('name', ['p::text', 'div::text'])
        self.assertEqual(l.get_output_value('name'), ['Paragraph', 'Marta'])

        l.add_css('url', 'a::attr(href)', re='http://(.+)')
        self.assertEqual(l.get_output_value('url'), ['www.scrapy.org'])
        l.replace_css('url', 'img::attr(src)')
        self.assertEqual(l.get_output_value('url'), ['/images/logo.png'])

    def test_get_css(self):
        l = TestItemLoader(response=self.response)
        self.assertEqual(l.get_css('p::text'), ['paragraph'])
        self.assertEqual(l.get_css('p::text', TakeFirst()), 'paragraph')
        self.assertEqual(l.get_css('p::text', TakeFirst(), re='pa'), 'pa')

        self.assertEqual(l.get_css(['p::text', 'div::text']), ['paragraph', 'marta'])
        self.assertEqual(l.get_css(['a::attr(href)', 'img::attr(src)']),
                         ['http://www.scrapy.org', '/images/logo.png'])

    def test_replace_css_multi_fields(self):
        l = TestItemLoader(response=self.response)
        l.add_css(None, 'div::text', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), ['Marta'])
        l.replace_css(None, 'p::text', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), ['Paragraph'])

        l.add_css(None, 'a::attr(href)', TakeFirst(), lambda x: {'url': x})
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org'])
        l.replace_css(None, 'img::attr(src)', TakeFirst(), lambda x: {'url': x})
        self.assertEqual(l.get_output_value('url'), ['/images/logo.png'])

    def test_replace_css_re(self):
        l = TestItemLoader(response=self.response)
        self.assertTrue(l.selector)
        l.add_css('url', 'a::attr(href)')
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org'])
        l.replace_css('url', 'a::attr(href)', re=r'http://www\.(.+)')
        self.assertEqual(l.get_output_value('url'), ['scrapy.org'])


class SubselectorLoaderTest(unittest.TestCase):
    response = HtmlResponse(url="", encoding='utf-8', body=b"""
    <html>
    <body>
    <header>
      <div id="id">marta</div>
      <p>paragraph</p>
    </header>
    <footer class="footer">
      <a href="http://www.scrapy.org">homepage</a>
      <img src="/images/logo.png" width="244" height="65" alt="Scrapy">
    </footer>
    </body>
    </html>
    """)

    def test_nested_xpath(self):
        l = NestedItemLoader(response=self.response)

        nl = l.nested_xpath("//header")
        nl.add_xpath('name', 'div/text()')
        nl.add_css('name_div', '#id')
        nl.add_value('name_value', nl.selector.xpath('div[@id = "id"]/text()').getall())

        self.assertEqual(l.get_output_value('name'), ['marta'])
        self.assertEqual(l.get_output_value('name_div'), ['<div id="id">marta</div>'])
        self.assertEqual(l.get_output_value('name_value'), ['marta'])

        self.assertEqual(l.get_output_value('name'), nl.get_output_value('name'))
        self.assertEqual(l.get_output_value('name_div'), nl.get_output_value('name_div'))
        self.assertEqual(l.get_output_value('name_value'), nl.get_output_value('name_value'))

    def test_nested_css(self):
        l = NestedItemLoader(response=self.response)
        nl = l.nested_css("header")
        nl.add_xpath('name', 'div/text()')
        nl.add_css('name_div', '#id')
        nl.add_value('name_value', nl.selector.xpath('div[@id = "id"]/text()').getall())

        self.assertEqual(l.get_output_value('name'), ['marta'])
        self.assertEqual(l.get_output_value('name_div'), ['<div id="id">marta</div>'])
        self.assertEqual(l.get_output_value('name_value'), ['marta'])

        self.assertEqual(l.get_output_value('name'), nl.get_output_value('name'))
        self.assertEqual(l.get_output_value('name_div'), nl.get_output_value('name_div'))
        self.assertEqual(l.get_output_value('name_value'), nl.get_output_value('name_value'))

    def test_nested_replace(self):
        l = NestedItemLoader(response=self.response)
        nl1 = l.nested_xpath('//footer')
        nl2 = nl1.nested_xpath('a')

        l.add_xpath('url', '//footer/a/@href')
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org'])
        nl1.replace_xpath('url', 'img/@src')
        self.assertEqual(l.get_output_value('url'), ['/images/logo.png'])
        nl2.replace_xpath('url', '@href')
        self.assertEqual(l.get_output_value('url'), ['http://www.scrapy.org'])

    def test_nested_ordering(self):
        l = NestedItemLoader(response=self.response)
        nl1 = l.nested_xpath('//footer')
        nl2 = nl1.nested_xpath('a')

        nl1.add_xpath('url', 'img/@src')
        l.add_xpath('url', '//footer/a/@href')
        nl2.add_xpath('url', 'text()')
        l.add_xpath('url', '//footer/a/@href')

        self.assertEqual(l.get_output_value('url'), [
            '/images/logo.png',
            'http://www.scrapy.org',
            'homepage',
            'http://www.scrapy.org',
        ])

    def test_nested_load_item(self):
        l = NestedItemLoader(response=self.response)
        nl1 = l.nested_xpath('//footer')
        nl2 = nl1.nested_xpath('img')

        l.add_xpath('name', '//header/div/text()')
        nl1.add_xpath('url', 'a/@href')
        nl2.add_xpath('image', '@src')

        item = l.load_item()

        assert item is l.item
        assert item is nl1.item
        assert item is nl2.item

        self.assertEqual(item['name'], ['marta'])
        self.assertEqual(item['url'], ['http://www.scrapy.org'])
        self.assertEqual(item['image'], ['/images/logo.png'])


# Functions as processors

def function_processor_strip(iterable):
    return [x.strip() for x in iterable]


def function_processor_upper(iterable):
    return [x.upper() for x in iterable]


class FunctionProcessorItem(Item):
    foo = Field(
        input_processor=function_processor_strip,
        output_processor=function_processor_upper,
    )


class FunctionProcessorItemLoader(ItemLoader):
    default_item_class = FunctionProcessorItem


class FunctionProcessorTestCase(unittest.TestCase):

    def test_processor_defined_in_item(self):
        lo = FunctionProcessorItemLoader()
        lo.add_value('foo', '  bar  ')
        lo.add_value('foo', ['  asdf  ', '  qwerty  '])
        self.assertEqual(
            dict(lo.load_item()),
            {'foo': ['BAR', 'ASDF', 'QWERTY']}
        )


if __name__ == "__main__":
    unittest.main()
