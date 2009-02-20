from scrapy.item import ScrapedItem
from scrapy.contrib_exp.newitem.fields import Field


class Item(ScrapedItem):
    """
    This is the base class for all scraped items.
    """

    def __init__(self):
        self._values = {}
        self._fields = self._get_fields()

    def _get_fields(self):
        return dict(i for i in self.__class__.__dict__.iteritems() \
                    if isinstance(i[1], Field))

    def __setattr__(self, name, value):
        if not name.startswith('_'):
            if name in self._fields.keys():
                self._values[name] = self._fields[name].assign(value)
            else:
                raise AttributeError(name)
        else:
            object.__setattr__(self, name, value)

    def __getattribute__(self, name):
        if not name.startswith('_') and name in self._fields.keys():
            try:
                return self._values[name]
            except KeyError:
                return self._fields[name].default
        else:
            return object.__getattribute__(self, name)

    def __repr__(self):
        """
        Generate the following format so that items can be deserialized
        easily: ClassName({'attrib': value, ...})
        """
        reprdict = dict((field, getattr(self, field)) for field in self._fields)
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))
