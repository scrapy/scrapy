from scrapy.item import Item, Field

class GoogledirItem(Item):

    name = Field()
    url = Field()
    description = Field()

    def __str__(self):
        return "Google Category: name=%s url=%s" % (self['name'], self['url'])
