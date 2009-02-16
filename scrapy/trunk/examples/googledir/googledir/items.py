# Define here the models for your scraped items

from scrapy.contrib.item import RobustScrapedItem

class GoogledirItem(RobustScrapedItem):
    """Directory website link"""

    ATTRIBUTES = {
        'guid': basestring,
        'name': basestring,
        'url': basestring,
        'description': basestring,
        }
