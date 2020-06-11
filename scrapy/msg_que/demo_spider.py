import scrapy
from scrapy.crawler import CrawlerProcess

class check_spider(scrapy.Spider):
    host='localhost' 
    port=6379
    db=0 
    password=None
    socket_timeout=None
    name = "Quotes"
    def start_requests(self):
        urls={
            "url1":'http://quotes.toscrape.com/page/1/',
            "url2":'http://quotes.toscrape.com/page/2/', 
            } 
        for url in urls:
            yield scrapy.Request(url=urls[url], callback=self.parse)
    
    def parse(self,response):
        for quote in response.css('div.quote'):
            yield {
                'text': quote.css('span.text::text').get(),
                'author': quote.css('small.author::text').get(),
                'tags': quote.css('div.tags a.tag::text').getall(),
            }


process = CrawlerProcess(settings = { 
    'FEED_FORMAT' :"json",
    "FEED_URI" : "items.json",
#    "JOBDIR":"crawl_dir"

})

process.crawl(check_spider)
process.start()