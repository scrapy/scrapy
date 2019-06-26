from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
import six

from scrapy.http import Request
from scrapy.crawler import CrawlerRunner
from tests.spiders import MockServerSpider
from tests.mockserver import MockServer


class KeywordArgumentsSpider(MockServerSpider):

    name = 'kwargs'
    checks = list()

    def start_requests(self):
        data = {'key': 'value', 'number': 123}
        yield Request(self.mockserver.url('/first'), self.parse_first, cb_kwargs=data)
        yield Request(self.mockserver.url('/general_with'), self.parse_general, cb_kwargs=data)
        yield Request(self.mockserver.url('/general_without'), self.parse_general)
        yield Request(self.mockserver.url('/no_kwargs'), self.parse_no_kwargs)
        yield Request(self.mockserver.url('/default'), self.parse_default, cb_kwargs=data)
        yield Request(self.mockserver.url('/takes_less'), self.parse_takes_less, cb_kwargs=data)
        yield Request(self.mockserver.url('/takes_more'), self.parse_takes_more, cb_kwargs=data)

    def parse_first(self, response, key, number):
        self.checks.append(key == 'value')
        self.checks.append(number == 123)
        self.crawler.stats.inc_value('boolean_checks', 2)
        yield response.follow(
            self.mockserver.url('/two'),
            self.parse_second,
            cb_kwargs={'new_key': 'new_value'})

    def parse_second(self, response, new_key):
        self.checks.append(new_key == 'new_value')
        self.crawler.stats.inc_value('boolean_checks')

    def parse_general(self, response, **kwargs):
        if response.url.endswith('/general_with'):
            self.checks.append(kwargs['key'] == 'value')
            self.checks.append(kwargs['number'] == 123)
            self.crawler.stats.inc_value('boolean_checks', 2)
        elif response.url.endswith('/general_without'):
            self.checks.append(kwargs == {})
            self.crawler.stats.inc_value('boolean_checks')

    def parse_no_kwargs(self, response):
        self.checks.append(response.url.endswith('/no_kwargs'))
        self.crawler.stats.inc_value('boolean_checks')

    def parse_default(self, response, key, number=None, default=99):
        self.checks.append(response.url.endswith('/default'))
        self.checks.append(key == 'value')
        self.checks.append(number == 123)
        self.checks.append(default == 99)
        self.crawler.stats.inc_value('boolean_checks', 4)

    def parse_takes_less(self, response, key):
        """
        Should raise
        TypeError: parse_takes_less() got an unexpected keyword argument 'number'
        """

    def parse_takes_more(self, response, key, number, other):
        """
        Should raise
        TypeError: parse_takes_more() missing 1 required positional argument: 'other'
        """


class CallbackKeywordArgumentsTestCase(TestCase):

    maxDiff = None

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.runner = CrawlerRunner()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_callback_kwargs(self):
        crawler = self.runner.create_crawler(KeywordArgumentsSpider)
        with LogCapture() as log:
            yield crawler.crawl(mockserver=self.mockserver)
        self.assertTrue(all(crawler.spider.checks))
        self.assertEqual(len(crawler.spider.checks), crawler.stats.get_value('boolean_checks'))
        # check exceptions for argument mismatch
        exceptions = {}
        for line in log.records:
            for key in ('takes_less', 'takes_more'):
                if key in line.getMessage():
                    exceptions[key] = line
        self.assertEqual(exceptions['takes_less'].exc_info[0], TypeError)
        self.assertEqual(str(exceptions['takes_less'].exc_info[1]), "parse_takes_less() got an unexpected keyword argument 'number'")
        self.assertEqual(exceptions['takes_more'].exc_info[0], TypeError)
        # py2 and py3 messages are different
        exc_message = str(exceptions['takes_more'].exc_info[1])
        if six.PY2:
            self.assertEqual(exc_message, "parse_takes_more() takes exactly 5 arguments (4 given)")
        elif six.PY3:
            self.assertEqual(exc_message, "parse_takes_more() missing 1 required positional argument: 'other'")