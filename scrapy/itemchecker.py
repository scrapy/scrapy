"""
Filter for Scrapy Items to be used by Feed slots.
"""
from itemadapter import ItemAdapter

from scrapy import Item
from scrapy.utils.misc import load_object


class ItemChecker:
    """
    This will be used by FeedExporter to decide if an item should be allowed
    to be exported to a particular feed.
    :param feed_options: feed specific options passed from FeedExporter
    :type feed_options: dict
    """

    item_classes = ()

    def __init__(self, feed_options):
        self.feed_options = feed_options

        if 'item_classes' in self.feed_options:
            item_classes = self.feed_options['item_classes']

            if isinstance(item_classes, (Item, str)):
                self.item_classes += (load_object(item_classes),)
            elif isinstance(item_classes, (list,set,tuple)):
                for item_class in item_classes:
                    self.item_classes += (load_object(item_class),)
            else:
                pass
                # raise some warning for invalid item_classes declaration?

    def accepts(self, item):
        """
        Main method to be used by FeedExporter to check if the item is acceptable according
        to defined constraints. This method uses accepts_class and accept_fields method
        to decide if the item is acceptable.
        :param item: scraped item which user wants to check if is acceptable
        :type item: scrapy supported items (dictionaries, Item objects, dataclass objects, and attrs objects)
        :return: `True` if accepted, `False` otherwise
        :rtype: bool
        """
        adapter = ItemAdapter(item)
        return self.accepts_class(item) and self.accepts_fields(adapter.asdict())

    def accepts_class(self, item):
        """
        Method to check if the item is an instance of a class declared in accepted_items
        list. Can be overriden by user if they want allow certain item classes.
        Default behaviour: if accepted_items is empty then all items will be
        accepted else only items present in accepted_items will be accepted.
        :param item: scraped item
        :type item: scrapy supported items  (dictionaries, Item objects, dataclass objects, and attrs objects)
        :return: `True` if item in accepted_items, `False` otherwise
        :rtype: bool
        """
        if self.item_classes:
            return isinstance(item, self.item_classes)

        return True    # all items accepted if none declared in accepted_items

    def accepts_fields(self, fields):
        """
        Method to check if certain fields of the item passes the filtering
        criteria. Users can override this method to add their own custom
        filters.
        Default behaviour: accepts all fields.
        :param fields: all the fields of the scraped item
        :type fields: dict
        :return: `True` if all the fields passes the filtering criteria, else `False`
        :rtype: bool
        """
        return True    # all fields accepted if user doesn't override and write their custom filter
