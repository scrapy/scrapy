"""
Scheduler queue web console module 

See documentation in docs/topics/extensions.rst
"""

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core.manager import scrapymanager
from scrapy.management.web import banner, webconsole_discover_module

class SchedulerQueue(object):
    webconsole_id = 'scheduler'
    webconsole_name = 'Scheduler queue'

    def __init__(self):
        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def webconsole_discover_module(self):
        return self

    def webconsole_render(self, wc_request):
        s = banner(self)
        s += "<ul>\n"
        for domain, request_queue in scrapymanager.engine.scheduler.pending_requests.iteritems():
            s += "<li>\n"
            s += "%s (<b>%s</b> requests)\n" % (domain, len(request_queue))
            s += "<ul>\n"
            for ((req, _), prio) in request_queue:
                s += "<li><a href='%s'>%s</a> (priority: %d)</li>\n" % (req.url, req.url, prio)
            s += "</ul>\n"
            s += "</li>\n" 
        s += "</ul>\n"

        s += "</body>\n"
        s += "</html>\n"

        return s
