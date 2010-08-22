from scrapy.webservice import JsonRpcResource
from scrapy.project import crawler

class ExtensionsResource(JsonRpcResource):

    ws_name = 'extensions'

    def __init__(self, _extensions=None):
        if _extensions is None:
            _extensions = crawler.extensions
        JsonRpcResource.__init__(self)
        self._target = _extensions
