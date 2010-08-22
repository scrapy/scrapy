from scrapy.webservice import JsonRpcResource
from scrapy.project import crawler

class SpidersResource(JsonRpcResource):

    ws_name = 'spiders'

    def __init__(self, _spiders=None):
        if _spiders is None:
            _spiders = crawler.spiders
        JsonRpcResource.__init__(self)
        self._target = _spiders
