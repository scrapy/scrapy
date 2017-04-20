# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

class ReelscoutItem(Item):
	description = Field()
	jurisdictiontype = Field()
	agency = Field()
	contactinfo = Field()
	links = Field()