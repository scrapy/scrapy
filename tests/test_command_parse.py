import argparse
import os
from pathlib import Path

from twisted.internet import defer

from scrapy.commands import parse
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.testproc import ProcessTest
from scrapy.utils.testsite import SiteTest
from tests.test_commands import CommandTest


def _textmode(bstr):
    """Normalize input the same as writing to a file
    and reading from it in text mode"""
    return to_unicode(bstr).replace(os.linesep, "\n")


class ParseCommandTest(ProcessTest, SiteTest, CommandTest):
    command = "parse"

    def setUp(self):
        super().setUp()
        self.spider_name = "parse_spider"
        (self.proj_mod_path / "spiders" / "myspider.py").write_text(
            f"""
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.utils.test import get_from_asyncio_queue
import asyncio


class AsyncDefAsyncioReturnSpider(scrapy.Spider):
    name = "asyncdef_asyncio_return"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {{status}}")
        return [{{'id': 1}}, {{'id': 2}}]

class AsyncDefAsyncioReturnSingleElementSpider(scrapy.Spider):
    name = "asyncdef_asyncio_return_single_element"

    async def parse(self, response):
        await asyncio.sleep(0.1)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {{status}}")
        return {{'foo': 42}}

class AsyncDefAsyncioGenLoopSpider(scrapy.Spider):
    name = "asyncdef_asyncio_gen_loop"

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {{'foo': i}}
        self.logger.info(f"Got response {{response.status}}")

class AsyncDefAsyncioSpider(scrapy.Spider):
    name = "asyncdef_asyncio"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.debug(f"Got response {{status}}")

class AsyncDefAsyncioGenExcSpider(scrapy.Spider):
    name = "asyncdef_asyncio_gen_exc"

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {{'foo': i}}
            if i > 5:
                raise ValueError("Stopping the processing")

class CallbackSignatureDownloaderMiddleware:
    def process_request(self, request, spider):
        from inspect import signature
        spider.logger.debug(f"request.callback signature: {{signature(request.callback)}}")


class MySpider(scrapy.Spider):
    name = '{self.spider_name}'

    custom_settings = {{
        "DOWNLOADER_MIDDLEWARES": {{
            CallbackSignatureDownloaderMiddleware: 0,
        }}
    }}

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
    name = 'goodcrawl{self.spider_name}'

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
    name = 'badcrawl{self.spider_name}'

    rules = (
        Rule(LinkExtractor(allow=r'/html'), callback='parse_item', follow=True),
    )

    def parse(self, response):
        return [scrapy.Item(), dict(foo='bar')]
""",
            encoding="utf-8",
        )

        (self.proj_mod_path / "pipelines.py").write_text(
            """
import logging

class MyPipeline:
    component_name = 'my_pipeline'

    def process_item(self, item, spider):
        logging.info('It Works!')
        return item
""",
            encoding="utf-8",
        )

        with (self.proj_mod_path / "settings.py").open("a", encoding="utf-8") as f:
            f.write(
                f"""
ITEM_PIPELINES = {{'{self.project_name}.pipelines.MyPipeline': 1}}
"""
            )

    @defer.inlineCallbacks
    def test_spider_arguments(self):
        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "-a",
                "test_arg=1",
                "-c",
                "parse",
                "--verbose",
                self.url("/html"),
            ]
        )
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_request_with_meta(self):
        raw_json_string = '{"foo" : "baz"}'
        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "--meta",
                raw_json_string,
                "-c",
                "parse_request_with_meta",
                "--verbose",
                self.url("/html"),
            ]
        )
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "-m",
                raw_json_string,
                "-c",
                "parse_request_with_meta",
                "--verbose",
                self.url("/html"),
            ]
        )
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_request_with_cb_kwargs(self):
        raw_json_string = '{"foo" : "bar", "key": "value"}'
        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "--cbkwargs",
                raw_json_string,
                "-c",
                "parse_request_with_cb_kwargs",
                "--verbose",
                self.url("/html"),
            ]
        )
        log = _textmode(stderr)
        self.assertIn("DEBUG: It Works!", log)
        self.assertIn(
            "DEBUG: request.callback signature: (response, foo=None, key=None)", log
        )

    @defer.inlineCallbacks
    def test_request_without_meta(self):
        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "-c",
                "parse_request_without_meta",
                "--nolinks",
                self.url("/html"),
            ]
        )
        self.assertIn("DEBUG: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_pipelines(self):
        _, _, stderr = yield self.execute(
            [
                "--spider",
                self.spider_name,
                "--pipelines",
                "-c",
                "parse",
                "--verbose",
                self.url("/html"),
            ]
        )
        self.assertIn("INFO: It Works!", _textmode(stderr))

    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_items_list(self):
        status, out, stderr = yield self.execute(
            [
                "--spider",
                "asyncdef_asyncio_return",
                "-c",
                "parse",
                self.url("/html"),
            ]
        )
        self.assertIn("INFO: Got response 200", _textmode(stderr))
        self.assertIn("{'id': 1}", _textmode(out))
        self.assertIn("{'id': 2}", _textmode(out))

    @defer.inlineCallbacks
    def test_async_def_asyncio_parse_items_single_element(self):
        status, out, stderr = yield self.execute(
            [
                "--spider",
                "asyncdef_asyncio_return_single_element",
                "-c",
                "parse",
                self.url("/html"),
            ]
        )
        self.assertIn("INFO: Got response 200", _textmode(stderr))
        self.assertIn("{'foo': 42}", _textmode(out))

    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse_loop(self):
        status, out, stderr = yield self.execute(
            [
                "--spider",
                "asyncdef_asyncio_gen_loop",
                "-c",
                "parse",
                self.url("/html"),
            ]
        )
        self.assertIn("INFO: Got response 200", _textmode(stderr))
        for i in range(10):
            self.assertIn(f"{{'foo': {i}}}", _textmode(out))

    @defer.inlineCallbacks
    def test_async_def_asyncgen_parse_exc(self):
        status, out, stderr = yield self.execute(
            [
                "--spider",
                "asyncdef_asyncio_gen_exc",
                "-c",
                "parse",
                self.url("/html"),
            ]
        )
        self.assertIn("ValueError", _textmode(stderr))
        for i in range(7):
            self.assertIn(f"{{'foo': {i}}}", _textmode(out))

    @defer.inlineCallbacks
    def test_async_def_asyncio_parse(self):
        _, _, stderr = yield self.execute(
            [
                "--spider",
                "asyncdef_asyncio",
                "-c",
                "parse",
                self.url("/html"),
            ]
        )
        self.assertIn("DEBUG: Got response 200", _textmode(stderr))

    @defer.inlineCallbacks
    def test_parse_items(self):
        status, out, stderr = yield self.execute(
            ["--spider", self.spider_name, "-c", "parse", self.url("/html")]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_parse_items_no_callback_passed(self):
        status, out, stderr = yield self.execute(
            ["--spider", self.spider_name, self.url("/html")]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_wrong_callback_passed(self):
        status, out, stderr = yield self.execute(
            ["--spider", self.spider_name, "-c", "dummy", self.url("/html")]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""Cannot find callback""", _textmode(stderr))

    @defer.inlineCallbacks
    def test_crawlspider_matching_rule_callback_set(self):
        """If a rule matches the URL, use it's defined callback."""
        status, out, stderr = yield self.execute(
            ["--spider", "goodcrawl" + self.spider_name, "-r", self.url("/html")]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_crawlspider_matching_rule_default_callback(self):
        """If a rule match but it has no callback set, use the 'parse' callback."""
        status, out, stderr = yield self.execute(
            ["--spider", "goodcrawl" + self.spider_name, "-r", self.url("/text")]
        )
        self.assertIn("""[{}, {'nomatch': 'default'}]""", _textmode(out))

    @defer.inlineCallbacks
    def test_spider_with_no_rules_attribute(self):
        """Using -r with a spider with no rule should not produce items."""
        status, out, stderr = yield self.execute(
            ["--spider", self.spider_name, "-r", self.url("/html")]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""No CrawlSpider rules found""", _textmode(stderr))

    @defer.inlineCallbacks
    def test_crawlspider_missing_callback(self):
        status, out, stderr = yield self.execute(
            ["--spider", "badcrawl" + self.spider_name, "-r", self.url("/html")]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")

    @defer.inlineCallbacks
    def test_crawlspider_no_matching_rule(self):
        """The requested URL has no matching rule, so no items should be scraped"""
        status, out, stderr = yield self.execute(
            ["--spider", "badcrawl" + self.spider_name, "-r", self.url("/enc-gb18030")]
        )
        self.assertRegex(_textmode(out), r"""# Scraped Items  -+\n\[\]""")
        self.assertIn("""Cannot find a rule that matches""", _textmode(stderr))

    @defer.inlineCallbacks
    def test_crawlspider_not_exists_with_not_matched_url(self):
        status, out, stderr = yield self.execute([self.url("/invalid_url")])
        self.assertEqual(status, 0)

    @defer.inlineCallbacks
    def test_output_flag(self):
        """Checks if a file was created successfully having
        correct format containing correct data in it.
        """
        file_name = "data.json"
        file_path = Path(self.proj_path, file_name)
        yield self.execute(
            [
                "--spider",
                self.spider_name,
                "-c",
                "parse",
                "-o",
                file_name,
                self.url("/html"),
            ]
        )

        self.assertTrue(file_path.exists())
        self.assertTrue(file_path.is_file())

        content = '[\n{},\n{"foo": "bar"}\n]'
        self.assertEqual(file_path.read_text(encoding="utf-8"), content)

    def test_parse_add_options(self):
        command = parse.Command()
        command.settings = Settings()
        parser = argparse.ArgumentParser(
            prog="scrapy",
            formatter_class=argparse.HelpFormatter,
            conflict_handler="resolve",
            prefix_chars="-",
        )
        command.add_options(parser)
        namespace = parser.parse_args(
            ["--verbose", "--nolinks", "-d", "2", "--spider", self.spider_name]
        )
        self.assertTrue(namespace.nolinks)
        self.assertEqual(namespace.depth, 2)
        self.assertEqual(namespace.spider, self.spider_name)
        self.assertTrue(namespace.verbose)
