from scrapy.spiders import Spider


# Same class name as in the nameless1 module, to check that nameless spiders
# are told apart by their full import path.
class NamelessSpider(Spider):
    pass
