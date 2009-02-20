# Define here the models for your scraped items

from scrapy.contrib_exp import newitem 

from scrapy.contrib_exp.newitem import extractors
from scrapy.contrib_exp import adaptors


class GoogledirItem(newitem.Item):
    name = newitem.StringField()
    url = newitem.StringField()
    description = newitem.StringField()


class GoogledirItemExtractor(extractors.ItemExtractor):
    item_class = GoogledirItem

    name = extractors.ExtractorField([adaptors.extract, adaptors.strip])
    url = extractors.ExtractorField([adaptors.extract, adaptors.strip])
    description = extractors.ExtractorField([adaptors.extract, adaptors.strip])
