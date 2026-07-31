from __future__ import annotations

import argparse
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import pytest

from scrapy.commands import parse
from scrapy.settings import Settings
from tests.utils.bases.commands import TestProjectBase
from tests.utils.cmdline import call, proc

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


class TestParseCommand(TestProjectBase):
    spider_name = "parse_spider"

    @pytest.fixture(autouse=True)
    def create_files(self, proj_path: Path) -> None:
        proj_mod_path = proj_path / self.project_name
        (proj_mod_path / "spiders" / "myspider.py").write_text(
            f"""
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.utils.test import get_from_asyncio_queue
import asyncio


class BaseSpider(scrapy.Spider):
    custom_settings = {{
        "DOWNLOAD_DELAY": 0,
    }}


class AsyncDefAsyncioReturnSpider(BaseSpider):
    name = "asyncdef_asyncio_return"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {{status}}")
        return [{{'id': 1}}, {{'id': 2}}]

class AsyncDefAsyncioReturnSingleElementSpider(BaseSpider):
    name = "asyncdef_asyncio_return_single_element"

    async def parse(self, response):
        await asyncio.sleep(0.1)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {{status}}")
        return {{'foo': 42}}

class AsyncDefAsyncioGenLoopSpider(BaseSpider):
    name = "asyncdef_asyncio_gen_loop"

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {{'foo': i}}
        self.logger.info(f"Got response {{response.status}}")

class AsyncDefAsyncioSpider(BaseSpider):
    name = "asyncdef_asyncio"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.debug(f"Got response {{status}}")

class AsyncDefAsyncioGenExcSpider(BaseSpider):
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
        }},
        "DOWNLOAD_DELAY": 0,
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

class RetryRequestSpider(BaseSpider):
    name = 'retry_request'

    def parse(self, response):
        if response.meta.get('retried'):
            yield {{'retried': True}}
            return
        response.meta['retried'] = True
        yield response.request.replace(dont_filter=True)

class CustomCallbackRetryRequestSpider(BaseSpider):
    name = 'retry_request_custom_callback'

    def parse(self, response):
        yield response.request.replace(
            callback=self.parse_retry,
            dont_filter=True,
        )

    def parse_retry(self, response):
        if response.meta.get('retried'):
            yield {{'retried_with_custom_callback': True}}
            return
        response.meta['retried'] = True
        yield response.request.replace(dont_filter=True)

class MyGoodCrawlSpider(CrawlSpider):
    name = 'goodcrawl{self.spider_name}'

    custom_settings = {{
        "DOWNLOAD_DELAY": 0,
    }}

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

    custom_settings = {{
        "DOWNLOAD_DELAY": 0,
    }}

    rules = (
        Rule(LinkExtractor(allow=r'/html'), callback='parse_item', follow=True),
    )

    def parse(self, response):
        return [scrapy.Item(), dict(foo='bar')]
""",
            encoding="utf-8",
        )

        (proj_mod_path / "pipelines.py").write_text(
            """
import logging

class MyPipeline:
    component_name = 'my_pipeline'

    def process_item(self, item):
        logging.info('It Works!')
        return item
""",
            encoding="utf-8",
        )

        with (proj_mod_path / "settings.py").open("a", encoding="utf-8") as f:
            f.write(
                f"""
ITEM_PIPELINES = {{'{self.project_name}.pipelines.MyPipeline': 1}}
"""
            )

    def test_spider_arguments(self, proj_path: Path, mockserver: MockServer) -> None:
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-a",
            "test_arg=1",
            "-c",
            "parse",
            "--verbose",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr

    def test_invalid_url(self, proj_path: Path) -> None:
        code, _, _ = proc(
            "parse", "--spider", self.spider_name, "not-a-url", cwd=proj_path
        )
        assert code != 0

    def test_curl(self, proj_path: Path, mockserver: MockServer) -> None:
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-a",
            "test_arg=1",
            "--curl",
            f"curl {mockserver.url('/html')}",
            "-c",
            "parse",
            "--verbose",
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr

    def test_curl_with_url(self, proj_path: Path, mockserver: MockServer) -> None:
        url = mockserver.url("/html")
        code, _, _ = proc(
            "parse",
            "--spider",
            self.spider_name,
            "--curl",
            f"curl {url}",
            url,
            cwd=proj_path,
        )
        assert code != 0

    def test_request_with_meta(self, proj_path: Path, mockserver: MockServer) -> None:
        raw_json_string = '{"foo" : "baz"}'
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "--meta",
            raw_json_string,
            "-c",
            "parse_request_with_meta",
            "--verbose",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr

        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-m",
            raw_json_string,
            "-c",
            "parse_request_with_meta",
            "--verbose",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr

    def test_request_with_cb_kwargs(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        raw_json_string = '{"foo" : "bar", "key": "value"}'
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "--cbkwargs",
            raw_json_string,
            "-c",
            "parse_request_with_cb_kwargs",
            "--verbose",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr
        assert (
            "DEBUG: request.callback signature: (response, foo=None, key=None)"
            in stderr
        )

    def test_request_without_meta(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-c",
            "parse_request_without_meta",
            "--nolinks",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: It Works!" in stderr

    def test_pipelines(self, proj_path: Path, mockserver: MockServer) -> None:
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "--pipelines",
            "-c",
            "parse",
            "--verbose",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "INFO: It Works!" in stderr

    def test_async_def_asyncio_parse_items_list(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio_return",
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "INFO: Got response 200" in stderr
        assert "{'id': 1}" in out
        assert "{'id': 2}" in out

    def test_async_def_asyncio_parse_items_single_element(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio_return_single_element",
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "INFO: Got response 200" in stderr
        assert "{'foo': 42}" in out

    def test_async_def_asyncgen_parse_loop(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio_gen_loop",
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "INFO: Got response 200" in stderr
        for i in range(10):
            assert f"{{'foo': {i}}}" in out

    def test_async_def_asyncgen_parse_exc(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio_gen_exc",
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "ValueError" in stderr
        for i in range(7):
            assert f"{{'foo': {i}}}" in out

    def test_async_def_asyncio_parse(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, _, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio",
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "DEBUG: Got response 200" in stderr

    def test_parse_items(self, proj_path: Path, mockserver: MockServer) -> None:
        _, out, _ = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-c",
            "parse",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "[{}, {'foo': 'bar'}]" in out

    def test_parse_items_no_callback_passed(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, _ = proc(
            "parse",
            "--spider",
            self.spider_name,
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "[{}, {'foo': 'bar'}]" in out

    def test_retry_response_request(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "retry_request",
            "-d",
            "2",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "RecursionError" not in stderr
        assert "{'retried': True}" in out

    def test_retry_response_request_with_custom_callback(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "retry_request_custom_callback",
            "-d",
            "3",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "RecursionError" not in stderr
        assert "{'retried_with_custom_callback': True}" in out

    def test_wrong_callback_passed(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-c",
            "dummy",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert re.search(r"# Scraped Items  -+\r?\n\[\]", out)
        assert "Cannot find callback" in stderr

    def test_crawlspider_matching_rule_callback_set(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        """If a rule matches the URL, use it's defined callback."""
        _, out, _ = proc(
            "parse",
            "--spider",
            "goodcrawl" + self.spider_name,
            "-r",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "[{}, {'foo': 'bar'}]" in out

    def test_crawlspider_matching_rule_default_callback(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        """If a rule match but it has no callback set, use the 'parse' callback."""
        _, out, _ = proc(
            "parse",
            "--spider",
            "goodcrawl" + self.spider_name,
            "-r",
            mockserver.url("/text"),
            cwd=proj_path,
        )
        assert "[{}, {'nomatch': 'default'}]" in out

    def test_spider_with_no_rules_attribute(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        """Using -r with a spider with no rule should not produce items."""
        _, out, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-r",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert re.search(r"# Scraped Items  -+\r?\n\[\]", out)
        assert "No CrawlSpider rules found" in stderr

    def test_crawlspider_missing_callback(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        _, out, _ = proc(
            "parse",
            "--spider",
            "badcrawl" + self.spider_name,
            "-r",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert re.search(r"# Scraped Items  -+\r?\n\[\]", out)

    def test_crawlspider_no_matching_rule(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        """The requested URL has no matching rule, so no items should be scraped"""
        _, out, stderr = proc(
            "parse",
            "--spider",
            "badcrawl" + self.spider_name,
            "-r",
            mockserver.url("/enc-gb18030"),
            cwd=proj_path,
        )
        assert re.search(r"# Scraped Items  -+\r?\n\[\]", out)
        assert "Cannot find a rule that matches" in stderr

    def test_crawlspider_not_exists_with_not_matched_url(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        assert call("parse", mockserver.url("/invalid_url"), cwd=proj_path) == 0

    def test_output_flag(self, proj_path: Path, mockserver: MockServer) -> None:
        """Checks if a file was created successfully having
        correct format containing correct data in it.
        """
        file_name = "data.json"
        file_path = proj_path / file_name
        proc(
            "parse",
            "--spider",
            self.spider_name,
            "-c",
            "parse",
            "-o",
            file_name,
            mockserver.url("/html"),
            cwd=proj_path,
        )

        assert file_path.exists()
        assert file_path.is_file()

        content = '[\n{},\n{"foo": "bar"}\n]'
        assert file_path.read_text(encoding="utf-8") == content

    @pytest.mark.parametrize("args", [(), ("not-a-url",), ("a:b", "c:d")])
    def test_bad_arguments(self, args: tuple[str, ...], proj_path: Path) -> None:
        returncode, out, _ = proc("parse", *args, cwd=proj_path)
        assert returncode == 2
        assert "Usage" in out

    @pytest.mark.parametrize(
        ("option", "message"),
        [
            ("--meta", "Invalid -m/--meta value"),
            ("-m", "Invalid -m/--meta value"),
            ("--cbkwargs", "Invalid --cbkwargs value"),
        ],
    )
    def test_invalid_json(
        self, option: str, message: str, proj_path: Path, mockserver: MockServer
    ) -> None:
        returncode, _, err = proc(
            "parse",
            "--spider",
            self.spider_name,
            option,
            "{invalid",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert returncode == 2
        assert message in err

    def test_unknown_spider(self, proj_path: Path, mockserver: MockServer) -> None:
        returncode, _, err = proc(
            "parse",
            "--spider",
            "nonexistent",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert returncode == 0, err
        assert "Unable to find spider: nonexistent" in err

    def test_spider_found_by_url(self, proj_path: Path, mockserver: MockServer) -> None:
        """Without --spider, the spider is chosen based on the URL."""
        url = mockserver.url("/html")
        # The spider name doubles as a domain of the spider, and it is matched
        # against the netloc of the URL, hence the port.
        (proj_path / self.project_name / "spiders" / "urlspider.py").write_text(
            f"""
import scrapy

class UrlSpider(scrapy.Spider):
    name = "{urlparse(url).netloc}"

    def parse(self, response):
        return [{{"found_by_url": True}}]
""",
            encoding="utf-8",
        )
        returncode, out, err = proc("parse", url, cwd=proj_path)
        assert returncode == 0, err
        assert "Unable to find spider for" not in err
        assert "{'found_by_url': True}" in out

    def test_legacy_item_processor(
        self, proj_path: Path, mockserver: MockServer
    ) -> None:
        """--pipelines supports an ITEM_PROCESSOR without process_item_async()."""
        (proj_path / self.project_name / "legacy.py").write_text(
            """
import logging

from twisted.internet.defer import succeed


class LegacyItemProcessor:
    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider):
        return succeed(None)

    def close_spider(self, spider):
        return succeed(None)

    def process_item(self, item, spider):
        logging.info("Legacy item processor!")
        return succeed(item)
""",
            encoding="utf-8",
        )
        _, _, stderr = proc(
            "parse",
            "--spider",
            self.spider_name,
            "--pipelines",
            "-c",
            "parse",
            "-s",
            f"ITEM_PROCESSOR={self.project_name}.legacy.LegacyItemProcessor",
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "INFO: Legacy item processor!" in stderr

    @pytest.mark.parametrize("verbose", [True, False])
    def test_no_items_no_links(
        self, verbose: bool, proj_path: Path, mockserver: MockServer
    ) -> None:
        args = ["--verbose"] if verbose else []
        _, out, err = proc(
            "parse",
            "--spider",
            self.spider_name,
            "-c",
            "parse",
            "--noitems",
            "--nolinks",
            *args,
            mockserver.url("/html"),
            cwd=proj_path,
        )
        assert "# Scraped Items" not in out, err
        assert "# Requests" not in out

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
        assert namespace.nolinks
        assert namespace.depth == 2
        assert namespace.spider == self.spider_name
        assert namespace.verbose

    def test_no_reactor(self, proj_path: Path, mockserver: MockServer) -> None:
        _, out, stderr = proc(
            "parse",
            "--spider",
            "asyncdef_asyncio_return",
            "-c",
            "parse",
            mockserver.url("/html"),
            "-s",
            "TWISTED_REACTOR_ENABLED=False",
            cwd=proj_path,
        )
        assert "INFO: Got response 200" in stderr
        assert "{'id': 1}" in out
        assert "{'id': 2}" in out
