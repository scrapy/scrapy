from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.

    The only required attributes are:
    * guid (unique global indentifier)
    * url (URL where that item was scraped from)
    """
    adaptors_pipe = AdaptorPipe()

    def attribute(self, attrname, value, **pipeargs):
        value = self.adaptors_pipe.execute(attrname, value, **pipeargs)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)
