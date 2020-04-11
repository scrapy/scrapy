from scrapy.item import BaseItem


def _is_dataclass_instance(obj):
    """
    Returns True if *obj* is a dataclass object, False otherwise.
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
    Returns True if *obj* is considered a Scrapy *item*, False otherwise.

    An object is considered an *item* if it is:
    - a scrapy.item.BaseItem or dict instance (or any subclass)
    - a dataclass object
    """
    return isinstance(obj, (BaseItem, dict)) or _is_dataclass_instance(obj)


class ItemAdapter:
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

    def __contains__(self, field_name):
        if _is_dataclass_instance(self.item):
            from dataclasses import fields
            return field_name in (f.name for f in fields(self.item))
        return field_name in self.item

    def __getitem__(self, field_name):
        if _is_dataclass_instance(self.item):
            if field_name in self:
                return getattr(self.item, field_name)
            raise KeyError(field_name)
        return self.item[field_name]

    def __setitem__(self, field_name, value):
        if _is_dataclass_instance(self.item):
            if field_name in self:
                setattr(self.item, field_name, value)
            else:
                raise KeyError(
                    "%s does not support field: %s" % (self.item.__class__.__name__, field_name))
        else:
            self.item[field_name] = value

    def get(self, field_name, default=None):
        if _is_dataclass_instance(self.item):
            return getattr(self.item, field_name, default)
        return self.item.get(field_name, default)

    def get_field(self, field_name):
        """
        Returns the appropriate class:`scrapy.item.Field` object if the wrapped item
        is a BaseItem object, None otherwise.
        """
        if isinstance(self.item, BaseItem):
            return self.item.fields.get(field_name)
        return None

    def asdict(self):
        """
        Return a class:`dict` instance with the same data as the wrapped item.
        Returns a shallow copy of the wrapped item if it is already a dict object.
        """
        if _is_dataclass_instance(self.item):
            from dataclasses import asdict
            return asdict(self.item)
        elif isinstance(self.item, dict):
            return self.item.copy()
        elif isinstance(self.item, BaseItem):
            return dict(self.item)

    def field_names(self):
        """
        Returns a generator with the names of the item's fields
        """
        if _is_dataclass_instance(self.item):
            from dataclasses import fields
            for field in fields(self.item):
                yield field.name
        elif isinstance(self.item, dict):
            yield from self.item.keys()
        elif isinstance(self.item, BaseItem):
            yield from self.item.fields.keys()
