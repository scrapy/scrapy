import scrapy


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    def __init__(self, *args, foo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.foo = foo

    async def start(self):
        self.logger.info(f"foo: {self.foo}")
        self.logger.info(f"CONCURRENT_REQUESTS: {self.settings['CONCURRENT_REQUESTS']}")
        return
        yield


scrapy.run(NoRequestsSpider, {"foo": 42}, settings={"CONCURRENT_REQUESTS": 7})
