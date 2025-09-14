from abc import ABCMeta
from unittest import mock

import pytest

from scrapy.item import Field, Item, ItemMeta


class TestItem:
    def assertSortedEqual(self, first, second, msg=None):
        assert sorted(first) == sorted(second), msg

    def test_simple(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i["name"] = "name"
        assert i["name"] == "name"

    def test_init(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        with pytest.raises(KeyError):
            i["name"]

        i2 = TestItem(name="john doe")
        assert i2["name"] == "john doe"

        i3 = TestItem({"name": "john doe"})
        assert i3["name"] == "john doe"

        i4 = TestItem(i3)
        assert i4["name"] == "john doe"

        with pytest.raises(KeyError):
            TestItem({"name": "john doe", "other": "foo"})

    def test_invalid_field(self):
        class TestItem(Item):
            pass

        i = TestItem()
        with pytest.raises(KeyError):
            i["field"] = "text"
        with pytest.raises(KeyError):
            i["field"]

    def test_repr(self):
        class TestItem(Item):
            name = Field()
            number = Field()

        i = TestItem()
        i["name"] = "John Doe"
        i["number"] = 123
        itemrepr = repr(i)

        assert itemrepr == "{'name': 'John Doe', 'number': 123}"

        i2 = eval(itemrepr)  # pylint: disable=eval-used
        assert i2["name"] == "John Doe"
        assert i2["number"] == 123

    def test_private_attr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i._private = "test"
        assert i._private == "test"

    def test_raise_getattr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        with pytest.raises(AttributeError):
            i.name

    def test_raise_setattr(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        with pytest.raises(AttributeError):
            i.name = "john"

    def test_custom_methods(self):
        class TestItem(Item):
            name = Field()

            def get_name(self):
                return self["name"]

            def change_name(self, name):
                self["name"] = name

        i = TestItem()
        with pytest.raises(KeyError):
            i.get_name()
        i["name"] = "lala"
        assert i.get_name() == "lala"
        i.change_name("other")
        assert i.get_name() == "other"

    def test_metaclass(self):
        class TestItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        i = TestItem()
        i["name"] = "John"
        assert list(i.keys()) == ["name"]
        assert list(i.values()) == ["John"]

        i["keys"] = "Keys"
        i["values"] = "Values"
        self.assertSortedEqual(list(i.keys()), ["keys", "values", "name"])
        self.assertSortedEqual(list(i.values()), ["Keys", "Values", "John"])

    def test_metaclass_with_fields_attribute(self):
        class TestItem(Item):
            fields = {"new": Field(default="X")}

        item = TestItem(new="New")
        self.assertSortedEqual(list(item.keys()), ["new"])
        self.assertSortedEqual(list(item.values()), ["New"])

    def test_metaclass_inheritance(self):
        class ParentItem(Item):
            name = Field()
            keys = Field()
            values = Field()

        class TestItem(ParentItem):
            keys = Field()

        i = TestItem()
        i["keys"] = 3
        assert list(i.keys()) == ["keys"]
        assert list(i.values()) == [3]

    def test_metaclass_multiple_inheritance_simple(self):
        class A(Item):
            fields = {"load": Field(default="A")}
            save = Field(default="A")

        class B(A):
            pass

        class C(Item):
            fields = {"load": Field(default="C")}
            save = Field(default="C")

        class D(B, C):
            pass

        item = D(save="X", load="Y")
        assert item["save"] == "X"
        assert item["load"] == "Y"
        assert D.fields == {"load": {"default": "A"}, "save": {"default": "A"}}

        # D class inverted
        class E(C, B):
            pass

        assert E(save="X")["save"] == "X"
        assert E(load="X")["load"] == "X"
        assert E.fields == {"load": {"default": "C"}, "save": {"default": "C"}}

    def test_metaclass_multiple_inheritance_diamond(self):
        class A(Item):
            fields = {"update": Field(default="A")}
            save = Field(default="A")
            load = Field(default="A")

        class B(A):
            pass

        class C(A):
            fields = {"update": Field(default="C")}
            save = Field(default="C")

        class D(B, C):
            fields = {"update": Field(default="D")}
            load = Field(default="D")

        assert D(save="X")["save"] == "X"
        assert D(load="X")["load"] == "X"
        assert D.fields == {
            "save": {"default": "C"},
            "load": {"default": "D"},
            "update": {"default": "D"},
        }

        # D class inverted
        class E(C, B):
            load = Field(default="E")

        assert E(save="X")["save"] == "X"
        assert E(load="X")["load"] == "X"
        assert E.fields == {
            "save": {"default": "C"},
            "load": {"default": "E"},
            "update": {"default": "C"},
        }

    def test_metaclass_multiple_inheritance_without_metaclass(self):
        class A(Item):
            fields = {"load": Field(default="A")}
            save = Field(default="A")

        class B(A):
            pass

        class C:
            fields = {"load": Field(default="C")}
            not_allowed = Field(default="not_allowed")
            save = Field(default="C")

        class D(B, C):
            pass

        with pytest.raises(KeyError):
            D(not_allowed="value")
        assert D(save="X")["save"] == "X"
        assert D.fields == {"save": {"default": "A"}, "load": {"default": "A"}}

        # D class inverted
        class E(C, B):
            pass

        with pytest.raises(KeyError):
            E(not_allowed="value")
        assert E(save="X")["save"] == "X"
        assert E.fields == {"save": {"default": "A"}, "load": {"default": "A"}}

    def test_to_dict(self):
        class TestItem(Item):
            name = Field()

        i = TestItem()
        i["name"] = "John"
        assert dict(i) == {"name": "John"}

    def test_copy(self):
        class TestItem(Item):
            name = Field()

        item = TestItem({"name": "lower"})
        copied_item = item.copy()
        assert id(item) != id(copied_item)
        copied_item["name"] = copied_item["name"].upper()
        assert item["name"] != copied_item["name"]

    def test_deepcopy(self):
        class TestItem(Item):
            tags = Field()

        item = TestItem({"tags": ["tag1"]})
        copied_item = item.deepcopy()
        item["tags"].append("tag2")
        assert item["tags"] != copied_item["tags"]


class TestItemMeta:
    def test_new_method_propagates_classcell(self):
        new_mock = mock.Mock(side_effect=ABCMeta.__new__)
        base = ItemMeta.__bases__[0]

        with mock.patch.object(base, "__new__", new_mock):

            class MyItem(Item):
                def f(self):
                    # For rationale of this see:
                    # https://github.com/python/cpython/blob/ee1a81b77444c6715cbe610e951c655b6adab88b/Lib/test/test_super.py#L222
                    return __class__

            MyItem()

        (first_call, second_call) = new_mock.call_args_list[-2:]

        mcs, class_name, bases, attrs = first_call[0]
        assert "__classcell__" not in attrs
        mcs, class_name, bases, attrs = second_call[0]
        assert "__classcell__" in attrs


class TestItemMetaClassCellRegression:
    def test_item_meta_classcell_regression(self):
        class MyItem(Item, metaclass=ItemMeta):
            def __init__(self, *args, **kwargs):  # pylint: disable=useless-parent-delegation
                # This call to super() trigger the __classcell__ propagation
                # requirement. When not done properly raises an error:
                # TypeError: __class__ set to <class '__main__.MyItem'>
                # defining 'MyItem' as <class '__main__.MyItem'>
                super().__init__(*args, **kwargs)
