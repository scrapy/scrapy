# Define here the models for your scraped items

from scrapy.contrib_exp import newitem 

from scrapy.contrib_exp.newitem.extractors import ItemExtractor, adaptor
from scrapy.contrib_exp.adaptors import extract, strip


class GoogledirItem(newitem.Item):
    name = newitem.StringField()
    url = newitem.StringField()
    description = newitem.StringField()


class GoogledirItemExtractor(ItemExtractor):
    item_class = GoogledirItem

    name = adaptor(extract, strip)
    url = adaptor(extract, strip)
    description = adaptor(extract, strip)
