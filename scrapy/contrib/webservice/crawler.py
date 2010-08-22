from scrapy.webservice import JsonRpcResource
from scrapy.project import crawler

class CrawlerResource(JsonRpcResource):

    ws_name = 'crawler'

    def __init__(self, _crawler=crawler):
        JsonRpcResource.__init__(self)
        self._target = _crawler
