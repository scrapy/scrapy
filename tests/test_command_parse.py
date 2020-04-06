import os
from os.path import join, abspath
from twisted.internet import defer
from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest
from scrapy.utils.python import to_unicode
from tests.test_commands import CommandTest


def _textmode(bstr):
    """Normalize input the same as writing to a file
    and reading from it in text mode"""
    return to_unicode(bstr).replace(os.linesep, '\n')


class ParseCommandTest(ProcessTest, SiteTest, CommandTest):
    command = 'parse'

    def setUp(self):
        super(ParseCommandTest, self).setUp()
        self.spider_name = 'parse_spider'
        fname = abspath(join(self.proj_mod_path, 'spiders', 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule


class MySpider(scrapy.Spider):
    name = '{0}'

    def parse(self, response):
        if getattr(self, 'test_arg', None):
            self.logger.debug('It Works!')
        return [scrapy.Item(), dict(foo='bar')]

    def parse_request_with_meta(self, response):
        foo = response.meta.get('foo', 'bar')

        if foo == 'bar':
            self.logger.debug('It Does Not Work :(')
        else:
            self.logger.debug('It Works!')

    def parse_request_with_cb_kwargs(self, response, foo=None, key=None):
        if foo == 'bar' and key == 'value':
            self.logger.debug('It Works!')
        else:
            self.logger.debug('It Does Not Work :(')

    def parse_request_without_meta(self, response):
        foo = response.meta.get('foo', 'bar')

        if foo == 'bar':
            self.logger.debug('It Works!')
        else:
            self.logger.debug('It Does Not Work :(')

class MyGoodCrawlSpider(CrawlSpider):
    name = 'goodcrawl{0}'

    rules = (
        Rule(LinkExtractor(allow=r'/html'), callback='parse_item', follow=True),
        Rule(LinkExtractor(allow=r'/text'), follow=True),
    )

    def parse_item(self, response):
        return [scrapy.Item(), dict(foo='bar')]

    def parse(self, response):
        return [scrapy.Item(), dict(nomatch='default')]


class MyBadCrawlSpider(CrawlSpider):
    '''Spider which doesn't define a parse_item callback while using it in a rule.'''
    name = 'badcrawl{0}'

    rules = (
        Rule(LinkExtractor(allow=r'/html'), callback='parse_item', follow=True),
    )

    def parse(self, response):
        return [scrapy.Item(), dict(foo='bar')]
""".format(self.spider_name))

        fname = abspath(join(self.proj_mod_path, 'pipelines.py'))
        with open(fname, 'w') as f:
            f.write("""
import logging

class MyPipeline:
    component_name = 'my_pipeline'

    def process_item(self, item, spider):
        logging.info('It Works!')
        return item
""")

        fname = abspath(join(self.proj_mod_path, 'settings.py'))
        with open(fname, 'a') as f:
            f.write("""
ITEM_PIPELINES = {'%s.pipelines.MyPipeline': 1}
""" % self.project_name)

    @defer.inlineCallbacks
    def test_spider_arguments(self):
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '-a', 'test_arg=1',
                                           '-c', 'parse',
                                           '--verbose',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_request_with_meta(self):
        raw_json_string = '{"foo" : "baz"}'
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '--meta', raw_json_string,
                                           '-c', 'parse_request_with_meta',
                                           '--verbose',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '-m', raw_json_string,
                                           '-c', 'parse_request_with_meta',
                                           '--verbose',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_request_with_cb_kwargs(self):
        raw_json_string = '{"foo" : "bar", "key": "value"}'
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '--cbkwargs', raw_json_string,
                                           '-c', 'parse_request_with_cb_kwargs',
                                           '--verbose',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_request_without_meta(self):
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                          '-c', 'parse_request_without_meta',
                                          '--nolinks',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_pipelines(self):
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '--pipelines',
                                           '-c', 'parse',
                                           '--verbose',
                                           self.url('/html')])
        self.assertIn("INFO: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_parse_items(self):
        status, out, stderr = yield self.execute(
            ['--spider', self.spider_name, '-c', 'parse', self.url('/html')]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_parse_items_no_callback_passed(self):
        status, out, stderr = yield self.execute(
            ['--spider', self.spider_name, self.url('/html')]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_wrong_callback_passed(self):
        status, out, stderr = yield self.execute(
            ['--spider', self.spider_name, '-c', 'dummy', self.url('/html')]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""Cannot find callback""", _textmode(stderr))

    @defer.inlineCallbacks
    def test_crawlspider_matching_rule_callback_set(self):
        """If a rule matches the URL, use it's defined callback."""
        status, out, stderr = yield self.execute(
            ['--spider', 'goodcrawl' + self.spider_name, '-r', self.url('/html')]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_crawlspider_matching_rule_default_callback(self):
        """If a rule match but it has no callback set, use the 'parse' callback."""
        status, out, stderr = yield self.execute(
            ['--spider', 'goodcrawl' + self.spider_name, '-r', self.url('/text')]
        )
        self.assertIn("""[{}, {'nomatch': 'default'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_spider_with_no_rules_attribute(self):
        """Using -r with a spider with no rule should not produce items."""
        status, out, stderr = yield self.execute(
            ['--spider', self.spider_name, '-r', self.url('/html')]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""No CrawlSpider rules found""", _textmode(stderr))

    @defer.inlineCallbacks
    def test_crawlspider_missing_callback(self):
        status, out, stderr = yield self.execute(
            ['--spider', 'badcrawl' + self.spider_name, '-r', self.url('/html')]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")

    @defer.inlineCallbacks
    def test_crawlspider_no_matching_rule(self):
        """The requested URL has no matching rule, so no items should be scraped"""
        status, out, stderr = yield self.execute(
            ['--spider', 'badcrawl' + self.spider_name, '-r', self.url('/enc-gb18030')]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""Cannot find a rule that matches""", _textmode(stderr))
