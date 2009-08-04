import unittest

from scrapy.newitem.loader import ItemLoader
from scrapy.newitem.loader.expanders import tree_expander
from scrapy.newitem import Item, Field


class BaseItem(Item):
    name = Field()


class TestItem(BaseItem):
    url = Field()
    summary = Field()


class BaseItemLoader(ItemLoader):
    item_class = TestItem


class TestItemLoader(BaseItemLoader):
    expand_name = tree_expander(lambda v: v.title())


class DefaultedItemLoader(BaseItemLoader):
    expand = tree_expander(lambda v: v[:-1])


class InheritDefaultedItemLoader(DefaultedItemLoader):
    pass


class ItemLoaderTest(unittest.TestCase):

    def test_get_item(self):
        il = TestItemLoader()

        il.add_value('name', u'marta')
        item = il.get_item()
        self.assertEqual(item['name'], u'Marta')

    def test_add_value(self):
        il = TestItemLoader()

        il.add_value('name', u'marta')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

        il.add_value('name', u'pepe')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta', u'Pepe'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

    def test_replace_value(self):
        il = TestItemLoader()

        il.replace_value('name', u'marta')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

        il.replace_value('name', u'pepe')
        self.assertEqual(il.get_expanded_value('name'), [u'Pepe'])
        self.assertEqual(il.get_reduced_value('name'), u'Pepe')

    def test_multiple_functions(self):
        class TestItemLoader(BaseItemLoader):
            expand_name = tree_expander(lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Mart')

        item = il.get_item()
        self.assertEqual(item['name'], u'Mart')

    def test_defaulted(self):
        dil = DefaultedItemLoader()

        dil.add_value('name', u'marta')
        self.assertEqual(dil.get_reduced_value('name'), u'mart')

    def test_inherited_default(self):
        dil = InheritDefaultedItemLoader()

        dil.add_value('name', u'marta')
        self.assertEqual(dil.get_reduced_value('name'), u'mart')

    def test_inheritance(self):
        class ChildItemLoader(TestItemLoader):
            expand_url = tree_expander(lambda v: v.lower())

        il = ChildItemLoader()

        il.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(il.get_reduced_value('url'), u'http://scrapy.org')

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

        class ChildChildItemLoader(ChildItemLoader):
            expand_url = tree_expander(lambda v: v.upper())
            expand_summary = tree_expander(lambda v: v)

        il = ChildChildItemLoader()

        il.add_value('url', u'http://scrapy.org')
        self.assertEqual(il.get_reduced_value('url'), u'HTTP://SCRAPY.ORG')

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

    def test_identity(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            expand_name = tree_expander()

        il = IdentityDefaultedItemLoader()

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'marta')

    def test_staticmethods(self):
        class ChildItemLoader(TestItemLoader):
            expand_name = tree_expander(TestItemLoader.expand_name, unicode.swapcase)

        il = ChildItemLoader()

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mARTA')


    def test_staticdefaults(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            expand_name = tree_expander(DefaultedItemLoader.expand, unicode.swapcase)

        il = ChildDefaultedItemLoader()

        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'MART')

    def test_reducer(self):
        il = TestItemLoader()

        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class TakeFirstItemLoader(TestItemLoader):
            reduce_name = staticmethod(u" ".join)

        il = TakeFirstItemLoader()

        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar Ta')

    def test_loader_args(self):
        def expander_func_with_args(value, loader_args):
            if 'val' in loader_args:
                return loader_args['val']
            return value

        class ChildItemLoader(TestItemLoader):
            expand_url = tree_expander(expander_func_with_args)

        il = ChildItemLoader(val=u'val')
        il.add_value('url', u'text')
        self.assertEqual(il.get_reduced_value('url'), 'val')

        il = ChildItemLoader()
        il.add_value('url', u'text', val=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_add_value_unknown_field(self):
        il = TestItemLoader()
        il.add_value('wrong_field', [u'lala', u'lolo'])

        self.assertRaises(KeyError, il.get_item)
