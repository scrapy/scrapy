from collections.abc import MutableMapping

from scrapy.item import BaseItem


def _is_dataclass_instance(obj):
    """
    Return True if *obj* is a dataclass object, False otherwise.
    Taken from https://docs.python.org/3/library/dataclasses.html#dataclasses.is_dataclass.
    """
    try:
        from dataclasses import is_dataclass
    except ImportError:
        return False
    else:
        return is_dataclass(obj) and not isinstance(obj, type)


def is_item(obj):
    """Return ``True`` if *obj* is an instance of a :ref:`supported item type
    <item-types>`; return ``False`` otherwise."""
    return isinstance(obj, (BaseItem, dict)) or _is_dataclass_instance(obj)


class ItemAdapter(MutableMapping):
    """Wrapper class to interact with any :ref:`supported item type
    <item-types>` using the same, :class:`dict`-like API.

    .. invisible-code-block: python

        import sys

    .. skip: start if(sys.version_info < (3, 6), reason="python 3.6+ only")

    >>> from dataclasses import dataclass
    >>> from scrapy.utils.item import ItemAdapter
    >>> @dataclass
    ... class InventoryItem:
    ...     name: str
    ...     price: int
    ...
    >>> item = InventoryItem(name="foo", price=10)
    >>> adapter = ItemAdapter(item)
    >>> adapter.item is item
    True
    >>> adapter["name"]
    'foo'
    >>> adapter["name"] = "bar"
    >>> adapter["price"] = 5
    >>> item
    InventoryItem(name='bar', price=5)

    .. skip: end
    """

    def __init__(self, item):
        if not is_item(item):
            raise TypeError("Expected a valid item, got %r instead: %s" % (type(item), item))
        self.item = item

    def __repr__(self):
        return "ItemAdapter for type %s: %r" % (self.item.__class__.__name__, self.item)

    def __getitem__(self, field_name):
        if _is_dataclass_instance(self.item):
            if field_name in iter(self):
                return getattr(self.item, field_name)
            raise KeyError(field_name)
        return self.item[field_name]

    def __setitem__(self, field_name, value):
        if _is_dataclass_instance(self.item):
            if field_name in iter(self):
                setattr(self.item, field_name, value)
            else:
                raise KeyError("%s does not support field: %s"
                               % (self.item.__class__.__name__, field_name))
        else:
            self.item[field_name] = value

    def __delitem__(self, field_name):
        if _is_dataclass_instance(self.item):
            if field_name in iter(self):
                try:
                    delattr(self.item, field_name)
                except AttributeError:
                    raise KeyError(field_name)
            else:
                raise KeyError("%s does not support field: %s"
                               % (self.item.__class__.__name__, field_name))
        else:
            del self.item[field_name]

    def __iter__(self):
        if _is_dataclass_instance(self.item):
            return iter(attr for attr in dir(self.item) if attr in self.field_names())
        return iter(self.item)

    def __len__(self):
        if _is_dataclass_instance(self.item):
            return len(list(iter(self)))
        return len(self.item)

    def get_field(self, field_name):
        """
        Return the appropriate class:`scrapy.item.Field` object
        if the wrapped item is a BaseItem object, None otherwise.
        """
        if isinstance(self.item, BaseItem):
            return self.item.fields.get(field_name)
        return None

    def field_names(self):
        """
        Return a list with the names of all the defined fields for the item
        """
        if _is_dataclass_instance(self.item):
            from dataclasses import fields
            return [field.name for field in fields(self.item)]
        elif isinstance(self.item, dict):
            return list(self.item.keys())
        elif isinstance(self.item, BaseItem):
            return list(self.item.fields.keys())
