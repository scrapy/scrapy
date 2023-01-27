import scrapy


class NormalSpider(scrapy.Spider):
    name = "normal"

    custom_settings = {
        "ITEM_PIPELINES": {"test_spider.pipelines.TestSpiderPipeline": 300}
    }

    def parse(self, response):
        pass
