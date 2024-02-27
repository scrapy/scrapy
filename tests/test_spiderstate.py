import shutil
from datetime import datetime, timezone
from tempfile import mkdtemp

from twisted.trial import unittest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.spiderstate import SpiderState
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class SpiderStateTest(unittest.TestCase):
    def test_store_load(self):
        jobdir = mkdtemp()
        try:
            spider = Spider(name="default")
            dt = datetime.now(tz=timezone.utc)

            ss = SpiderState(jobdir)
            ss.spider_opened(spider)
            spider.state["one"] = 1
            spider.state["dt"] = dt
            ss.spider_closed(spider)

            spider2 = Spider(name="default")
            ss2 = SpiderState(jobdir)
            ss2.spider_opened(spider2)
            self.assertEqual(spider.state, {"one": 1, "dt": dt})
            ss2.spider_closed(spider2)
        finally:
            shutil.rmtree(jobdir)

    def test_state_attribute(self):
        # state attribute must be present if jobdir is not set, to provide a
        # consistent interface
        spider = Spider(name="default")
        ss = SpiderState()
        ss.spider_opened(spider)
        self.assertEqual(spider.state, {})
        ss.spider_closed(spider)

    def test_not_configured(self):
        crawler = get_crawler(Spider)
        self.assertRaises(NotConfigured, SpiderState.from_crawler, crawler)
