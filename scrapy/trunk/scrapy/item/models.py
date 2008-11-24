from scrapy.item.adaptors import AdaptorPipe
from scrapy.conf import settings

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def set_adaptors(self, adaptors_dict):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        _adaptors_dict = dict(item for item in adaptors_dict.items() if isinstance(item[1], AdaptorPipe))
        self.__dict__['_adaptors_dict'] = _adaptors_dict
        return self
    
    def set_attrib_adaptors(self, attrib, pipe):
        """
        Set the adaptors (from a list or tuple) to be used for a specific attribute.
        """
        self._adaptors_dict[attrib] = AdaptorPipe(pipe) if hasattr(pipe, '__iter__') else None

    def attribute(self, attrname, value, **kwargs):
        pipe = self._adaptors_dict.get(attrname)
        if pipe:
            val = pipe(value, **kwargs)
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
        elif value:
            setattr(self, attrname, value)

    def __sub__(self, other):
        raise NotImplementedError

class ItemDelta(object):
    pass
