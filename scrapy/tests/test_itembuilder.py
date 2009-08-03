import unittest
import string
from scrapy.newitem.builder import ItemBuilder, BuilderField
from scrapy.newitem.builder import reducers
from scrapy.newitem import Item, fields


class BaseItem(Item):
    name = fields.TextField()


class TestItem(BaseItem):
    url = fields.TextField()
    summary = fields.TextField()


class BaseItemBuilder(ItemBuilder):
    item_class = TestItem


class TestItemBuilder(BaseItemBuilder):
    name = BuilderField(lambda v: v.title())


class DefaultedItemBuilder(BaseItemBuilder):
    default_builder = BuilderField(lambda v: v[:-1])
    

class InheritDefaultedItemBuilder(DefaultedItemBuilder):
    pass


class ListFieldTestItem(Item):
    names = fields.ListField(fields.TextField())


class ListFieldItemBuilder(ItemBuilder):
    item_class = ListFieldTestItem

    names = BuilderField(lambda v: v.title())


class ItemBuilderTest(unittest.TestCase):

    def test_basic(self):
        ib = TestItemBuilder()

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'Marta')

        item = ib.get_item()
        self.assertEqual(item['name'], u'Marta')

    def test_multiple_functions(self):
        class TestItemBuilder(BaseItemBuilder):
            name = BuilderField(lambda v: v.title(), lambda v: v[:-1])

        ib = TestItemBuilder()
        
        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'Mart')

        item = ib.get_item()
        self.assertEqual(item['name'], u'Mart')

    def test_defaulted(self):
        dib = DefaultedItemBuilder()
        assert dib.default_builder

        dib.add_value('name', u'marta')
        self.assertEqual(dib.get_value('name'), u'mart')

    def test_inherited_default(self):
        dib = InheritDefaultedItemBuilder()
        assert dib.default_builder

        dib.add_value('name', u'marta')
        self.assertEqual(dib.get_value('name'), u'mart')

    def test_inheritance(self):
        class ChildItemBuilder(TestItemBuilder):
            url = BuilderField(lambda v: v.lower())

        ib = ChildItemBuilder()
        assert 'url' in ib._builder_fields
        assert 'name' in ib._builder_fields

        ib.add_value('url', u'HTTP://scrapy.ORG')
        self.assertEqual(ib.get_value('url'), u'http://scrapy.org')

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'Marta')

        class ChildChildItemBuilder(ChildItemBuilder):
            url = BuilderField(lambda v: v.upper())
            summary = BuilderField(lambda v: v)

        ib = ChildChildItemBuilder()
        assert 'url' in ib._builder_fields
        assert 'name' in ib._builder_fields
        assert 'summary' in ib._builder_fields

        ib.add_value('url', u'http://scrapy.org')
        self.assertEqual(ib.get_value('url'), u'HTTP://SCRAPY.ORG')

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'Marta')

    def test_multiplevaluedadaptor(self):
        ib = ListFieldItemBuilder()

        ib.add_value('names',  [u'name1', u'name2'])
        self.assertEqual(ib.get_value('names'), [u'Name1', u'Name2'])

    def test_identity(self):
        class IdentityDefaultedItemBuilder(DefaultedItemBuilder):
            name = BuilderField()

        ib = IdentityDefaultedItemBuilder()

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'marta')

    def test_staticmethods(self):
        class ChildItemBuilder(TestItemBuilder):
            name = BuilderField(TestItemBuilder.name.expander, string.swapcase)

        ib = ChildItemBuilder()

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'mARTA')


    def test_staticdefaults(self):
        class ChildDefaultedItemBuilder(DefaultedItemBuilder):
            name = BuilderField(DefaultedItemBuilder.name.expander, string.swapcase)

        ib = ChildDefaultedItemBuilder()

        ib.add_value('name', u'marta')
        self.assertEqual(ib.get_value('name'), u'MART')

    def test_reducer(self):
        ib = TestItemBuilder()

        ib.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ib.get_value('name'), u'Mar Ta')

        class TakeFirstItemBuilder(TestItemBuilder):
            name = BuilderField(TestItemBuilder.name.expander,
                                reducer=reducers.take_first)

        ib = TakeFirstItemBuilder()

        ib.add_value('name', [u'mar', u'ta'])
        self.assertEqual(ib.get_value('name'), u'Mar')

    def test_expander_args(self):
        def expander_with_args(value, expander_args=None):
            if 'val' in expander_args:
                return expander_args['val']
            return value

        class ChildItemBuilder(TestItemBuilder):
            url = BuilderField(expander_with_args)

        ib = ChildItemBuilder(val=u'val')
        ib.add_value('url', u'text')
        self.assertEqual(ib.get_value('url'), 'val')

        ib = ChildItemBuilder()
        ib.add_value('url', u'text', val=u'val')
        self.assertEqual(ib.get_value('url'), 'val')

