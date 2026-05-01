from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from twisted.internet import reactor
import gc

class FailingSpider(Spider):
    name = "fail"
    def __init__(self, *args, **kwargs):
        raise RuntimeError("simulated init error")

if __name__ == "__main__":
    settings = Settings({"TWISTED_REACTOR_ENABLED": True, "LOG_LEVEL": "DEBUG"})
    crawler = Crawler(FailingSpider, settings, init_reactor=True)
    
    def run(_=None):
        crawler.crawl()  # ← Deferred returned and completely ignored
        gc.collect()
        reactor.callLater(1, reactor.stop)
    
    reactor.callWhenRunning(run)
    reactor.run()
    gc.collect()
    print("done")