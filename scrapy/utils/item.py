from scrapy.item import BaseItem


def is_item_like(obj):
    """
    Returns True if *obj* is considered a Scrapy *item*, False otherwise.

    An object is considered an *item* if it is:
    - a scrapy.item.BaseItem or dict instance (or any subclass)
    - a dataclass object
    """
    return isinstance(obj, (BaseItem, dict)) or _is_dataclass_instance(obj)


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

    def get_item_field(self, field, default=None):
        if _is_dataclass_instance(self.item):
            return getattr(self.item, field, default)
        else:
            return self.item.get(field, default)

    def set_item_field(self, field, value):
        if _is_dataclass_instance(self.item):
            from dataclasses import fields as dataclass_fields
            field_names = [f.name for f in dataclass_fields(self.item)]
            if field in field_names:
                setattr(self.item, field, value)
            else:
                raise KeyError(
                    "%s does not support field: %s" % (self.item.__class__.__name__, field))
        else:
            self.item[field] = value

    def as_dict(self):
        """
        Return a class:`dict` instance with the same data as the stored item.
        Returns the stored item unaltered if is already a dict object.
        """
        if isinstance(self.item, dict):
            return self.item
        elif isinstance(self.item, BaseItem):
            return dict(self.item)
        elif _is_dataclass_instance(self.item):
            from dataclasses import asdict
            return asdict(self.item)
