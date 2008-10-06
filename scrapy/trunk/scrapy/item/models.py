from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def setadaptors(self, adaptors_dict):
        """Set adaptors to use for this item. Receives a dict of adaptors and
        returns the item itself"""
        self.adaptors_dict = AdaptorPipe(adaptors_dict)
        return self

    def attribute(self, attrname, value):
        value = self.adaptors_pipe.execute(attrname, value)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)
