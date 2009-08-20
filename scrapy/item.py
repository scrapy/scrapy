"""
Scrapy Item

See documentation in docs/topics/item.rst
"""

from UserDict import DictMixin

from scrapy.utils.trackref import object_ref

class BaseItem(object_ref):
    """Base class for all scraped items."""
    pass


class Field(dict):
    """Container of field metadata"""


class _ItemMeta(type):

    def __new__(mcs, class_name, bases, attrs):
        fields = {}
        new_attrs = {}
        for n, v in attrs.iteritems():
            if isinstance(v, Field):
                fields[n] = v
            else:
                new_attrs[n] = v

        cls = type.__new__(mcs, class_name, bases, new_attrs)
        cls.fields = cls.fields.copy()
        cls.fields.update(fields)
        return cls


class Item(DictMixin, BaseItem):

    __metaclass__ = _ItemMeta

    fields = {}

    def __init__(self, *args, **kwargs):
        self._values = {}
        if args or kwargs: # avoid creating dict for most common case
            for k, v in dict(*args, **kwargs).iteritems():
                self[k] = v

    def __getitem__(self, key):
        try:
            return self._values[key]
        except KeyError:
            field = self.fields[key]
            if 'default' in field:
                return field['default']
            raise

    def __setitem__(self, key, value):
        if key in self.fields:
            self._values[key] = value
        else:
            raise KeyError("%s does not support field: %s" % \
                (self.__class__.__name__, key))

    def __delitem__(self, key):
        del self._values[key]

    def __getattr__(self, name):
        if name in self.fields:
            raise AttributeError("Use [%r] to access item field value" % name)
        raise AttributeError(name)

    def keys(self):
        return self._values.keys()

    def __repr__(self):
        """Generate a representation of this item that can be used to
        reconstruct the item by evaluating it
        """
        values = ', '.join('%s=%r' % field for field in self.iteritems())
        return "%s(%s)" % (self.__class__.__name__, values)


class ScrapedItem(BaseItem):

    def __init__(self, data=None):
        """
        A ScrapedItem can be initialised with a dictionary that will be
        squirted directly into the object.
        """
        import warnings
        warnings.warn("scrapy.item.ScrapedItem is deprecated, use scrapy.item.Item instead",
            DeprecationWarning, stacklevel=2)
        if isinstance(data, dict):
            for attr, value in data.iteritems():
                setattr(self, attr, value)
        elif data is not None:
            raise TypeError("Initialize with dict, not %s" % data.__class__.__name__)

    def __repr__(self):
        """
        Generate the following format so that items can be deserialized
        easily: ClassName({'attrib': value, ...})
        """
        reprdict = dict(items for items in self.__dict__.iteritems() \
            if not items[0].startswith('_'))
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))

