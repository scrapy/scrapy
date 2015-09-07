from scrapy.spiders import Spider

class Spider3(Spider):
    name = "spider3"
    allowed_domains = ['spider3.com']

    @classmethod
    def handles_request(cls, request):
        return request.url == 'http://spider3.com/onlythis'
