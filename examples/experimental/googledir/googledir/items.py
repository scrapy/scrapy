# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/topics/items.html

from scrapy.item import Item, Field

class GoogledirItem(Item):

    name = Field(default='')
    url = Field(default='')
    description = Field(default='')

    def __str__(self):
        return "Google Category: name=%s url=%s" \
                    % (self['name'], self['url'])
