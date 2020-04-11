# -*- coding: utf-8 -*-
import unittest

from scrapy.item import BaseItem, Field, Item
from scrapy.utils.item import _is_dataclass_instance, is_item_like, ItemAdapter


try:
    from dataclasses import make_dataclass, field
except ImportError:
    DataClassItem = None
else:
    DataClassItem = make_dataclass(
        "DataClassItem",
        [
            ("name", str, field(default_factory=lambda: None)),
            ("value", int, field(default_factory=lambda: None)),
        ],
    )


class TestItem(Item):
    name = Field()
    value = Field()


class DataclassTestCase(unittest.TestCase):

    def test_false_always(self):
        """These objects should return False whether or not the dataclasses module is available"""
        self.assertFalse(_is_dataclass_instance(int))
        self.assertFalse(_is_dataclass_instance(sum))
        self.assertFalse(_is_dataclass_instance(1234))
        self.assertFalse(_is_dataclass_instance(object()))
        self.assertFalse(_is_dataclass_instance(Item()))
        self.assertFalse(_is_dataclass_instance(TestItem()))
        self.assertFalse(_is_dataclass_instance("a string"))
        self.assertFalse(_is_dataclass_instance(b"some bytes"))
        self.assertFalse(_is_dataclass_instance({"a": "dict"}))
        self.assertFalse(_is_dataclass_instance(["a", "list"]))
        self.assertFalse(_is_dataclass_instance(("a", "tuple")))
        self.assertFalse(_is_dataclass_instance({"a", "set"}))

    @unittest.skipIf(not DataClassItem, "dataclasses module is not available")
    def test_false_only_if_installed(self):
        self.assertFalse(_is_dataclass_instance(DataClassItem))

    @unittest.skipIf(not DataClassItem, "dataclasses module is not available")
    def test_true_only_if_installed(self):
        self.assertTrue(_is_dataclass_instance(DataClassItem(name="asdf", value=1234)))


class ItemLikeTestCase(unittest.TestCase):

    def test_false(self):
        self.assertFalse(is_item_like(int))
        self.assertFalse(is_item_like(sum))
        self.assertFalse(is_item_like(1234))
        self.assertFalse(is_item_like(object()))
        self.assertFalse(is_item_like("a string"))
        self.assertFalse(is_item_like(b"some bytes"))
        self.assertFalse(is_item_like(["a", "list"]))
        self.assertFalse(is_item_like(("a", "tuple")))
        self.assertFalse(is_item_like({"a", "set"}))
        self.assertFalse(is_item_like(dict))
        self.assertFalse(is_item_like(Item))
        self.assertFalse(is_item_like(BaseItem))

    def test_true(self):
        self.assertTrue(is_item_like({"a": "dict"}))
        self.assertTrue(is_item_like(Item()))
        self.assertTrue(is_item_like(BaseItem()))
        self.assertTrue(is_item_like(TestItem(name="asdf", value=1234)))

    @unittest.skipIf(not DataClassItem, "dataclasses module is not available")
    def test_dataclass(self):
        self.assertFalse(is_item_like(DataClassItem))
        self.assertTrue(is_item_like(DataClassItem(name="asdf", value=1234)))


class ItemAdapterTestCase(unittest.TestCase):

    def test_non_item(self):
        with self.assertRaises(TypeError):
            ItemAdapter(Item)
        with self.assertRaises(TypeError):
            ItemAdapter(dict)
        with self.assertRaises(TypeError):
            ItemAdapter(1234)

    def test_get_set_value(self):
        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls()
            adapter = ItemAdapter(item)
            self.assertEqual(adapter.get_value("name"), None)
            self.assertEqual(adapter.get_value("value"), None)
            adapter.set_value("name", "asdf")
            adapter.set_value("value", 1234)
            self.assertEqual(adapter.get_value("name"), "asdf")
            self.assertEqual(adapter.get_value("value"), 1234)

    def test_as_dict(self):
        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls(name="asdf", value=1234)
            adapter = ItemAdapter(item)
            self.assertEqual(dict(name="asdf", value=1234), adapter.as_dict())
