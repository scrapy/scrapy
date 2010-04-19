from scrapy.xlib.pydispatch import dispatcher

from scrapy.stats import stats
from scrapy.management.web import banner, webconsole_discover_module

def stats_html_table(statsdict):
    s = ""
    s += "<table border='1'>\n"
    for kv in statsdict.iteritems():
        s += "<tr><th align='left'>%s</th><td>%s</td></tr>\n" % kv
    s += "</table>\n"
    return s

class StatsDump(object):
    webconsole_id = 'stats'
    webconsole_name = 'StatsCollector dump'

    def __init__(self):
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_render(self, wc_request):
        s = banner(self)
        s += "<h3>Global stats</h3>\n"
        s += stats_html_table(stats.get_stats())
        for spider, spider_stats in stats.iter_spider_stats():
            s += "<h3>%s</h3>\n" % spider.name
            s += stats_html_table(spider_stats)
        s += "</body>\n"
        s += "</html>\n"

        return str(s)

    def webconsole_discover_module(self):
        return self

