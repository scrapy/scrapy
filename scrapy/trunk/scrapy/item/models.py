from scrapy.item.adaptors import AdaptorPipe
from scrapy.conf import settings

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def __init__(self, adaptors_pipe={}):
        self.set_adaptors(adaptors_pipe)
        pass

    def set_adaptors(self, adaptors_pipe):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        setattr(self, '_adaptors_pipe', AdaptorPipe(adaptors_pipe))
        return self
    
    def set_attrib_adaptors(self, attrib, adaptors):
        """
        Set the adaptors (from a list or tuple) to be used for a specific attribute.
        """
        self._adaptors_pipe.set_adaptors(attrib, adaptors)

    def attribute(self, attrname, value, **kwargs):
        val = self._adaptors_pipe.execute(attrname, value, kwargs)
        if not getattr(self, attrname, None) or kwargs.get('override'):
            setattr(self, attrname, val)

    def __sub__(self, other):
        raise NotImplementedError

class ItemDelta(object):
    pass
