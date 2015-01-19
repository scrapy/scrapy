# coding=utf-8
import re
import string
import unittest
from functools import partial

from scrapy.contrib.loader import ItemLoader
from scrapy.contrib.loader.common import purge_chars
from scrapy.contrib.loader.processor import Join, Identity, TakeFirst, \
    Compose, MapCompose, Strip, OnlyChars, TakeNth, OnlyAsciiItems, OnlyDigits, Replace, Filter, ReSub, OnlyAscii, \
    OnlyCharsItems, OnlyDigitsItems, ParseNum
from scrapy.item import Item, Field
from scrapy.selector import Selector
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
    name_in = MapCompose(lambda v: v.title())


class DefaultedItemLoader(NameItemLoader):
    default_input_processor = MapCompose(lambda v: v[:-1])


# test processors
def processor_with_args(value, other=None, loader_context=None):
    if 'key' in loader_context:
        return loader_context['key']
    return value


class BasicItemLoaderTest(unittest.TestCase):

    def test_load_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = u'lala'
        il = ItemLoader(item=i)
        il.add_value('name', u'marta')
        item = il.load_item()
        assert item is i
        self.assertEqual(item['summary'], u'lala')
        self.assertEqual(item['name'], [u'marta'])

    def test_load_item_using_custom_loader(self):
        il = TestItemLoader()
        il.add_value('name', u'marta')
        item = il.load_item()
        self.assertEqual(item['name'], [u'Marta'])

    def test_load_item_ignore_none_field_values(self):
        def validate_sku(value):
            # Let's assume a SKU is only digits.
            if value.isdigit():
                return value

        class MyLoader(ItemLoader):
            name_out = Compose(lambda vs: vs[0])  # take first which allows empty values
            price_out = Compose(TakeFirst(), float)
            sku_out = Compose(TakeFirst(), validate_sku)

        valid_fragment = u'SKU: 1234'
        invalid_fragment = u'SKU: not available'
        sku_re = 'SKU: (.+)'

        il = MyLoader(item={})
        # Should not return "sku: None".
        il.add_value('sku', [invalid_fragment], re=sku_re)
        # Should not ignore empty values.
        il.add_value('name', u'')
        il.add_value('price', [u'0'])
        self.assertEqual(il.load_item(), {
            'name': u'',
            'price': 0.0,
        })

        il.replace_value('sku', [valid_fragment], re=sku_re)
        self.assertEqual(il.load_item()['sku'], u'1234')

    def test_add_value(self):
        il = TestItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_collected_values('name'), [u'Marta'])
        self.assertEqual(il.get_output_value('name'), [u'Marta'])
        il.add_value('name', u'pepe')
        self.assertEqual(il.get_collected_values('name'), [u'Marta', u'Pepe'])
        self.assertEqual(il.get_output_value('name'), [u'Marta', u'Pepe'])

        # test add object value
        il.add_value('summary', {'key': 1})
        self.assertEqual(il.get_collected_values('summary'), [{'key': 1}])

        il.add_value(None, u'Jim', lambda x: {'name': x})
        self.assertEqual(il.get_collected_values('name'), [u'Marta', u'Pepe', u'Jim'])

    def test_add_zero(self):
        il = NameItemLoader()
        il.add_value('name', 0)
        self.assertEqual(il.get_collected_values('name'), [0])

    def test_replace_value(self):
        il = TestItemLoader()
        il.replace_value('name', u'marta')
        self.assertEqual(il.get_collected_values('name'), [u'Marta'])
        self.assertEqual(il.get_output_value('name'), [u'Marta'])
        il.replace_value('name', u'pepe')
        self.assertEqual(il.get_collected_values('name'), [u'Pepe'])
        self.assertEqual(il.get_output_value('name'), [u'Pepe'])

        il.replace_value(None, u'Jim', lambda x: {'name': x})
        self.assertEqual(il.get_collected_values('name'), [u'Jim'])

    def test_get_value(self):
        il = NameItemLoader()
        self.assertEqual(u'FOO', il.get_value([u'foo', u'bar'], TakeFirst(), unicode.upper))
        self.assertEqual([u'foo', u'bar'], il.get_value([u'name:foo', u'name:bar'], re=u'name:(.*)$'))
        self.assertEqual(u'foo', il.get_value([u'name:foo', u'name:bar'], TakeFirst(), re=u'name:(.*)$'))

        il.add_value('name', [u'name:foo', u'name:bar'], TakeFirst(), re=u'name:(.*)$')
        self.assertEqual([u'foo'], il.get_collected_values('name'))
        il.replace_value('name', u'name:bar', re=u'name:(.*)$')
        self.assertEqual([u'bar'], il.get_collected_values('name'))

    def test_iter_on_input_processor_input(self):
        class NameFirstItemLoader(NameItemLoader):
            name_in = TakeFirst()

        il = NameFirstItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_collected_values('name'), [u'marta'])
        il = NameFirstItemLoader()
        il.add_value('name', [u'marta', u'jose'])
        self.assertEqual(il.get_collected_values('name'), [u'marta'])

        il = NameFirstItemLoader()
        il.replace_value('name', u'marta')
        self.assertEqual(il.get_collected_values('name'), [u'marta'])
        il = NameFirstItemLoader()
        il.replace_value('name', [u'marta', u'jose'])
        self.assertEqual(il.get_collected_values('name'), [u'marta'])

        il = NameFirstItemLoader()
        il.add_value('name', u'marta')
        il.add_value('name', [u'jose', u'pedro'])
        self.assertEqual(il.get_collected_values('name'), [u'marta', u'jose'])

    def test_map_compose_filter(self):
        def filter_world(x):
            return None if x == 'world' else x

        proc = MapCompose(filter_world, str.upper)
        self.assertEqual(proc(['hello', 'world', 'this', 'is', 'scrapy']),
                         ['HELLO', 'THIS', 'IS', 'SCRAPY'])

    def test_map_compose_filter_multil(self):
        class TestItemLoader(NameItemLoader):
            name_in = MapCompose(lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'Mart'])
        item = il.load_item()
        self.assertEqual(item['name'], [u'Mart'])

    def test_default_input_processor(self):
        il = DefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'mart'])

    def test_inherited_default_input_processor(self):
        class InheritDefaultedItemLoader(DefaultedItemLoader):
            pass

        il = InheritDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'mart'])

    def test_input_processor_inheritance(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(lambda v: v.lower())

        il = ChildItemLoader()
        il.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(il.get_output_value('url'), [u'http://scrapy.org'])
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'Marta'])

        class ChildChildItemLoader(ChildItemLoader):
            url_in = MapCompose(lambda v: v.upper())
            summary_in = MapCompose(lambda v: v)

        il = ChildChildItemLoader()
        il.add_value('url', u'http://scrapy.org')
        self.assertEqual(il.get_output_value('url'), [u'HTTP://SCRAPY.ORG'])
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'Marta'])

    def test_empty_map_compose(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = MapCompose()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'marta'])

    def test_identity_input_processor(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = Identity()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'marta'])

    def test_extend_custom_input_processors(self):
        class ChildItemLoader(TestItemLoader):
            name_in = MapCompose(TestItemLoader.name_in, unicode.swapcase)

        il = ChildItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'mARTA'])

    def test_extend_default_input_processors(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            name_in = MapCompose(DefaultedItemLoader.default_input_processor, unicode.swapcase)

        il = ChildDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'MART'])

    def test_output_processor_using_function(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = u" ".join

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), u'Mar Ta')

    def test_output_processor_error(self):
        class TestItemLoader(ItemLoader):
            default_item_class = TestItem
            name_out = MapCompose(float)

        il = TestItemLoader()
        il.add_value('name', [u'$10'])
        try:
            float('$10')
        except Exception as e:
            expected_exc_str = str(e)

        exc = None
        try:
            il.load_item()
        except Exception as e:
            exc = e
        assert isinstance(exc, ValueError)
        s = str(exc)
        assert 'name' in s, s
        assert '$10' in s, s
        assert 'ValueError' in s, s
        assert expected_exc_str in s, s

    def test_output_processor_using_classes(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), [u'Mar', u'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join()

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), u'Mar Ta')

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join("<br>")

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), u'Mar<br>Ta')

    def test_default_output_processor(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), [u'Mar', u'Ta'])

        class LalaItemLoader(TestItemLoader):
            default_output_processor = Identity()

        il = LalaItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_output_value('name'), [u'Mar', u'Ta'])

    def test_loader_context_on_declaration(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args, key=u'val')

        il = ChildItemLoader()
        il.add_value('url', u'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', u'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_loader_context_on_instantiation(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args)

        il = ChildItemLoader(key=u'val')
        il.add_value('url', u'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', u'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_loader_context_on_assign(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args)

        il = ChildItemLoader()
        il.context['key'] = u'val'
        il.add_value('url', u'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', u'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_item_passed_to_input_processor_functions(self):
        def processor(value, loader_context):
            return loader_context['item']['name']

        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor)

        it = TestItem(name='marta')
        il = ChildItemLoader(item=it)
        il.add_value('url', u'text')
        self.assertEqual(il.get_output_value('url'), ['marta'])
        il.replace_value('url', u'text2')
        self.assertEqual(il.get_output_value('url'), ['marta'])

    def test_add_value_on_unknown_field(self):
        il = TestItemLoader()
        self.assertRaises(KeyError, il.add_value, 'wrong_field', [u'lala', u'lolo'])

    def test_compose_processor(self):
        class TestItemLoader(NameItemLoader):
            name_out = Compose(lambda v: v[0], lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()
        il.add_value('name', [u'marta', u'other'])
        self.assertEqual(il.get_output_value('name'), u'Mart')
        item = il.load_item()
        self.assertEqual(item['name'], u'Mart')

    def test_partial_processor(self):
        def join(values, sep=None, loader_context=None, ignored=None):
            if sep is not None:
                return sep.join(values)
            elif loader_context and 'sep' in loader_context:
                return loader_context['sep'].join(values)
            else:
                return ''.join(values)

        class TestItemLoader(NameItemLoader):
            name_out = Compose(partial(join, sep='+'))
            url_out = Compose(partial(join, loader_context={'sep': '.'}))
            summary_out = Compose(partial(join, ignored='foo'))

        il = TestItemLoader()
        il.add_value('name', [u'rabbit', u'hole'])
        il.add_value('url', [u'rabbit', u'hole'])
        il.add_value('summary', [u'rabbit', u'hole'])
        item = il.load_item()
        self.assertEqual(item['name'], u'rabbit+hole')
        self.assertEqual(item['url'], u'rabbit.hole')
        self.assertEqual(item['summary'], u'rabbithole')


class ProcessorsTest(unittest.TestCase):

    def test_take_first(self):
        proc = TakeFirst()
        self.assertEqual(proc([None, '', 'hello', 'world']), 'hello')
        self.assertEqual(proc([None, '', 0, 'hello', 'world']), 0)

    def test_identity(self):
        proc = Identity()
        self.assertEqual(proc([None, '', 'hello', 'world']),
                         [None, '', 'hello', 'world'])

    def test_join(self):
        proc = Join()
        self.assertRaises(TypeError, proc, [None, '', 'hello', 'world'])
        self.assertEqual(proc(['', 'hello', 'world']), u' hello world')
        self.assertEqual(proc(['hello', 'world']), u'hello world')
        self.assert_(isinstance(proc(['hello', 'world']), unicode))

    def test_compose(self):
        proc = Compose(lambda v: v[0], str.upper)
        self.assertEqual(proc(['hello', 'world']), 'HELLO')
        proc = Compose(str.upper)
        self.assertEqual(proc(None), None)
        proc = Compose(str.upper, stop_on_none=False)
        self.assertRaises(TypeError, proc, None)

    def test_mapcompose(self):
        filter_world = lambda x: None if x == 'world' else x
        proc = MapCompose(filter_world, unicode.upper)
        self.assertEqual(proc([u'hello', u'world', u'this', u'is', u'scrapy']),
                         [u'HELLO', u'THIS', u'IS', u'SCRAPY'])


class SelectortemLoaderTest(unittest.TestCase):
    response = HtmlResponse(url="", body="""
    <html>
    <body>
    <div id="id">marta</div>
    <p>paragraph</p>
    <a href="http://www.scrapy.org">homepage</a>
    <img src="/images/logo.png" width="244" height="65" alt="Scrapy">
    </body>
    </html>
    """)

    def test_constructor(self):
        l = TestItemLoader()
        self.assertEqual(l.selector, None)

    def test_constructor_errors(self):
        l = TestItemLoader()
        self.assertRaises(RuntimeError, l.add_xpath, 'url', '//a/@href')
        self.assertRaises(RuntimeError, l.replace_xpath, 'url', '//a/@href')
        self.assertRaises(RuntimeError, l.get_xpath, '//a/@href')
        self.assertRaises(RuntimeError, l.add_css, 'name', '#name::text')
        self.assertRaises(RuntimeError, l.replace_css, 'name', '#name::text')
        self.assertRaises(RuntimeError, l.get_css, '#name::text')

    def test_constructor_with_selector(self):
        sel = Selector(text=u"<html><body><div>marta</div></body></html>")
        l = TestItemLoader(selector=sel)
        self.assert_(l.selector is sel)

        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_constructor_with_selector_css(self):
        sel = Selector(text=u"<html><body><div>marta</div></body></html>")
        l = TestItemLoader(selector=sel)
        self.assert_(l.selector is sel)

        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_constructor_with_response(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)

        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

    def test_constructor_with_response_css(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)

        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])

        l.add_css('url', 'a::attr(href)')
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org'])

        # combining/accumulating CSS selectors and XPath expressions
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta', u'Marta'])

        l.add_xpath('url', '//img/@src')
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org', u'/images/logo.png'])

    def test_add_xpath_re(self):
        l = TestItemLoader(response=self.response)
        l.add_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), [u'Ma'])

    def test_replace_xpath(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])
        l.replace_xpath('name', '//p/text()')
        self.assertEqual(l.get_output_value('name'), [u'Paragraph'])

        l.replace_xpath('name', ['//p/text()', '//div/text()'])
        self.assertEqual(l.get_output_value('name'), [u'Paragraph', 'Marta'])

    def test_get_xpath(self):
        l = TestItemLoader(response=self.response)
        self.assertEqual(l.get_xpath('//p/text()'), [u'paragraph'])
        self.assertEqual(l.get_xpath('//p/text()', TakeFirst()), u'paragraph')
        self.assertEqual(l.get_xpath('//p/text()', TakeFirst(), re='pa'), u'pa')

        self.assertEqual(l.get_xpath(['//p/text()', '//div/text()']), [u'paragraph', 'marta'])

    def test_replace_xpath_multi_fields(self):
        l = TestItemLoader(response=self.response)
        l.add_xpath(None, '//div/text()', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), [u'Marta'])
        l.replace_xpath(None, '//p/text()', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), [u'Paragraph'])

    def test_replace_xpath_re(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)
        l.add_xpath('name', '//div/text()')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])
        l.replace_xpath('name', '//div/text()', re='ma')
        self.assertEqual(l.get_output_value('name'), [u'Ma'])

    def test_add_css_re(self):
        l = TestItemLoader(response=self.response)
        l.add_css('name', 'div::text', re='ma')
        self.assertEqual(l.get_output_value('name'), [u'Ma'])

        l.add_css('url', 'a::attr(href)', re='http://(.+)')
        self.assertEqual(l.get_output_value('url'), [u'www.scrapy.org'])

    def test_replace_css(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)
        l.add_css('name', 'div::text')
        self.assertEqual(l.get_output_value('name'), [u'Marta'])
        l.replace_css('name', 'p::text')
        self.assertEqual(l.get_output_value('name'), [u'Paragraph'])

        l.replace_css('name', ['p::text', 'div::text'])
        self.assertEqual(l.get_output_value('name'), [u'Paragraph', 'Marta'])

        l.add_css('url', 'a::attr(href)', re='http://(.+)')
        self.assertEqual(l.get_output_value('url'), [u'www.scrapy.org'])
        l.replace_css('url', 'img::attr(src)')
        self.assertEqual(l.get_output_value('url'), [u'/images/logo.png'])

    def test_get_css(self):
        l = TestItemLoader(response=self.response)
        self.assertEqual(l.get_css('p::text'), [u'paragraph'])
        self.assertEqual(l.get_css('p::text', TakeFirst()), u'paragraph')
        self.assertEqual(l.get_css('p::text', TakeFirst(), re='pa'), u'pa')

        self.assertEqual(l.get_css(['p::text', 'div::text']), [u'paragraph', 'marta'])
        self.assertEqual(l.get_css(['a::attr(href)', 'img::attr(src)']),
            [u'http://www.scrapy.org', u'/images/logo.png'])

    def test_replace_css_multi_fields(self):
        l = TestItemLoader(response=self.response)
        l.add_css(None, 'div::text', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), [u'Marta'])
        l.replace_css(None, 'p::text', TakeFirst(), lambda x: {'name': x})
        self.assertEqual(l.get_output_value('name'), [u'Paragraph'])

        l.add_css(None, 'a::attr(href)', TakeFirst(), lambda x: {'url': x})
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org'])
        l.replace_css(None, 'img::attr(src)', TakeFirst(), lambda x: {'url': x})
        self.assertEqual(l.get_output_value('url'), [u'/images/logo.png'])

    def test_replace_css_re(self):
        l = TestItemLoader(response=self.response)
        self.assert_(l.selector)
        l.add_css('url', 'a::attr(href)')
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org'])
        l.replace_css('url', 'a::attr(href)', re='http://www\.(.+)')
        self.assertEqual(l.get_output_value('url'), [u'scrapy.org'])


