from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.

    The only required attributes are:
    * guid (unique global indentifier)
    * url (URL where that item was scraped from)
    """
    adaptors_pipe = AdaptorPipe()

    def attribute(self, attrname, value, match_condition=None):
        value = self.adaptors_pipe.execute(match_condition or attrname, value)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)
