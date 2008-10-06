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


class ItemDelta(object):
    """
    This class represents the difference between
    a pair of items.
    """

    def __init__(self, old, new):
        self.diff = self.do_diff()

    def do_diff(self):
        """
        This method should retreive a dictionary
        containing the changes between both items
        as in this example:
        
        >>> delta.do_diff()
        >>> {'attrib': {'new': 'New value', 'old': 'Old value'}, # Common attributes
             'attrib2': {'new': 'New value 2', 'old': 'Old value 2'},
             'attrib3': [{'new': 'New list value', 'old': 'Old list value'}, # List attributes
                         {'new': 'New list value 2', 'old': 'Old list value 2'}]}
        """
        pass
