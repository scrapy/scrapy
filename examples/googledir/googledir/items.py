# Define here the models for your scraped items

from scrapy.item import ScrapedItem

class GoogledirItem(ScrapedItem):

    def __str__(self):
        return "Google Category: name=%s url=%s" % (self.name, self.url)

