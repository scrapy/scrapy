from scrapy.item.adaptors import AdaptorDict
from scrapy.conf import settings

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def set_adaptors(self, adaptors_dict, **kwargs):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        setattr(self, '_adaptors_dict', AdaptorDict(adaptors_dict))
        return self
    
    def set_attrib_adaptors(self, attrib, adaptors, **kwargs):
        """
        Set the adaptors (from a list or tuple) to be used for a specific attribute.
        """
        self._adaptors_dict[attrib] = adaptors

    def attribute(self, attrname, value, override=False, add=False, debug=False):
        val = self._adaptors_dict.execute(attrname, value, debug)
        if val or val is False:
            curr_val = getattr(self, attrname, None)
            if not curr_val:
                setattr(self, attrname, val)
            else:
                if override:
                    setattr(self, attrname, val)
                elif add and all(hasattr(var, '__iter__') for var in (curr_val, val)):
                    newval = []
                    newval.extend(curr_val)
                    newval.extend(val)
                    setattr(self, attrname, newval)

    def __sub__(self, other):
        raise NotImplementedError

class ItemDelta(object):
    pass
