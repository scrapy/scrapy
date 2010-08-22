from scrapy.webservice import JsonResource
from scrapy.project import crawler
from scrapy.utils.engine import get_engine_status

class EngineStatusResource(JsonResource):

    ws_name = 'enginestatus'

    def __init__(self, spider_name=None, _manager=crawler):
        JsonResource.__init__(self)
        self._spider_name = spider_name
        self.isLeaf = spider_name is not None
        self._manager = _manager

    def render_GET(self, txrequest):
        status = get_engine_status(self._manager.engine)
        if self._spider_name is None:
            return status
        for sp, st in status['spiders'].items():
            if sp.name == self._spider_name:
                return st

    def getChild(self, name, txrequest):
        return EngineStatusResource(name, self._manager)
