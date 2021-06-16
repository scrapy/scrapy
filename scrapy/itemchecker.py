"""
Filter for Scrapy Items to be used by Feed slots.
"""
from scrapy.utils.misc import load_object


class ItemChecker:
    """
    This will be used by FeedExporter to decide if an item should be allowed
    to be exported to a particular feed.
    :param feed_options: feed specific options passed from FeedExporter
    :type feed_options: dict
    """

    def __init__(self, feed_options):
        self.feed_options = feed_options
        self.item_classes = set()

        if 'item_classes' in self.feed_options:
            for item_class in self.feed_options['item_classes']:
                self.item_classes.add(load_object(item_class))

    def accepts(self, item):
        """
        Main method to be used by FeedExporter to check if the item is acceptable according
        to defined constraints.
        :param item: scraped item which user wants to check if is acceptable
        :type item: scrapy supported items (dictionaries, Item objects, dataclass objects, and attrs objects)
        :return: `True` if accepted, `False` otherwise
        :rtype: bool
        """
        if self.item_classes:
            return isinstance(item, tuple(self.item_classes))

        return True    # accept all items if none declared in item_classes
