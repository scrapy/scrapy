import unittest

from scrapy.core.scheduler import Scheduler, RoundRobinScheduler
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.http import Request
from scrapy.dupefilters import RFPDupeFilter


class BaseSchedulerTestCase(unittest.TestCase):

    Scheduler = None

    def setUp(self):
        self.crawler = get_crawler(Spider, None)
        self.spider = self.crawler._create_spider('foo')
        self.scheduler = self.Scheduler.from_crawler(self.crawler)
        self.scheduler.open(self.spider)

    def tearDown(self):
        self.scheduler.close('finished')


class SchedulerTestCase(BaseSchedulerTestCase):
    Scheduler = Scheduler
    def test_scheduler(self):
        self.scheduler.enqueue_request(Request("http://foo.com/a"))
        self.scheduler.enqueue_request(Request("http://foo.com/b"))

        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/b")
        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/a")

    def test_scheduler_priorities(self):
        self.scheduler.enqueue_request(Request("http://foo.com/a", priority=1))
        self.scheduler.enqueue_request(Request("http://foo.com/b", priority=0))

        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/a")
        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/b")


class RoundRobinSchedulerTestCase(BaseSchedulerTestCase):

    Scheduler = RoundRobinScheduler

    def test_scheduler(self):
        self.scheduler.enqueue_request(Request("http://foo.com/a"))
        self.scheduler.enqueue_request(Request("http://foo.com/b"))
        self.scheduler.enqueue_request(Request("http://bar.com/a"))
        self.scheduler.enqueue_request(Request("http://bar.com/b"))

        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/b")
        self.assertEqual(self.scheduler.next_request().url, "http://bar.com/b")
        self.assertEqual(self.scheduler.next_request().url, "http://foo.com/a")
        self.assertEqual(self.scheduler.next_request().url, "http://bar.com/a")


if __name__ == '__main__':
    unittest.main()
