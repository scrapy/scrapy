from scrapy.item import ScrapedItem
from scrapy.contrib_exp.newitem.declarative import Declarative
from scrapy.contrib_exp.newitem.fields import Field


class Item(Declarative, ScrapedItem):
    """ This is the base class for all scraped items. """

    fields = {}

    def __classinit__(cls, attrs):
        cls.fields = cls.fields.copy()
        for n, v in attrs.items():
            if isinstance(v, Field):
                cls.fields[n] = v

    def __init__(self):
        self._values = {}

    @property
    def _fields(self):
        return self.__class__.fields

    def __setattr__(self, name, value):
        if name.startswith('_'):
            return object.__setattr__(self, name, value)

        if name in self._fields.keys():
            self._values[name] = self._fields[name].assign(value)
        else:
            raise AttributeError(name)

    def __getattribute__(self, name):
        if name.startswith('_'):
            return object.__getattribute__(self, name)
        
        if name in self._fields.keys():
            try:
                return self._values[name]
            except KeyError:
                return self._fields[name].default
        else:
            raise AttributeError(name)

    def __repr__(self):
        """
        Generate the following format so that items can be deserialized
        easily: ClassName({'attrib': value, ...})
        """
        reprdict = dict((field, getattr(self, field)) for field in self._fields)
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))
