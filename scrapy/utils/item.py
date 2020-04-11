from scrapy.item import BaseItem


def is_dataclass_instance(obj):
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
    return isinstance(obj, (BaseItem, dict)) or is_dataclass_instance(obj)


class ItemAdapter:
    """
    Wrapper class to interact with items. It provides a common interface for components
    such as middlewares and pipelines to extract and set data without having to take
    the item's implementation (scrapy.Item, dict, dataclass) into account.
    """

    def __init__(self, item):
        if not is_item_like(item):
            raise TypeError("Expected a valid item, got %s (%r) instead" % (item, type(item)))
        self.item = item

    def __contains__(self, field_name):
        """
        Returns True if the field with the given name contains a value, False otherwise
        """
        if is_dataclass_instance(self.item):
            from dataclasses import fields
            return field_name in (f.name for f in fields(self.item))
        else:
            return field_name in self.item

    def get_value(self, field_name, default=None):
        if is_dataclass_instance(self.item):
            return getattr(self.item, field_name, default)
        else:
            return self.item.get(field_name, default)

    def set_value(self, field_name, value):
        if is_dataclass_instance(self.item):
            from dataclasses import fields
            if field_name in (f.name for f in fields(self.item)):
                setattr(self.item, field_name, value)
            else:
                raise KeyError(
                    "%s does not support field: %s" % (self.item.__class__.__name__, field_name))
        else:
            self.item[field_name] = value

    def get_field(self, field_name):
        """
        Returns the corresponding scrapy.item.Field object if the base item
        is a BaseItem object, None otherwise.
        """
        if isinstance(self.item, BaseItem):
            return self.item.fields.get(field_name)
        return None

    def as_dict(self):
        """
        Return a class:`dict` instance with the same data as the stored item.
        Returns the base item unaltered if is already a dict object.
        """
        if isinstance(self.item, dict):
            return self.item
        elif isinstance(self.item, BaseItem):
            return dict(self.item)
        elif is_dataclass_instance(self.item):
            from dataclasses import asdict
            return asdict(self.item)

    def field_names(self):
        """
        Returns a generator with the names of the item's fields
        """
        if is_dataclass_instance(self.item):
            from dataclasses import fields
            return (field.name for field in fields(self.item))
        elif isinstance(self.item, dict):
            yield from self.item.keys()
        elif isinstance(self.item, BaseItem):
            yield from self.item.fields.keys()
