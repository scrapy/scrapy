from scrapy.webservice import JsonRpcResource
from scrapy.extension import extensions

class ExtensionsResource(JsonRpcResource):

    ws_name = 'extensions'

    def __init__(self, _extensions=extensions):
        JsonRpcResource.__init__(self)
        self._target = _extensions
