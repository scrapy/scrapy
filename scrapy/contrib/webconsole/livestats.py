"""
Live statistics extension
"""
from datetime import datetime
from scrapy.xlib.pydispatch import dispatcher
from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.management.web import banner, webconsole_discover_module

class SpiderStats(object):
    def __init__(self):
        self.scraped = 0
        self.crawled = 0
        self.started = None
        self.finished = None

class LiveStats(object):
    webconsole_id = 'livestats'
    webconsole_name = 'Spider live statistics of current run'

    def __init__(self):
        self.domains = {}
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.response_downloaded, signal=signals.response_downloaded)

        dispatcher.connect(self.webconsole_discover_module, signal=webconsole_discover_module)

    def spider_opened(self, spider):
        pstats = SpiderStats()
        self.domains[spider] = pstats
        pstats.started = datetime.now().replace(microsecond=0)
        pstats.finished = None

    def spider_closed(self, spider):
        self.domains[spider].finished = datetime.now().replace(microsecond=0)

    def item_scraped(self, item, spider):
        self.domains[spider].scraped += 1

    def response_downloaded(self, response, spider):
        # sometimes we download responses without opening/closing domains,
        # for example from scrapy shell
        if self.domains.get(spider):
            self.domains[spider].crawled += 1
            
    def webconsole_render(self, wc_request):
        sch = scrapyengine.scheduler
        dwl = scrapyengine.downloader

        totdomains = totscraped = totcrawled = totscheduled = totactive = totdqueued = tottransf = 0
        s = banner(self)
        s += "<table border='1'>\n"
        s += "<tr><th>Domain</th><th>Items<br>Scraped</th><th>Pages<br>Crawled</th><th>Scheduler<br>Pending</th><th>Downloader<br/>Queued</th><th>Downloader<br/>Active</th><th>Downloader<br/>Transferring</th><th>Start time</th><th>Finish time</th><th>Run time</th></tr>\n"
        for spider in sorted(self.domains.keys()):
            scheduled = len(sch.pending_requests[spider]) if spider in sch.pending_requests else 0
            active = len(dwl.sites[spider].active) if spider in dwl.sites else 0
            dqueued = len(dwl.sites[spider].queue) if spider in dwl.sites else 0
            transf = len(dwl.sites[spider].transferring) if spider in dwl.sites else 0
            stats = self.domains[spider]
            runtime = stats.finished - stats.started if stats.finished else datetime.now() - stats.started

            s += '<tr><td>%s</td><td align="right">%d</td><td align="right">%d</td><td align="right">%d</td><td align="right">%d</td><td align="right">%d</td><td align="right">%d</td><td>%s</td><td>%s</td><td>%s</td></tr>\n' % \
                 (spider.domain_name, stats.scraped, stats.crawled, scheduled, dqueued, active, transf, str(stats.started), str(stats.finished), str(runtime))

            totdomains += 1
            totscraped += stats.scraped
            totcrawled += stats.crawled
            totscheduled += scheduled
            totactive += active
            totdqueued += dqueued
            tottransf += transf
        s += '<tr><td><b>%d domains</b></td><td align="right"><b>%d</b></td><td align="right"><b>%d</b></td><td align="right"><b>%d</b></td><td align="right"><b>%d</b></td><td align="right"><b>%d</b></td><td align="right"><b>%d</b></td><td/><td/></tr>\n' % \
             (totdomains, totscraped, totcrawled, totscheduled, totdqueued, totactive, tottransf)
        s += "</table>\n"

        s += "</body>\n"
        s += "</html>\n"

        return s

    def webconsole_discover_module(self):
        return self
