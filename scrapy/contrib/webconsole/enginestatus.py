"""
Scheduler information module for Scrapy webconsole
"""
from scrapy.xlib.pydispatch import dispatcher
from scrapy.utils.engine import get_engine_status
from scrapy.management.web import banner

class EngineStatus(object):
    webconsole_id = 'enginestatus'
    webconsole_name = 'Engine status'

    def __init__(self):
        from scrapy.management.web import webconsole_discover_module
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        s = banner(self)
        s += "<pre><code>\n"
        s += get_engine_status()
        s += "</pre></code>\n"
        s += "</body>\n"
        s += "</html>\n"

        return s

    def webconsole_discover_module(self):
        return self
