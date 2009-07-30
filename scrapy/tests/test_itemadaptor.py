import unittest
import string
from scrapy.contrib_exp.newitem.adaptors import adaptor, ItemAdaptor
from scrapy.newitem import Item, fields


class BaseItem(Item):
    name = fields.TextField()


class TestItem(BaseItem):
    url = fields.TextField()
    summary = fields.TextField()


class BaseAdaptor(ItemAdaptor):
    item_class = TestItem


class TestAdaptor(BaseAdaptor):
    name = lambda v: v.title()


class DefaultedAdaptor(BaseAdaptor):
    default_adaptor = lambda v: v[:-1]


class InheritDefaultAdaptor(DefaultedAdaptor):
    pass


class MultiValuedTestItem(Item):
    names = fields.MultiValuedField(fields.TextField)


class MultiValuedItemAdaptor(ItemAdaptor):
    item_class = MultiValuedTestItem

    names = adaptor(lambda v: v.title())


class ItemAdaptorTest(unittest.TestCase):

    def test_basic(self):
        ia = TestAdaptor()
        ia.name = u'marta'
        self.assertEqual(ia.item_instance['name'], u'Marta')
        self.assertEqual(ia.name, u'Marta')

    def test_defaultadaptor(self):
        dta = DefaultedAdaptor()
        assert dta.default_adaptor
        dta.name = u'marta'
        self.assertEqual(dta.name, u'mart')

    def test_inheritdefaultadaptor(self):
        ida = InheritDefaultAdaptor()
        ida.name = u'marta'
        assert ida.name == u'mart'

    def test_inheritance(self):
        class ChildTestAdaptor(TestAdaptor):
            url = lambda v: v.lower()

        ia = ChildTestAdaptor()
        assert 'url' in ia._field_adaptors
        assert 'name' in ia._field_adaptors

        ia.url = u'HTTP://scrapy.ORG'
        self.assertEqual(ia.url, u'http://scrapy.org')

        ia.name = u'marta'
        self.assertEqual(ia.name, u'Marta')

        class ChildChildTestAdaptor(ChildTestAdaptor):
            url = lambda v: v.upper()
            summary = lambda v: v

        ia = ChildChildTestAdaptor()
        assert 'url' in ia._field_adaptors
        assert 'name' in ia._field_adaptors
        assert 'summary' in ia._field_adaptors

        ia.url = u'HTTP://scrapy.ORG'
        self.assertEqual(ia.url, u'HTTP://SCRAPY.ORG')

        ia.name = u'marta'
        self.assertEqual(ia.name, u'Marta')

# FIXME: deprecated tests - will be replaced by ItemBuilder tests
#
#    def test_staticmethods(self):
#        class ChildAdaptor(TestAdaptor):
#            name = adaptor(TestAdaptor.name, string.swapcase)
#
#        ia = ChildAdaptor()
#        ia.name = u'Marta'
#        self.assertEqual(ia.name, u'mARTA')
#
#    def test_staticdefaults(self):
#        class ChildAdaptorDefaulted(DefaultedAdaptor):
#            name = adaptor(DefaultedAdaptor.name, string.swapcase)
#
#        dia = ChildAdaptorDefaulted()
#        dia.name = u'marta'
#        self.assertEqual(dia.name, u'MART')

    def test_multiplevaluedadaptor(self):
        ma = MultiValuedItemAdaptor()
        ma.names = [u'name1', u'name2']
        assert ma.names == [u'Name1', u'Name2']


class TreeadaptTest(unittest.TestCase):

    def test_1_passtrough(self):
        ad = adaptor()
        self.assertEqual(ad('string'), ['string'])

    def test_2_composing(self):
        addone = lambda v: v+1
        ad = adaptor(addone)
        self.assertEqual(ad(0), [1])

        addtwo = lambda v: v+2
        ad2 = adaptor(addone, addtwo)
        self.assertEqual(ad2(0), [3])

        ad3 = adaptor(ad, ad2)
        self.assertEqual(ad3(0), [4])

    def test_3_adaptor_args(self):
        addn = lambda v, adaptor_args: v + adaptor_args.get('add_value', 0)

        ad = adaptor(addn)
        self.assertEqual(ad(0), [0])
        self.assertEqual(ad(0, {'add_value': 3}), [3])
        self.assertEqual(ad(0), [0])

        ad = adaptor(addn, add_value=5)
        self.assertEqual(ad(0), [5])
        self.assertEqual(ad(0, {'add_value': 3}), [3])
        self.assertEqual(ad(0), [5])

    def test_4_treelogic(self):
        split1 = lambda v: v.split('&')
        split2 = lambda v: v.split('=')
        ad = adaptor(split1, split2)
        self.assertEqual(ad('name=joe&job=joker'), ['name', 'joe', 'job', 'joker'])

