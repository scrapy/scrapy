"""
These tests are kept as references from the ones that were ported to a itemloaders library.
Once we remove the references from scrapy, we can remove these tests.
"""

import unittest
import warnings
from functools import partial

from itemloaders.processors import (Compose, Identity, Join,
                                    MapCompose, SelectJmes, TakeFirst)

from scrapy.item import Item, Field
from scrapy.loader import ItemLoader
from scrapy.loader.common import wrap_loader_context
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.misc import extract_regex


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

    def test_load_item_ignore_none_field_values(self):
        def validate_sku(value):
            # Let's assume a SKU is only digits.
            if value.isdigit():
                return value

        class MyLoader(ItemLoader):
            name_out = Compose(lambda vs: vs[0])  # take first which allows empty values
            price_out = Compose(TakeFirst(), float)
            sku_out = Compose(TakeFirst(), validate_sku)

        valid_fragment = 'SKU: 1234'
        invalid_fragment = 'SKU: not available'
        sku_re = 'SKU: (.+)'

        il = MyLoader(item={})
        # Should not return "sku: None".
        il.add_value('sku', [invalid_fragment], re=sku_re)
        # Should not ignore empty values.
        il.add_value('name', '')
        il.add_value('price', ['0'])
        self.assertEqual(il.load_item(), {
            'name': '',
            'price': 0.0,
        })

        il.replace_value('sku', [valid_fragment], re=sku_re)
        self.assertEqual(il.load_item()['sku'], '1234')

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
        il.add_value('name', 'marta')
        self.assertEqual(il.get_collected_values('name'), ['Marta'])
        self.assertEqual(il.get_output_value('name'), ['Marta'])
        il.add_value('name', 'pepe')
        self.assertEqual(il.get_collected_values('name'), ['Marta', 'Pepe'])
        self.assertEqual(il.get_output_value('name'), ['Marta', 'Pepe'])

        # test add object value
        il.add_value('summary', {'key': 1})
        self.assertEqual(il.get_collected_values('summary'), [{'key': 1}])

        il.add_value(None, 'Jim', lambda x: {'name': x})
        self.assertEqual(il.get_collected_values('name'), ['Marta', 'Pepe', 'Jim'])

    def test_add_zero(self):
        il = NameItemLoader()
        il.add_value('name', 0)
        self.assertEqual(il.get_collected_values('name'), [0])

    def test_replace_value(self):
        il = TestItemLoader()
        il.replace_value('name', 'marta')
        self.assertEqual(il.get_collected_values('name'), ['Marta'])
        self.assertEqual(il.get_output_value('name'), ['Marta'])
        il.replace_value('name', 'pepe')
        self.assertEqual(il.get_collected_values('name'), ['Pepe'])
        self.assertEqual(il.get_output_value('name'), ['Pepe'])

        il.replace_value(None, 'Jim', lambda x: {'name': x})
        self.assertEqual(il.get_collected_values('name'), ['Jim'])

    def test_get_value(self):
        il = NameItemLoader()
        self.assertEqual('FOO', il.get_value(['foo', 'bar'], TakeFirst(), str.upper))
        self.assertEqual(['foo', 'bar'], il.get_value(['name:foo', 'name:bar'], re='name:(.*)$'))
        self.assertEqual('foo', il.get_value(['name:foo', 'name:bar'], TakeFirst(), re='name:(.*)$'))

        il.add_value('name', ['name:foo', 'name:bar'], TakeFirst(), re='name:(.*)$')
        self.assertEqual(['foo'], il.get_collected_values('name'))
        il.replace_value('name', 'name:bar', re='name:(.*)$')
        self.assertEqual(['bar'], il.get_collected_values('name'))

    def test_iter_on_input_processor_input(self):
        class NameFirstItemLoader(NameItemLoader):
            name_in = TakeFirst()

        il = NameFirstItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_collected_values('name'), ['marta'])
        il = NameFirstItemLoader()
        il.add_value('name', ['marta', 'jose'])
        self.assertEqual(il.get_collected_values('name'), ['marta'])

        il = NameFirstItemLoader()
        il.replace_value('name', 'marta')
        self.assertEqual(il.get_collected_values('name'), ['marta'])
        il = NameFirstItemLoader()
        il.replace_value('name', ['marta', 'jose'])
        self.assertEqual(il.get_collected_values('name'), ['marta'])

        il = NameFirstItemLoader()
        il.add_value('name', 'marta')
        il.add_value('name', ['jose', 'pedro'])
        self.assertEqual(il.get_collected_values('name'), ['marta', 'jose'])

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
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['Mart'])
        item = il.load_item()
        self.assertEqual(item['name'], ['Mart'])

    def test_default_input_processor(self):
        il = DefaultedItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['mart'])

    def test_inherited_default_input_processor(self):
        class InheritDefaultedItemLoader(DefaultedItemLoader):
            pass

        il = InheritDefaultedItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['mart'])

    def test_input_processor_inheritance(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(lambda v: v.lower())

        il = ChildItemLoader()
        il.add_value('url', 'HTTP://scrapy.ORG')
        self.assertEqual(il.get_output_value('url'), ['http://scrapy.org'])
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['Marta'])

        class ChildChildItemLoader(ChildItemLoader):
            url_in = MapCompose(lambda v: v.upper())
            summary_in = MapCompose(lambda v: v)

        il = ChildChildItemLoader()
        il.add_value('url', 'http://scrapy.org')
        self.assertEqual(il.get_output_value('url'), ['HTTP://SCRAPY.ORG'])
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['Marta'])

    def test_empty_map_compose(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = MapCompose()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['marta'])

    def test_identity_input_processor(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_in = Identity()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['marta'])

    def test_extend_custom_input_processors(self):
        class ChildItemLoader(TestItemLoader):
            name_in = MapCompose(TestItemLoader.name_in, str.swapcase)

        il = ChildItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['mARTA'])

    def test_extend_default_input_processors(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            name_in = MapCompose(DefaultedItemLoader.default_input_processor, str.swapcase)

        il = ChildDefaultedItemLoader()
        il.add_value('name', 'marta')
        self.assertEqual(il.get_output_value('name'), ['MART'])

    def test_output_processor_using_function(self):
        il = TestItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), ['Mar', 'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = " ".join

        il = TakeFirstItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), 'Mar Ta')

    def test_output_processor_error(self):
        class TestItemLoader(ItemLoader):
            default_item_class = TestItem
            name_out = MapCompose(float)

        il = TestItemLoader()
        il.add_value('name', ['$10'])
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
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), ['Mar', 'Ta'])

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join()

        il = TakeFirstItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), 'Mar Ta')

        class TakeFirstItemLoader(TestItemLoader):
            name_out = Join("<br>")

        il = TakeFirstItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), 'Mar<br>Ta')

    def test_default_output_processor(self):
        il = TestItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), ['Mar', 'Ta'])

        class LalaItemLoader(TestItemLoader):
            default_output_processor = Identity()

        il = LalaItemLoader()
        il.add_value('name', ['mar', 'ta'])
        self.assertEqual(il.get_output_value('name'), ['Mar', 'Ta'])

    def test_loader_context_on_declaration(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args, key='val')

        il = ChildItemLoader()
        il.add_value('url', 'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', 'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_loader_context_on_instantiation(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args)

        il = ChildItemLoader(key='val')
        il.add_value('url', 'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', 'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_loader_context_on_assign(self):
        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor_with_args)

        il = ChildItemLoader()
        il.context['key'] = 'val'
        il.add_value('url', 'text')
        self.assertEqual(il.get_output_value('url'), ['val'])
        il.replace_value('url', 'text2')
        self.assertEqual(il.get_output_value('url'), ['val'])

    def test_item_passed_to_input_processor_functions(self):
        def processor(value, loader_context):
            return loader_context['item']['name']

        class ChildItemLoader(TestItemLoader):
            url_in = MapCompose(processor)

        it = TestItem(name='marta')
        il = ChildItemLoader(item=it)
        il.add_value('url', 'text')
        self.assertEqual(il.get_output_value('url'), ['marta'])
        il.replace_value('url', 'text2')
        self.assertEqual(il.get_output_value('url'), ['marta'])

    def test_compose_processor(self):
        class TestItemLoader(NameItemLoader):
            name_out = Compose(lambda v: v[0], lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()
        il.add_value('name', ['marta', 'other'])
        self.assertEqual(il.get_output_value('name'), 'Mart')
        item = il.load_item()
        self.assertEqual(item['name'], 'Mart')

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
        il.add_value('name', ['rabbit', 'hole'])
        il.add_value('url', ['rabbit', 'hole'])
        il.add_value('summary', ['rabbit', 'hole'])
        item = il.load_item()
        self.assertEqual(item['name'], 'rabbit+hole')
        self.assertEqual(item['url'], 'rabbit.hole')
        self.assertEqual(item['summary'], 'rabbithole')

    def test_error_input_processor(self):
        class TestItem(Item):
            name = Field()

        class TestItemLoader(ItemLoader):
            default_item_class = TestItem
            name_in = MapCompose(float)

        il = TestItemLoader()
        self.assertRaises(ValueError, il.add_value, 'name',
                          ['marta', 'other'])

    def test_error_output_processor(self):
        class TestItem(Item):
            name = Field()

        class TestItemLoader(ItemLoader):
            default_item_class = TestItem
            name_out = Compose(Join(), float)

        il = TestItemLoader()
        il.add_value('name', 'marta')
        with self.assertRaises(ValueError):
            il.load_item()

    def test_error_processor_as_argument(self):
        class TestItem(Item):
            name = Field()

        class TestItemLoader(ItemLoader):
            default_item_class = TestItem

        il = TestItemLoader()
        self.assertRaises(ValueError, il.add_value, 'name',
                          ['marta', 'other'], Compose(float))


class InitializationFromDictTest(unittest.TestCase):

    item_class = dict

    def test_keep_single_value(self):
        """Loaded item should contain values from the initial item"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo']})

    def test_keep_list(self):
        """Loaded item should contain values from the initial item"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo', 'bar']})

    def test_add_value_singlevalue_singlevalue(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        il.add_value('name', 'bar')
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo', 'bar']})

    def test_add_value_singlevalue_list(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        il.add_value('name', ['item', 'loader'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo', 'item', 'loader']})

    def test_add_value_list_singlevalue(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        il.add_value('name', 'qwerty')
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo', 'bar', 'qwerty']})

    def test_add_value_list_list(self):
        """Values added after initialization should be appended"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        il.add_value('name', ['item', 'loader'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(dict(loaded_item), {'name': ['foo', 'bar', 'item', 'loader']})

    def test_get_output_value_singlevalue(self):
        """Getting output value must not remove value from item"""
        input_item = self.item_class(name='foo')
        il = ItemLoader(item=input_item)
        self.assertEqual(il.get_output_value('name'), ['foo'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(loaded_item, dict({'name': ['foo']}))

    def test_get_output_value_list(self):
        """Getting output value must not remove value from item"""
        input_item = self.item_class(name=['foo', 'bar'])
        il = ItemLoader(item=input_item)
        self.assertEqual(il.get_output_value('name'), ['foo', 'bar'])
        loaded_item = il.load_item()
        self.assertIsInstance(loaded_item, self.item_class)
        self.assertEqual(loaded_item, dict({'name': ['foo', 'bar']}))

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


class BaseNoInputReprocessingLoader(ItemLoader):
    title_in = MapCompose(str.upper)
    title_out = TakeFirst()


class NoInputReprocessingDictLoader(BaseNoInputReprocessingLoader):
    default_item_class = dict


class NoInputReprocessingFromDictTest(unittest.TestCase):
    """
    Loaders initialized from loaded items must not reprocess fields (dict instances)
    """
    def test_avoid_reprocessing_with_initial_values_single(self):
        il = NoInputReprocessingDictLoader(item=dict(title='foo'))
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, dict(title='foo'))
        self.assertEqual(NoInputReprocessingDictLoader(item=il_loaded).load_item(), dict(title='foo'))

    def test_avoid_reprocessing_with_initial_values_list(self):
        il = NoInputReprocessingDictLoader(item=dict(title=['foo', 'bar']))
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, dict(title='foo'))
        self.assertEqual(NoInputReprocessingDictLoader(item=il_loaded).load_item(), dict(title='foo'))

    def test_avoid_reprocessing_without_initial_values_single(self):
        il = NoInputReprocessingDictLoader()
        il.add_value('title', 'foo')
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, dict(title='FOO'))
        self.assertEqual(NoInputReprocessingDictLoader(item=il_loaded).load_item(), dict(title='FOO'))

    def test_avoid_reprocessing_without_initial_values_list(self):
        il = NoInputReprocessingDictLoader()
        il.add_value('title', ['foo', 'bar'])
        il_loaded = il.load_item()
        self.assertEqual(il_loaded, dict(title='FOO'))
        self.assertEqual(NoInputReprocessingDictLoader(item=il_loaded).load_item(), dict(title='FOO'))


class TestOutputProcessorDict(unittest.TestCase):
    def test_output_processor(self):

        class TempDict(dict):
            def __init__(self, *args, **kwargs):
                super(TempDict, self).__init__(self, *args, **kwargs)
                self.setdefault('temp', 0.3)

        class TempLoader(ItemLoader):
            default_item_class = TempDict
            default_input_processor = Identity()
            default_output_processor = Compose(TakeFirst())

        loader = TempLoader()
        item = loader.load_item()
        self.assertIsInstance(item, TempDict)
        self.assertEqual(dict(item), {'temp': 0.3})


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
        self.assertEqual(proc(['', 'hello', 'world']), ' hello world')
        self.assertEqual(proc(['hello', 'world']), 'hello world')
        self.assertIsInstance(proc(['hello', 'world']), str)

    def test_compose(self):
        proc = Compose(lambda v: v[0], str.upper)
        self.assertEqual(proc(['hello', 'world']), 'HELLO')
        proc = Compose(str.upper)
        self.assertEqual(proc(None), None)
        proc = Compose(str.upper, stop_on_none=False)
        self.assertRaises(ValueError, proc, None)
        proc = Compose(str.upper, lambda x: x + 1)
        self.assertRaises(ValueError, proc, 'hello')

    def test_mapcompose(self):
        def filter_world(x):
            return None if x == 'world' else x
        proc = MapCompose(filter_world, str.upper)
        self.assertEqual(proc(['hello', 'world', 'this', 'is', 'scrapy']),
                         ['HELLO', 'THIS', 'IS', 'SCRAPY'])
        proc = MapCompose(filter_world, str.upper)
        self.assertEqual(proc(None), [])
        proc = MapCompose(filter_world, str.upper)
        self.assertRaises(ValueError, proc, [1])
        proc = MapCompose(filter_world, lambda x: x + 1)
        self.assertRaises(ValueError, proc, 'hello')


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
        for tl in self.test_list_equals:
            expr, test_list, expected = self.test_list_equals[tl]
            test = SelectJmes(expr)(test_list)
            self.assertEqual(
                test,
                expected,
                msg='test "{}" got {} expected {}'.format(tl, test, expected)
            )


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


class FunctionProcessorDictLoader(ItemLoader):
    default_item_class = dict
    foo_in = function_processor_strip
    foo_out = function_processor_upper


class FunctionProcessorTestCase(unittest.TestCase):

    def test_processor_defined_in_item_loader(self):
        lo = FunctionProcessorDictLoader()
        lo.add_value('foo', '  bar  ')
        lo.add_value('foo', ['  asdf  ', '  qwerty  '])
        self.assertEqual(
            dict(lo.load_item()),
            {'foo': ['BAR', 'ASDF', 'QWERTY']}
        )


class DeprecatedUtilityFunctionsTestCase(unittest.TestCase):

    def test_deprecated_wrap_loader_context(self):
        def function(*args):
            return None

        with warnings.catch_warnings(record=True) as w:
            wrap_loader_context(function, context=dict())

            assert len(w) == 1
            assert issubclass(w[0].category, ScrapyDeprecationWarning)

    def test_deprecated_extract_regex(self):
        with warnings.catch_warnings(record=True) as w:
            extract_regex(r'\w+', 'this is a test')

            assert len(w) == 1
            assert issubclass(w[0].category, ScrapyDeprecationWarning)


if __name__ == "__main__":
    unittest.main()