class TakeNthTestCase(unittest.TestCase):
    test_lists_equals = {
        'simple': (5, range(10), 5, None),
        'list_of_lists': (1, [range(10), range(5)], range(5), None),
        'zero': (0, range(10), 0, None),
        'with_none': (2, [0, 1, None, 3], 3, None),
        'with_empty_str': (2, [0, 1, '', 3], 3, None),
        'string': (2, 'hello', 'l', None),
        'out_of_range': (10, 'hello', None, None),
        'one_too_high': (5, 'hello', None, None),  # lists starts from 0 where's len starts from 1
        'fallback_takefirst': (10, 'hello', 'h', TakeFirst()),  # You can fallback to different processor
        'nofallback_takefirst': (4, 'hello', 'o', TakeFirst()),  # You can fallback to different processor
        'fallback_self': (10, 'hello', 'hello', lambda value: value),
        'minus': (-1, 'hello', 'o', None),
    }
    test_list_errors = {
        'int': (2, 12345, TypeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            pos, test_list, expected, fallback_func = self.test_lists_equals[l]
            test = TakeNth(pos, fallback_func)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            pos, test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, TakeNth(pos).__call__, test_list)


class OnlyAsciiItemsTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_non_english': (u'lietuvių', None, ''),
        'russian': (u'русский', None, ''),
        'single_english': (u'english', 'english', ''),
        'list_non_englush': ([u'šuo', u'lietuvių'], [], ''),
        'list_englush': (['hi', "I'm", 'english'], ['hi', "I'm", 'english'], ''),
        'except': (u'ša', u'ša', u'š'),
        'except_list': ([u'ša', u'русский'], [u'ša'], u'šй'),
    }
    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, except_chars = self.test_lists_equals[l]
            test = OnlyAsciiItems(except_chars=except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg=u'test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyAsciiItems().__call__, test_list)


class OnlyAsciiTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_non_english': (u'lietuvių', 'lietuvi'),
        'russian': (u'русский', None),
        'single_english': (u'english', 'english'),
        'list_non_english': ([u'šuo', u'lietuvių'], ['uo', 'lietuvi']),
        'list_mix': (['hi', u'lietuvių'], ['hi', 'lietuvi']),
        'list_english': (['hi', "I'm", 'english'], ['hi', "I'm", 'english']),
        'printable': ([string.printable, 'english'], [string.printable, 'english']),
        'except': (u'this is русский', u'this is й', u'й'),
    }
    test_list_errors = {
        'int': (12345, TypeError),
        'float': (12345.0, TypeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected = self.test_lists_equals[l][0], self.test_lists_equals[l][1]
            except_chars = self.test_lists_equals[l][2] if len(self.test_lists_equals[l]) > 2 else ''
            test = OnlyAscii(except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg=u'test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyAscii().__call__, test_list)


class OnlyDigitsTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_digits': ('123456', '123456', ''),
        'single_mix': ('1a2b3c', '123', ''),
        'single_non_digits': ('english', '', ''),  # empty string when string expected
        'digits_list': (['123', '456'], ['123', '456'], ''),
        'char_list': (['abc', 'def'], [], ''),
        'mix_list': (['1a2b', '3c4d'], ['12', '34'], ''),
        'non_digits_list': (['one', 'two'], [], ''),  # empty list when list expected
        'punctuation': ('1+2=3', '1+2=3', string.punctuation),  # empty list when list expected
    }
    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, except_chars = self.test_lists_equals[l]
            test = OnlyDigits(except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyDigits().__call__, test_list)


class OnlyCharsTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_digits': ('123456', '', ''),  # empty string when string expected
        'single_mix': ('1a2b3c', 'abc', ''),
        'single_non_digits': ('english', 'english', ''),
        'digits_list': (['123', '456'], [], ''),  # empty list when list expected
        'char_list': (['abc', 'def'], ['abc', 'def'], ''),
        'mix_list': (['1a2b', '3c4d'], ['ab', 'cd'], ''),
        'non_digits_list': (['one', 'two'], ['one', 'two'], ''),
        'punctuation': ('one+two', 'one+two', string.punctuation),
        'punctuation_list': (['one+two', '=three'], ['one+two', '=three'], string.punctuation),
    }
    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, except_chars = self.test_lists_equals[l]
            test = OnlyChars(except_chars=except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyChars().__call__, test_list)


class OnlyCharsItemsTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_digits': ('123456', None, ''),  # empty string when string expected
        'single_mix': ('1a2b3c', None, ''),
        'single_non_digits': ('english', 'english', ''),
        'digits_list': (['123', '456'], [], ''),  # empty list when list expected
        'char_list': (['abc', 'def'], ['abc', 'def'], ''),
        'mix_list': (['1a2b', '3c4d'], [], ''),
        'non_digits_list': (['one', 'two'], ['one', 'two'], ''),
        'with_punctuation': ('foobar. is it?', 'foobar. is it?', string.punctuation + string.whitespace),
        'with_punctuation_list': (['foo bar.', 'char', '1.hi'], ['foo bar.', 'char'], string.punctuation + string.whitespace),
    }

    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, except_chars = self.test_lists_equals[l]
            test = OnlyCharsItems(except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyCharsItems().__call__, test_list)


