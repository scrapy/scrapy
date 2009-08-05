import unittest

from scrapy.newitem.loader import ItemLoader
from scrapy.newitem.loader.expanders import TreeExpander, IdentityExpander
from scrapy.newitem.loader.reducers import JoinStrings, Identity
from scrapy.newitem import Item, Field

# test items

class NameItem(Item):
    name = Field()

class TestItem(NameItem):
    url = Field()
    summary = Field()

# test loaders

class NameItemLoader(ItemLoader):
    default_item_class = TestItem

class TestItemLoader(NameItemLoader):
    name_exp = TreeExpander(lambda v: v.title())

class DefaultedItemLoader(NameItemLoader):
    default_expander = TreeExpander(lambda v: v[:-1])

# test expanders

def expander_func_with_args(value, other=None, loader_args=None):
    if 'key' in loader_args:
        return loader_args['key']
    return value

class ItemLoaderTest(unittest.TestCase):

    def test_get_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = u'lala'
        il = ItemLoader(item=i)
        il.add_value('name', u'marta')
        item = il.get_item()
        assert item is i
        self.assertEqual(item['summary'], u'lala')
        self.assertEqual(item['name'], u'marta')

    def test_get_item_using_custom_loader(self):
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

    def test_tree_expander_multiple_functions(self):
        class TestItemLoader(NameItemLoader):
            name_exp = TreeExpander(lambda v: v.title(), lambda v: v[:-1])

        il = TestItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Mart')
        item = il.get_item()
        self.assertEqual(item['name'], u'Mart')

    def test_default_expander(self):
        il = DefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mart')

    def test_inherited_default_expander(self):
        class InheritDefaultedItemLoader(DefaultedItemLoader):
            pass

        il = InheritDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mart')

    def test_expander_inheritance(self):
        class ChildItemLoader(TestItemLoader):
            url_exp = TreeExpander(lambda v: v.lower())

        il = ChildItemLoader()
        il.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(il.get_reduced_value('url'), u'http://scrapy.org')
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

        class ChildChildItemLoader(ChildItemLoader):
            url_exp = TreeExpander(lambda v: v.upper())
            summary_exp = TreeExpander(lambda v: v)

        il = ChildChildItemLoader()
        il.add_value('url', u'http://scrapy.org')
        self.assertEqual(il.get_reduced_value('url'), u'HTTP://SCRAPY.ORG')
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

    def test_empty_tree_expander(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_exp = TreeExpander()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'marta')

    def test_identity_expander(self):
        class IdentityDefaultedItemLoader(DefaultedItemLoader):
            name_exp = IdentityExpander()

        il = IdentityDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'marta')

    def test_extend_custom_expanders(self):
        class ChildItemLoader(TestItemLoader):
            name_exp = TreeExpander(TestItemLoader.name_exp, unicode.swapcase)

        il = ChildItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mARTA')

    def test_extend_default_expanders(self):
        class ChildDefaultedItemLoader(DefaultedItemLoader):
            name_exp = TreeExpander(DefaultedItemLoader.default_expander, unicode.swapcase)

        il = ChildDefaultedItemLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'MART')

    def test_reducer_using_function(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class TakeFirstItemLoader(TestItemLoader):
            name_red = u" ".join

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar Ta')

    def test_reducer_using_classes(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class TakeFirstItemLoader(TestItemLoader):
            name_red = JoinStrings()

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar Ta')

        class TakeFirstItemLoader(TestItemLoader):
            name_red = JoinStrings("<br>")

        il = TakeFirstItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar<br>Ta')

    def test_default_reducer(self):
        il = TestItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class LalaItemLoader(TestItemLoader):
            default_reducer = Identity()

        il = LalaItemLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), [u'Mar', u'Ta'])

    def test_expander_args_on_declaration(self):
        class ChildItemLoader(TestItemLoader):
            url_exp = TreeExpander(expander_func_with_args, key=u'val')

        il = ChildItemLoader()
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_expander_args_on_instantiation(self):
        class ChildItemLoader(TestItemLoader):
            url_exp = TreeExpander(expander_func_with_args)

        il = ChildItemLoader(key=u'val')
        il.add_value('url', u'text')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_expander_args_on_assign(self):
        class ChildItemLoader(TestItemLoader):
            url_exp = TreeExpander(expander_func_with_args)

        il = ChildItemLoader()
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_item_passed_to_expander_functions(self):
        def exp_func(value, loader_args):
            return loader_args['item']['name']

        class ChildItemLoader(TestItemLoader):
            url_exp = TreeExpander(exp_func)

        it = TestItem(name='marta')
        il = ChildItemLoader(item=it)
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'marta')

    def test_add_value_on_unknown_field(self):
        il = TestItemLoader()
        self.assertRaises(KeyError, il.add_value, 'wrong_field', [u'lala', u'lolo'])

if __name__ == "__main__":
    unittest.main()
