from scrapy.command import ScrapyCommand

class Command(ScrapyCommand):

    default_settings = {
        'LOG_LEVEL': 'INFO',
        'LOGSTATS_INTERVAL': 1,
        'CLOSESPIDER_TIMEOUT': 10,
    }

    def short_desc(self):
        return "Run quick benchmark test"

    def run(self, args, opts):
        from scrapy.tests.spiders import FollowAllSpider
        from scrapy.tests.mockserver import MockServer

        with MockServer():
            spider = FollowAllSpider(total=100000)
            crawler = self.crawler_process.create_crawler()
            crawler.crawl(spider)
            self.crawler_process.start()
