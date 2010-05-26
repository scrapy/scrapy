"""Some debugging functions for working with the Scrapy engine"""

from time import time

from scrapy.core.engine import scrapyengine

def get_engine_status(engine=None):
    """Return a report of the current engine status"""
    if engine is None:
        engine = scrapyengine

    global_tests = [
        "time()-engine.start_time",
        "engine.is_idle()",
        "engine.has_capacity()",
        "engine.scheduler.is_idle()",
        "len(engine.scheduler.pending_requests)",
        "engine.downloader.is_idle()",
        "len(engine.downloader.sites)",
        "engine.scraper.is_idle()",
        "len(engine.scraper.sites)",
    ]
    spider_tests = [
        "engine.spider_is_idle(spider)",
        "engine.closing.get(spider)",
        "engine.scheduler.spider_has_pending_requests(spider)",
        "len(engine.scheduler.pending_requests[spider])",
        "len(engine.downloader.sites[spider].queue)",
        "len(engine.downloader.sites[spider].active)",
        "len(engine.downloader.sites[spider].transferring)",
        "engine.downloader.sites[spider].closing",
        "engine.downloader.sites[spider].lastseen",
        "len(engine.scraper.sites[spider].queue)",
        "len(engine.scraper.sites[spider].active)",
        "engine.scraper.sites[spider].active_size",
        "engine.scraper.sites[spider].itemproc_size",
        "engine.scraper.sites[spider].needs_backout()",
    ]

    s = "Execution engine status\n\n"

    for test in global_tests:
        try:
            s += "%-47s : %s\n" % (test, eval(test))
        except Exception, e:
            s += "%-47s : %s (exception)\n" % (test, type(e).__name__)
    s += "\n"
    for spider in engine.downloader.sites:
        s += "Spider: %s\n" % spider
        for test in spider_tests:
            try:
                s += "  %-50s : %s\n" % (test, eval(test))
            except Exception, e:
                s += "  %-50s : %s (exception)\n" % (test, type(e).__name__)
    return s

def print_engine_status(engine=None):
    print get_engine_status(engine)

