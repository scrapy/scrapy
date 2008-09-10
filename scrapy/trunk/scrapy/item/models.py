from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    """
    adaptors_pipe = AdaptorPipe([])

    def attribute(self, attrname, value):
        value = self.adaptors_pipe.execute(attrname, value)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)
