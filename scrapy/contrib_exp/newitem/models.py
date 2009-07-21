from UserDict import DictMixin

from scrapy.item import ScrapedItem
from scrapy.contrib_exp.newitem.fields import BaseField


class _ItemMeta(type):

    def __new__(meta, class_name, bases, attrs):
        fields = {}
        new_attrs = {}
        for n, v in attrs.iteritems():
            if isinstance(v, BaseField):
                fields[n] = v
            else:
                new_attrs[n] = v

        cls = type.__new__(meta, class_name, bases, new_attrs)
        cls.fields = cls.fields.copy()
        cls.fields.update(fields)
        return cls


class Item(DictMixin, ScrapedItem):

    __metaclass__ = _ItemMeta

    fields = {}

    def __init__(self, *args, **kwargs):
        self._values = {}
        
        # load default values
        for name, field in self.fields.iteritems():
            default = field.get_default()
            if default:
                self._values[name] = default
            
        # load init values
        if args or kwargs: # don't instantiate dict for simple (most common) case
            for k, v in dict(*args, **kwargs).iteritems():
                self[k] = v

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        self._values[key] = self.fields[key].to_python(value)

    def __delitem__(self, key):
        del self._values[key]

    def keys(self):
        return self._values.keys()

    def __repr__(self):
        """Generate a representation of this item that can be used to
        reconstruct the item by evaluating it
        """
        values = ', '.join('%s=%r' % field for field in self.iteritems())
        return "%s(%s)" % (self.__class__.__name__, values)

    def get_id(self):
        """Returns the unique id for this item."""
        raise NotImplementedError

