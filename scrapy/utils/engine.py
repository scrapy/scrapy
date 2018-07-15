"""Some debugging functions for working with the Scrapy engine"""

from __future__ import print_function
from time import time # used in global tests code

def get_engine_status(engine):
    """Return a report of the current engine status"""
    tests = [
        "time()-engine.start_time",
        "engine.has_capacity()",
        "len(engine.downloader.active)",
        "engine.scraper.is_idle()",
        "engine.spider.name",
        "engine.spider_is_idle(engine.spider)",
        "engine.slot.closing",
        "len(engine.slot.inprogress)",
        "len(engine.slot.scheduler.dqs or [])",
        "len(engine.slot.scheduler.mqs)",
        "len(engine.scraper.slot.queue)",
        "len(engine.scraper.slot.active)",
        "engine.scraper.slot.active_size",
        "engine.scraper.slot.itemproc_size",
        "engine.scraper.slot.needs_backout()",
    ]

    checks = []
    for test in tests:
        try:
            checks += [(test, eval(test))]
        except Exception as e:
            checks += [(test, "%s (exception)" % type(e).__name__)]

    return checks

def format_engine_status(engine=None):
    checks = get_engine_status(engine)
    s = "Execution engine status\n\n"
    for test, result in checks:
        s += "%-47s : %s\n" % (test, result)
    s += "\n"

    return s

def print_engine_status(engine):
    print(format_engine_status(engine))
