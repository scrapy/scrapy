import pprint

from pydispatch import dispatcher

from scrapy.stats import stats
from scrapy.management.web import banner, webconsole_discover_module

class StatsDump(object):
    webconsole_id = 'stats'
    webconsole_name = 'StatsCollector dump'

    def __init__(self):
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        s = banner(self)
        s += "<pre><code>\n"
        s += pprint.pformat(stats)
        s += "</pre></code>\n"
        s += "</body>\n"
        s += "</html>\n"

        return str(s)

    def webconsole_discover_module(self):
        return self
