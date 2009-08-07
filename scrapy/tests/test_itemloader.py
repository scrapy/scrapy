import unittest

from scrapy.newitem.loader import Loader
from scrapy.newitem.loader.expanders import TreeExpander, IdentityExpander
from scrapy.newitem.loader.reducers import Join, Identity
from scrapy.newitem import Item, Field

# test items

class NameItem(Item):
    name = Field()

class TestItem(NameItem):
    url = Field()
    summary = Field()

# test loaders

class NameLoader(Loader):
    default_item_class = TestItem

class TestLoader(NameLoader):
    name_exp = TreeExpander(lambda v: v.title())

class DefaultedLoader(NameLoader):
    default_expander = TreeExpander(lambda v: v[:-1])

# test expanders

def expander_func_with_args(value, other=None, loader_args=None):
    if 'key' in loader_args:
        return loader_args['key']
    return value

class Loader(unittest.TestCase):

    def test_get_item_using_default_loader(self):
        i = TestItem()
        i['summary'] = u'lala'
        il = Loader(item=i)
        il.add_value('name', u'marta')
        item = il.get_item()
        assert item is i
        self.assertEqual(item['summary'], u'lala')
        self.assertEqual(item['name'], u'marta')

    def test_get_item_using_custom_loader(self):
        il = TestLoader()
        il.add_value('name', u'marta')
        item = il.get_item()
        self.assertEqual(item['name'], u'Marta')

    def test_add_value(self):
        il = TestLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')
        il.add_value('name', u'pepe')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta', u'Pepe'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

    def test_replace_value(self):
        il = TestLoader()
        il.replace_value('name', u'marta')
        self.assertEqual(il.get_expanded_value('name'), [u'Marta'])
        self.assertEqual(il.get_reduced_value('name'), u'Marta')
        il.replace_value('name', u'pepe')
        self.assertEqual(il.get_expanded_value('name'), [u'Pepe'])
        self.assertEqual(il.get_reduced_value('name'), u'Pepe')

    def test_tree_expander_multiple_functions(self):
        class TestLoader(NameLoader):
            name_exp = TreeExpander(lambda v: v.title(), lambda v: v[:-1])

        il = TestLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Mart')
        item = il.get_item()
        self.assertEqual(item['name'], u'Mart')

    def test_default_expander(self):
        il = DefaultedLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mart')

    def test_inherited_default_expander(self):
        class InheritDefaultedLoader(DefaultedLoader):
            pass

        il = InheritDefaultedLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mart')

    def test_expander_inheritance(self):
        class ChildLoader(TestLoader):
            url_exp = TreeExpander(lambda v: v.lower())

        il = ChildLoader()
        il.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(il.get_reduced_value('url'), u'http://scrapy.org')
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

        class ChildChildLoader(ChildLoader):
            url_exp = TreeExpander(lambda v: v.upper())
            summary_exp = TreeExpander(lambda v: v)

        il = ChildChildLoader()
        il.add_value('url', u'http://scrapy.org')
        self.assertEqual(il.get_reduced_value('url'), u'HTTP://SCRAPY.ORG')
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'Marta')

    def test_empty_tree_expander(self):
        class IdentityDefaultedLoader(DefaultedLoader):
            name_exp = TreeExpander()

        il = IdentityDefaultedLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'marta')

    def test_identity_expander(self):
        class IdentityDefaultedLoader(DefaultedLoader):
            name_exp = IdentityExpander()

        il = IdentityDefaultedLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'marta')

    def test_extend_custom_expanders(self):
        class ChildLoader(TestLoader):
            name_exp = TreeExpander(TestLoader.name_exp, unicode.swapcase)

        il = ChildLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'mARTA')

    def test_extend_default_expanders(self):
        class ChildDefaultedLoader(DefaultedLoader):
            name_exp = TreeExpander(DefaultedLoader.default_expander, unicode.swapcase)

        il = ChildDefaultedLoader()
        il.add_value('name', u'marta')
        self.assertEqual(il.get_reduced_value('name'), u'MART')

    def test_reducer_using_function(self):
        il = TestLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class TakeFirstLoader(TestLoader):
            name_red = u" ".join

        il = TakeFirstLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar Ta')

    def test_reducer_using_classes(self):
        il = TestLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class TakeFirstLoader(TestLoader):
            name_red = Join()

        il = TakeFirstLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar Ta')

        class TakeFirstLoader(TestLoader):
            name_red = Join("<br>")

        il = TakeFirstLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar<br>Ta')

    def test_default_reducer(self):
        il = TestLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), u'Mar')

        class LalaLoader(TestLoader):
            default_reducer = Identity()

        il = LalaLoader()
        il.add_value('name', [u'mar', u'ta'])
        self.assertEqual(il.get_reduced_value('name'), [u'Mar', u'Ta'])

    def test_expander_args_on_declaration(self):
        class ChildLoader(TestLoader):
            url_exp = TreeExpander(expander_func_with_args, key=u'val')

        il = ChildLoader()
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_expander_args_on_instantiation(self):
        class ChildLoader(TestLoader):
            url_exp = TreeExpander(expander_func_with_args)

        il = ChildLoader(key=u'val')
        il.add_value('url', u'text')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_expander_args_on_assign(self):
        class ChildLoadeLoader(TestLoader):
            url_exp = TreeExpander(expander_func_with_args)

        il = ChildLoader()
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'val')

    def test_item_passed_to_expander_functions(self):
        def exp_func(value, loader_args):
            return loader_args['item']['name']

        class ChildLoader(TestLoader):
            url_exp = TreeExpander(exp_func)

        it = TestItem(name='marta')
        il = ChildLoader(item=it)
        il.add_value('url', u'text', key=u'val')
        self.assertEqual(il.get_reduced_value('url'), 'marta')

    def test_add_value_on_unknown_field(self):
        il = TestLoader()
        self.assertRaises(KeyError, il.add_value, 'wrong_field', [u'lala', u'lolo'])

if __name__ == "__main__":
    unittest.main()
