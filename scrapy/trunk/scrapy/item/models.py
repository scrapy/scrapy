from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def setadaptors(self, adaptors_pipe):
        """
        Set adaptors to use for this item. Receives a dict of adaptors and
        returns the item itself.
        """
        object.__setattr__(self, '_adaptors_pipe', AdaptorPipe(adaptors_pipe))
        return self
    
    def append_adaptor(self, attrname, adaptor):
        self._adaptors_pipe.append_adaptor(attrname, adaptor)
            
    def attribute(self, attrname, value):
        value = self._adaptors_pipe.execute(attrname, value)
        if not hasattr(self, attrname) or not getattr(self, attrname):
            setattr(self, attrname, value)
