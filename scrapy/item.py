from scrapy.utils.ref import object_ref

class BaseItem(object_ref):
    """Base class for all scraped items."""
    pass


class ScrapedItem(BaseItem):

    def __init__(self, data=None):
        """
        A ScrapedItem can be initialised with a dictionary that will be
        squirted directly into the object.
        """
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
        reprdict = dict(items for items in self.__dict__.iteritems() if not items[0].startswith('_'))
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))