class OnlyDigitsItemsTestCase(unittest.TestCase):
    test_lists_equals = {
        'single_digits': ('123456', '123456', ''),
        'single_mix': ('1a2b3c', None, ''),
        'single_non_digits': ('english', None, ''),
        'digits_list': (['123', '456'], ['123', '456'], ''),
        'char_list': (['abc', 'def'], [], ''),  # empty list when list expected
        'mix_list': (['1a2b', '3c4d'], [], ''),
        'non_digits_list': (['one', 'two'], [], ''),
        'with_punctuation': ('1+2=3', '1+2=3', string.punctuation),
        'with_punctuation_list': (['2+2=4', 'char', '1?'], ['2+2=4', '1?'], string.punctuation),
    }
    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, except_chars = self.test_lists_equals[l]
            test = OnlyDigitsItems(except_chars=except_chars)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyDigitsItems().__call__, test_list)


class ParseNumTestCase(unittest.TestCase):
    test_lists_equals = {
        'simple_int': ('10,000', '10000', int, None),
        'simple_int_list': (['10,000', '20,000'], ['10000', '20000'], int, None),
        'simple_float': ('10,000.000', '10000.0', float, None),
        'simple_float_list': (['10,000.7', '20,000.99'], ['10000.7', '20000.99'], float, None),
    }
    test_list_errors = {
        'inti': (12345, AttributeError, int, None),
        'intf': (12345, AttributeError, float, None),
        'floati': (12345.0, AttributeError, int, None),
        'floatf': (12345.0, AttributeError, float, None),
        'float_when_int': ('10,000.000', ValueError, int, None),
        'texti': ('hello', ValueError, int, None),
        'textf': ('hello', ValueError, float, None),
        'text_listi': (['hello', 'bro'], ValueError, int, None),
        'text_listf': (['hello', 'bro'], ValueError, float, None),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            test_list, expected, return_type, slocale  = self.test_lists_equals[l]
            slocale = 'en_US.UTF-8' if not slocale else slocale
            test = ParseNum(return_type, slocale)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected, return_type, slocale  = self.test_list_errors[l]
            slocale = 'en_US.UTF-8' if not slocale else slocale
            self.assertRaises(expected, ParseNum(return_type, slocale).__call__, test_list)


class PurgeCharsTestCase(unittest.TestCase):

    test_lists_equals_clean_punctuation = {
        'single': ('foo.', 'foo', string.punctuation),
        'nothing': ('foobar', 'foobar', string.punctuation),
        'space': ('foobar is great? yes.', 'foobarisgreatyes', string.punctuation + string.whitespace),
        'all': (string.punctuation, '', string.punctuation),
        'unicode': (u'testingš', 'testing', u'š'),
    }

    def test_clean_punctuation(self):
        for l in self.test_lists_equals_clean_punctuation:
            value, expected, chars = self.test_lists_equals_clean_punctuation[l]
            test = purge_chars(value, chars)
            self.assertEqual(test, expected,
                             msg=u'test "{}" got "{}" expected "{}"'.format(l, test, expected))


class StripTestCase(unittest.TestCase):
    test_lists_equals = {
        'simple': (None, 'Friday ', 'Friday'),
        'simple_list': (None, ['Friday ', ' Tuesday'], ['Friday', 'Tuesday']),
        'punctuation': (string.punctuation, ',./hi+_)', 'hi'),
        'punctuation_list': (string.punctuation, [',./hi+_)','=_-Bye-_='], ['hi', 'Bye']),
        'empty': (string.punctuation, '', ''),
        'empty_list_members': (string.punctuation, ['', ''], []),
        'empty_list': (string.punctuation, [], []),
    }
    test_list_errors = {
        'int': (None, 12345, AttributeError),
        'float': (None, 12345.0, AttributeError),
        'int_in_chars': (100, 12345.0, AttributeError),
        'list_in_chars': ([1, 3, 4], 12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            chars, test_list, expected = self.test_lists_equals[l]
            test = Strip(chars)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            chars, test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, Strip(chars).__call__, test_list)


class ReplaceTestCase(unittest.TestCase):
    test_lists_equals = {
        'simple': ('Fri', 'Fries', -1, 'Friday', 'Friesday'),  # count -1 means take all
        'simple_list': ('Fri', 'Frie', -1, ['Friday', 'Fridge'], ['Frieday', 'Friedge']),
        'count': ('a', 'b', 2, ['aacc', 'aaaccc'], ['bbcc', 'bbaccc']),  # count is only 2
    }
    test_list_errors = {
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            find, replace, count, test_list, expected = self.test_lists_equals[l]
            test = Replace(find, replace, count)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            chars, test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, Strip(chars).__call__, test_list)


class ReSubTestCase(unittest.TestCase):
    test_lists_equals = {
        'simple': ('Fri', 'Fries', 0, 0, 'Friday', 'Friesday'),  # no count no flags
        'list': ('Fri', 'Fries', 0, 0, ['Friday', 'Fridge'], ['Friesday', 'Friesdge']),  # no count no flags
        'flag': ('foo', 'bar', 0, re.I, 'FooBar', 'barBar'),  # ignore case flag
        'flag_int': ('foo', 'bar', 0, re.I, 'FooBar', 'barBar'),  # ignore case flag in integer
        'count': ('Foo', 'bar', 1, 0, 'FooFooBar', 'barFooBar'),
    }
    test_list_errors = {
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            find, replace, count, flags, test_list, expected = self.test_lists_equals[l]
            test = ReSub(find, replace, count, flags)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            find, replace, count, flags, test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, ReSub(find, replace, count, flags).__call__, test_list)


class FilterTestCase(unittest.TestCase):
    test_lists_equals = {
        'digits': (str.isdigit, '123456', '123456'),
        'chars': (str.isalpha, '123456', ''),  # empty string when strin expected
        'lambda': (lambda x: x not in string.punctuation, 'only = and ...', 'only  and '),
        'lambda_list': (lambda x: x not in string.punctuation, ['only = and ...', 'one+two=3'], ['only  and ', 'onetwo3']),
    }
    test_list_errors = {
        'int': (12345, AttributeError),
        'float': (12345.0, AttributeError),
    }

    def test_equals(self):
        for l in self.test_lists_equals:
            func, test_list, expected = self.test_lists_equals[l]
            test = Filter(func)(test_list)
            self.assertEqual(test, expected,
                             msg='test "{}" got "{}" expected "{}"'.format(l, test, expected))

    def test_errors(self):
        for l in self.test_list_errors:
            test_list, expected = self.test_list_errors[l]
            self.assertRaises(expected, OnlyChars().__call__, test_list)

if __name__ == "__main__":
    unittest.main()
