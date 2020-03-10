import scrapy
from scrapy.crawler import CrawlerProcess
try :
    from scrapy.msg_que import redis_spider
except :
    from demo_queue import redis_spider 

class check_spider(redis_spider):
    host='localhost' 
    port=6379
    db=0 
    password=None
    socket_timeout=None
    name = "Quotes"
    def start_requests(self):
        for url in self.run():
            yield scrapy.Request(url=url, callback=self.parse)
    
    def parse(self,response):
        for quote in response.css('div.quote'):
            yield {
                'text': quote.css('span.text::text').get(),
                'author': quote.css('small.author::text').get(),
                'tags': quote.css('div.tags a.tag::text').getall(),
            }


process = CrawlerProcess(settings = { 
    'FEED_FORMAT' :"json",
    "FEED_URI" : "items.json"

})

process.crawl(check_spider)
process.start()