from scrapy.item import ScrapedItem
from scrapy.contrib_exp.newitem.fields import BaseField


class _ItemMeta(type):

    def __new__(meta, class_name, bases, attrs):
        cls = type.__new__(meta, class_name, bases, attrs)
        cls.fields = cls.fields.copy()
        for n, v in attrs.iteritems():
            if isinstance(v, BaseField):
                cls.fields[n] = v
        return cls


class Item(ScrapedItem):
    """ This is the base class for all scraped items. """

    __metaclass__ = _ItemMeta

    fields = {}

    def __init__(self, values=None):
        self._values = {}
        if isinstance(values, dict):
            for k, v in values.iteritems():
                setattr(self, k, v)
        elif values is not None:
            raise TypeError("Items must be instantiated with dicts, got %s" % \
                type(values).__name__)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            return ScrapedItem.__setattr__(self, name, value)

        if name in self.fields.keys():
            self._values[name] = self.fields[name].to_python(value)
        else:
            raise AttributeError(name)

    def __getattribute__(self, name):
        if name.startswith('_') or name == 'fields':
            return ScrapedItem.__getattribute__(self, name)
        
        if name in self.fields.keys():
            try:
                return self._values[name]
            except KeyError:
                return self.fields[name].default
        else:
            raise AttributeError(name)

    def __repr__(self):
        """Generate a representation of this item that can be used to
        reconstruct the item by evaluating it
        """
        values = dict((field, getattr(self, field)) for field in self.fields)
        return "%s(%s)" % (self.__class__.__name__, repr(values))
