from scrapy.webservice import JsonRpcResource

class CrawlerResource(JsonRpcResource):

    ws_name = 'crawler'

    def __init__(self, crawler):
        JsonRpcResource.__init__(self, crawler, crawler)
