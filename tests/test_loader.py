import unittest
import six
from functools import partial

from scrapy.loader import ItemLoader
from scrapy.loader.processors import Join, Identity, TakeFirst, \
    Compose, MapCompose, SelectJmes
from scrapy.item import Item, Field
from scrapy.selector import Selector
from scrapy.http import HtmlResponse

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

    def test_self_referencing_loader(self):
        class MyLoader(ItemLoader):
            url_out = TakeFirst()

            def img_url_out(self, values):
                return (self.get_output_value('url') or '') + values[0]

        il = MyLoader(item={})
        il.add_value('url', 'http://example.com/')
        il.add_value('img_url', '1234.png')
        self.assertEqual(il.load_item(), {
            'url': 'http://example.com/',
            'img_url': 'http://example.com/1234.png',
        })

        il = MyLoader(item={})
        il.add_value('img_url', '1234.png')
        self.assertEqual(il.load_item(), {
            'img_url': '1234.png',
        })

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
        self.assertEqual(u'FOO', il.get_value([u'foo', u'bar'], TakeFirst(), six.text_type.upper))
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
            name_in = MapCompose(TestItemLoader.name_in, six.text_type.swapcase)

        il = ChildItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_output_value('name'), [u'mARTA'])

    def test_extend_default_input_processors(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            name_in = MapCompose(DefaultedItemLoader.default_input_processor, six.text_type.swapcase)

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
        self.assert_(isinstance(proc(['hello', 'world']), six.text_type))

    def test_compose(self):
        proc = Compose(lambda v: v[0], str.upper)
        self.assertEqual(proc(['hello', 'world']), 'HELLO')
        proc = Compose(str.upper)
        self.assertEqual(proc(None), None)
        proc = Compose(str.upper, stop_on_none=False)
        self.assertRaises(TypeError, proc, None)

    def test_mapcompose(self):
        filter_world = lambda x: None if x == 'world' else x
        proc = MapCompose(filter_world, six.text_type.upper)
        self.assertEqual(proc([u'hello', u'world', u'this', u'is', u'scrapy']),
                         [u'HELLO', u'THIS', u'IS', u'SCRAPY'])


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
        nl.add_value('name_value', nl.selector.xpath('div[@id = "id"]/text()').extract())

        self.assertEqual(l.get_output_value('name'), [u'marta'])
        self.assertEqual(l.get_output_value('name_div'), [u'<div id="id">marta</div>'])
        self.assertEqual(l.get_output_value('name_value'),  [u'marta'])

        self.assertEqual(l.get_output_value('name'), nl.get_output_value('name'))
        self.assertEqual(l.get_output_value('name_div'), nl.get_output_value('name_div'))
        self.assertEqual(l.get_output_value('name_value'), nl.get_output_value('name_value'))

    def test_nested_css(self):
        l = NestedItemLoader(response=self.response)
        nl = l.nested_css("header")
        nl.add_xpath('name', 'div/text()')
        nl.add_css('name_div', '#id')
        nl.add_value('name_value', nl.selector.xpath('div[@id = "id"]/text()').extract())

        self.assertEqual(l.get_output_value('name'), [u'marta'])
        self.assertEqual(l.get_output_value('name_div'), [u'<div id="id">marta</div>'])
        self.assertEqual(l.get_output_value('name_value'),  [u'marta'])

        self.assertEqual(l.get_output_value('name'), nl.get_output_value('name'))
        self.assertEqual(l.get_output_value('name_div'), nl.get_output_value('name_div'))
        self.assertEqual(l.get_output_value('name_value'), nl.get_output_value('name_value'))

    def test_nested_replace(self):
        l = NestedItemLoader(response=self.response)
        nl1 = l.nested_xpath('//footer')
        nl2 = nl1.nested_xpath('a')

        l.add_xpath('url', '//footer/a/@href')
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org'])
        nl1.replace_xpath('url', 'img/@src')
        self.assertEqual(l.get_output_value('url'), [u'/images/logo.png'])
        nl2.replace_xpath('url', '@href')
        self.assertEqual(l.get_output_value('url'), [u'http://www.scrapy.org'])

    def test_nested_ordering(self):
        l = NestedItemLoader(response=self.response)
        nl1 = l.nested_xpath('//footer')
        nl2 = nl1.nested_xpath('a')

        nl1.add_xpath('url', 'img/@src')
        l.add_xpath('url', '//footer/a/@href')
        nl2.add_xpath('url', 'text()')
        l.add_xpath('url', '//footer/a/@href')

        self.assertEqual(l.get_output_value('url'), [
            u'/images/logo.png',
            u'http://www.scrapy.org',
            u'homepage',
            u'http://www.scrapy.org',
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

        self.assertEqual(item['name'], [u'marta'])
        self.assertEqual(item['url'], [u'http://www.scrapy.org'])
        self.assertEqual(item['image'], [u'/images/logo.png'])


class SelectJmesTestCase(unittest.TestCase):
        test_list_equals = {
            'simple': ('foo.bar', {"foo": {"bar": "baz"}}, "baz"),
            'invalid': ('foo.bar.baz', {"foo": {"bar": "baz"}}, None),
            'top_level': ('foo', {"foo": {"bar": "baz"}}, {"bar": "baz"}),
            'double_vs_single_quote_string': ('foo.bar', {"foo": {"bar": "baz"}}, "baz"),
            'dict': (
                'foo.bar[*].name',
                {"foo": {"bar": [{"name": "one"}, {"name": "two"}]}},
                ['one', 'two']
            ),
            'list': ('[1]', [1, 2], 2)
        }

        def test_output(self):
            for l in self.test_list_equals:
                expr, test_list, expected = self.test_list_equals[l]
                test = SelectJmes(expr)(test_list)
                self.assertEqual(
                    test,
                    expected,
                    msg='test "{}" got {} expected {}'.format(l, test, expected)
                )


if __name__ == "__main__":
    unittest.main()
