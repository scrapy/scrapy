"""Some debugging functions for working with the Scrapy engine"""

from scrapy.core.engine import scrapyengine

def get_engine_status(engine=None):
    """Return a report of the current engine status"""
    if engine is None:
        engine = scrapyengine

    global_tests = [
        "datetime.utcnow()-engine.start_time",
        "engine.is_idle()",
        "engine.scheduler.is_idle()",
        "len(engine.scheduler.pending_requests)",
        "engine.downloader.is_idle()",
        "len(engine.downloader.sites)",
        "engine.downloader.has_capacity()",
        "engine.scraper.is_idle()",
        "len(engine.scraper.sites)",
    ]
    domain_tests = [
        "engine.domain_is_idle(domain)",
        "engine.closing.get(domain)",
        "engine.scheduler.domain_has_pending_requests(domain)",
        "len(engine.scheduler.pending_requests[domain])",
        "len(engine.downloader.sites[domain].queue)",
        "len(engine.downloader.sites[domain].active)",
        "len(engine.downloader.sites[domain].transferring)",
        "engine.downloader.sites[domain].closing",
        "engine.downloader.sites[domain].lastseen",
        "len(engine.scraper.sites[domain].queue)",
        "len(engine.scraper.sites[domain].active)",
        "engine.scraper.sites[domain].active_size",
        "engine.scraper.sites[domain].itemproc_size",
        "engine.scraper.sites[domain].needs_backout()",
    ]

    s = "Execution engine status\n\n"

    for test in global_tests:
        try:
            s += "%-47s : %s\n" % (test, eval(test))
        except Exception, e:
            s += "%-47s : %s (exception)\n" % (test, type(e).__name__)
    s += "\n"
    for domain in engine.downloader.sites:
        s += "%s\n" % domain
        for test in domain_tests:
            try:
                s += "  %-50s : %s\n" % (test, eval(test))
            except Exception, e:
                s += "  %-50s : %s (exception)\n" % (test, type(e).__name__)
    return s

def print_engine_status(engine=None):
    print get_engine_status(engine)

