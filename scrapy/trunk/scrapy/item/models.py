import copy

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    """

    def __init__(self, data=None):
        """
        A ScrapedItem can be initialised with a dictionary that will be
        squirted directly into the object.
        """
        if isinstance(data, dict):
            for attr, value in data.iteritems():
                setattr(self, attr, value)
        elif data is not None:
            raise UsageError("Initialize with dict, not %s" % data.__class__.__name__)

    def __repr__(self):
        """
        Generate the following format so that items can be deserialized
        easily: ClassName({'attrib': value, ...})
        """
        reprdict = dict(items for items in self.__dict__.iteritems() if not items[0].startswith('_'))
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))

    def __sub__(self, other):
        raise NotImplementedError

    def copy(self):
        """Create a new ScrapedItem based on the current one"""
        return copy.deepcopy(self)

class ItemDelta(object):
    pass
