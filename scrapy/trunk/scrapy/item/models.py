from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """
    adaptors_pipe = AdaptorPipe()

    def __init__(self, adaptors_pipe=None):
        """If an adaptors_pipe is given, overrides class adaptors_pipe"""
        if adaptors_pipe:
            self.adaptors_pipe = adaptors_pipe

    def attribute(self, attrname, value):
        value = self.adaptors_pipe.execute(attrname, value)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)
