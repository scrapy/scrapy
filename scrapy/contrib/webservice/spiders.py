from scrapy.webservice import JsonRpcResource
from scrapy.spider import spiders

class SpidersResource(JsonRpcResource):

    ws_name = 'spiders'

    def __init__(self, _spiders=spiders):
        JsonRpcResource.__init__(self)
        self._target = _spiders
