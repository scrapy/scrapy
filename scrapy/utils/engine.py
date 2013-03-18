"""Some debugging functions for working with the Scrapy engine"""

from time import time # used in global tests code

def get_engine_status(engine):
    """Return a report of the current engine status"""
    global_tests = [
        "time()-engine.start_time",
        "engine.has_capacity()",
        "engine.downloader.is_idle()",
        "len(engine.downloader.slots)",
        "len(engine.downloader.active)",
        "engine.scraper.is_idle()",
    ]
    spider_tests = [
        "engine.spider_is_idle(spider)",
        "engine.slots[spider].closing",
        "len(engine.slots[spider].inprogress)",
        "len(engine.slots[spider].scheduler.dqs or [])",
        "len(engine.slots[spider].scheduler.mqs)",
        "len(engine.scraper.slot.queue)",
        "len(engine.scraper.slot.active)",
        "engine.scraper.slot.active_size",
        "engine.scraper.slot.itemproc_size",
        "engine.scraper.slot.needs_backout()",
    ]

    status = {'global': [], 'spiders': {}}
    for test in global_tests:
        try:
            status['global'] += [(test, eval(test))]
        except Exception, e:
            status['global'] += [(test, "%s (exception)" % type(e).__name__)]
    for spider in engine.slots.keys():
        x = []
        for test in spider_tests:
            try:
                x += [(test, eval(test))]
            except Exception, e:
                x += [(test, "%s (exception)" % type(e).__name__)]
            status['spiders'][spider] = x
    return status

def format_engine_status(engine=None):
    status = get_engine_status(engine)
    s = "Execution engine status\n\n"
    for test, result in status['global']:
        s += "%-47s : %s\n" % (test, result)
    s += "\n"
    for spider, tests in status['spiders'].items():
        s += "Spider: %s\n" % spider
        for test, result in tests:
            s += "  %-50s : %s\n" % (test, result)
    return s

def print_engine_status(engine):
    print format_engine_status(engine)

