from scrapy.spiders import Spider


class Spider4(Spider):
    name = "spider4"
    allowed_domains = ['spider4.com']

    @classmethod
    def handles_request(cls, request):
        return request.url == 'http://spider4.com/onlythis'
