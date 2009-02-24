
import unittest
from scrapy.contrib_exp.newitem.extractors import adaptor, ItemExtractor


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

