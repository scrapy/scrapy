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


def is_item_like(obj):
    """
    Return True if *obj* is considered a Scrapy *item*, False otherwise.

    An object is considered an *item* if it is:
    - a scrapy.item.BaseItem or dict instance (or any subclass)
    - a dataclass object
    """
    return isinstance(obj, (BaseItem, dict)) or _is_dataclass_instance(obj)


class ItemAdapter(MutableMapping):
    """
    Wrapper class to interact with items. It provides a common interface for components
    such as middlewares and pipelines to extract and set data without having to take
    the item's implementation (scrapy.Item, dict, dataclass) into account.
    """

    def __init__(self, item):
        if not is_item_like(item):
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
