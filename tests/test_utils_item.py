# -*- coding: utf-8 -*-
import types
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
    name = Field(serializer=str)
    value = Field(serializer=int)


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
        self.assertTrue(_is_dataclass_instance(DataClassItem()))
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
            self.assertEqual(adapter.get("name"), None)
            self.assertEqual(adapter.get("value"), None)
            adapter["name"] = "asdf"
            adapter["value"] = 1234
            self.assertEqual(adapter.get("name"), "asdf")
            self.assertEqual(adapter.get("value"), 1234)
            self.assertEqual(adapter["name"], "asdf")
            self.assertEqual(adapter["value"], 1234)

        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls(name="asdf", value=1234)
            adapter = ItemAdapter(item)
            self.assertEqual(adapter.get("name"), "asdf")
            self.assertEqual(adapter.get("value"), 1234)
            self.assertEqual(adapter["name"], "asdf")
            self.assertEqual(adapter["value"], 1234)

    def test_get_value_keyerror_all(self):
        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls()
            adapter = ItemAdapter(item)
            with self.assertRaises(KeyError):
                adapter["undefined_field"]

    def test_get_value_keyerror_item_dict(self):
        for cls in [TestItem, dict]:
            item = cls()
            adapter = ItemAdapter(item)
            with self.assertRaises(KeyError):
                adapter["name"]

    def test_set_value_keyerror(self):
        for cls in filter(None, [TestItem, DataClassItem]):
            item = cls()
            adapter = ItemAdapter(item)
            with self.assertRaises(KeyError):
                adapter["undefined_field"] = "some value"

    def test_get_field(self):
        for cls in filter(None, [dict, DataClassItem]):
            item = cls(name="asdf", value=1234)
            adapter = ItemAdapter(item)
            self.assertIsNone(adapter.get_field("undefined_field"))
            self.assertIsNone(adapter.get_field("name"))
            self.assertIsNone(adapter.get_field("value"))

        # scrapy.item.Field objects are only present in BaseItem instances
        item = TestItem()
        adapter = ItemAdapter(item)
        self.assertIsNone(adapter.get_field("undefined_field"))
        self.assertIsInstance(adapter.get_field("name"), Field)
        self.assertIsInstance(adapter.get_field("value"), Field)
        self.assertIs(adapter.get_field("name")["serializer"], str)
        self.assertIs(adapter.get_field("value")["serializer"], int)

    def test_asdict(self):
        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls(name="asdf", value=1234)
            adapter = ItemAdapter(item)
            self.assertEqual(dict(name="asdf", value=1234), adapter.asdict())

    def test_field_names(self):
        for cls in filter(None, [TestItem, dict, DataClassItem]):
            item = cls(name="asdf", value=1234)
            adapter = ItemAdapter(item)
            self.assertIsInstance(adapter.field_names(), types.GeneratorType)
            self.assertEqual(sorted(list(adapter.field_names())), ["name", "value"])
