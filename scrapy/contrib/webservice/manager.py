from scrapy.webservice import JsonRpcResource
from scrapy.core.manager import scrapymanager

class ManagerResource(JsonRpcResource):

    ws_name = 'manager'

    def __init__(self, _manager=scrapymanager):
        JsonRpcResource.__init__(self)
        self._target = _manager
