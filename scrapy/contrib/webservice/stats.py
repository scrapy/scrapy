from scrapy.webservice import JsonRpcResource
from scrapy.stats import stats

class StatsResource(JsonRpcResource):

    ws_name = 'stats'

    def __init__(self, _stats=stats):
        JsonRpcResource.__init__(self)
        self._target = _stats
