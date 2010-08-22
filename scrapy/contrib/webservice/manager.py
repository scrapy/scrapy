from scrapy.webservice import JsonRpcResource
from scrapy.project import crawler

class ManagerResource(JsonRpcResource):

    ws_name = 'manager'

    def __init__(self, _manager=crawler):
        JsonRpcResource.__init__(self)
        self._target = _manager
