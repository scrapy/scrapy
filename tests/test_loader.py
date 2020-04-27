from functools import partial
import unittest

from scrapy.http import HtmlResponse
from scrapy.item import Item, Field
from scrapy.loader import ItemLoader
from scrapy.loader.processors import MapCompose, TakeFirst


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

    def test_add_value_on_unknown_field(self):
        il = TestItemLoader()
        self.assertRaises(KeyError, il.add_value, 'wrong_field', [u'lala', u'lolo'])


class InitializationTestMixin:

    item_class = None

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


class InitializationFromItemTest(InitializationTestMixin, unittest.TestCase):
    item_class = NameItem


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


class NoInputReprocessingItem(Item):
    title = Field()


class NoInputReprocessingItemLoader(BaseNoInputReprocessingLoader):
    default_item_class = NoInputReprocessingItem


class NoInputReprocessingFromItemTest(unittest.TestCase):
    """
    Loaders initialized from loaded items must not reprocess fields (BaseItem instances)
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


class FunctionProcessorDictLoader(ItemLoader):
    default_item_class = dict
    foo_in = function_processor_strip
    foo_out = function_processor_upper


class FunctionProcessorTestCase(unittest.TestCase):

    def test_processor_defined_in_item(self):
        lo = FunctionProcessorItemLoader()
        lo.add_value('foo', '  bar  ')
        lo.add_value('foo', ['  asdf  ', '  qwerty  '])
        self.assertEqual(
            dict(lo.load_item()),
            {'foo': ['BAR', 'ASDF', 'QWERTY']}
        )

    def test_processor_defined_in_item_loader(self):
        lo = FunctionProcessorDictLoader()
        lo.add_value('foo', '  bar  ')
        lo.add_value('foo', ['  asdf  ', '  qwerty  '])
        self.assertEqual(
            dict(lo.load_item()),
            {'foo': ['BAR', 'ASDF', 'QWERTY']}
        )


if __name__ == "__main__":
    unittest.main()
