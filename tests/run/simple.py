import sys

import scrapy
from scrapy.utils.reactorless import is_reactorless


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        self.logger.info(f"is_reactorless(): {is_reactorless()}")
        return
        yield


crawl = scrapy.run(NoRequestsSpider)
assert crawl.crawler.spider is not None
print(f"spider: {crawl.crawler.spider.name}", file=sys.stderr)
print(
    f"finish_reason: {crawl.crawler.stats.get_value('finish_reason')}", file=sys.stderr
)
try:
    iter(crawl)
except TypeError as exception:
    print(f"TypeError: {exception}", file=sys.stderr)
try:
    scrapy.run_async(NoRequestsSpider)
except RuntimeError as exception:
    print(f"RuntimeError: {exception}", file=sys.stderr)
