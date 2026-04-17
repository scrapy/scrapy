from scrapy import Spider
from scrapy.crawler import CrawlerProcess

class FailingSpider(Spider):
    name = "fail"

    def __init__(self,*args, **kwargs):
        print("parse hit")
        raise RuntimeError("simulated init error")

if __name__ == "__main__":
    process = CrawlerProcess(
        {
            "TWISTED_REACTOR_ENABLED" : True, "LOG_LEVEL": "DEBUG"
        }
    ) 
    process.crawl(FailingSpider)
    process.start()
print("all done")