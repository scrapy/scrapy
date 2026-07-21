from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from zope.interface.exceptions import MultipleInvalid

from scrapy.crawler import (
    AsyncCrawlerProcess,
    AsyncCrawlerRunner,
    Crawler,
    CrawlerProcess,
    CrawlerRunner,
    CrawlerRunnerBase,
)
from scrapy.settings import Settings
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_reactor_settings
from tests.spiders import ExceptionSpider, NoRequestsSpider, SimpleSpider
from tests.utils import assert_option_is_default
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy import Spider
    from tests.mockserver.http import MockServer


class SpiderLoaderWithWrongInterface:
    def unneeded_method(self) -> None:
        pass


class TestCrawlerRunner:
    def test_spider_manager_verify_interface(self) -> None:
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            CrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self) -> None:
        runner = CrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        assert_option_is_default(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self) -> None:
        runner = CrawlerRunner()
        assert_option_is_default(runner.settings, "RETRY_ENABLED")


class TestAsyncCrawlerRunner:
    def test_spider_manager_verify_interface(self) -> None:
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            AsyncCrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self) -> None:
        runner = AsyncCrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        assert_option_is_default(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self) -> None:
        runner = AsyncCrawlerRunner()
        assert_option_is_default(runner.settings, "RETRY_ENABLED")


class TestCrawlerProcess:
    def test_crawler_process_accepts_dict(self) -> None:
        runner = CrawlerProcess({"foo": "bar"}, install_root_handler=False)
        assert runner.settings["foo"] == "bar"
        assert_option_is_default(runner.settings, "RETRY_ENABLED")

    def test_crawler_process_accepts_None(self) -> None:
        runner = CrawlerProcess(install_root_handler=False)
        assert_option_is_default(runner.settings, "RETRY_ENABLED")


@pytest.mark.only_asyncio
class TestAsyncCrawlerProcess:
    def test_crawler_process_accepts_dict(self, reactor_pytest: str) -> None:
        runner = AsyncCrawlerProcess(
            {"foo": "bar", "TWISTED_REACTOR_ENABLED": reactor_pytest != "none"},
            install_root_handler=False,
        )
        assert runner.settings["foo"] == "bar"
        assert_option_is_default(runner.settings, "RETRY_ENABLED")

    @pytest.mark.requires_reactor  # can't pass TWISTED_REACTOR_ENABLED=False
    def test_crawler_process_accepts_None(self) -> None:
        runner = AsyncCrawlerProcess(install_root_handler=False)
        assert_option_is_default(runner.settings, "RETRY_ENABLED")


@pytest.mark.requires_reactor  # CrawlerRunner requires a reactor
class TestCrawlerRunnerHasSpider:
    @pytest.fixture
    def runner(self) -> CrawlerRunnerBase:
        return CrawlerRunner(get_reactor_settings())

    @staticmethod
    async def _crawl(runner: CrawlerRunnerBase, spider: type[Spider]) -> None:
        await ensure_awaitable(runner.crawl(spider))

    @coroutine_test
    async def test_crawler_runner_bootstrap_successful(
        self, runner: CrawlerRunnerBase
    ) -> None:
        await self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_successful_for_several(
        self, runner: CrawlerRunnerBase
    ) -> None:
        await self._crawl(runner, NoRequestsSpider)
        await self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_failed(
        self, runner: CrawlerRunnerBase
    ) -> None:
        try:
            await self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        assert runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_failed_for_several(
        self, runner: CrawlerRunnerBase
    ) -> None:
        try:
            await self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        await self._crawl(runner, NoRequestsSpider)

        assert runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_asyncio_enabled_true(
        self, reactor_pytest: str
    ) -> None:
        if reactor_pytest != "asyncio":
            runner = CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
            with pytest.raises(
                Exception,
                match=r"The installed reactor \(.*?\) does not match the requested one \(.*?\)",
            ):
                await self._crawl(runner, NoRequestsSpider)
        else:
            runner = CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
            await self._crawl(runner, NoRequestsSpider)


@pytest.mark.only_asyncio
class TestAsyncCrawlerRunnerHasSpider(TestCrawlerRunnerHasSpider):
    @pytest.fixture
    def runner(self) -> CrawlerRunnerBase:
        return AsyncCrawlerRunner(get_reactor_settings())

    def test_crawler_runner_asyncio_enabled_true(self) -> None:  # type: ignore[override]
        pytest.skip("This test is only for CrawlerRunner")


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_runner_settings_applied_to_crawler_instance(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    runner = runner_cls({"FOO": "runner"})
    crawler = Crawler(DefaultSpider)
    result = runner.create_crawler(crawler)
    assert result is crawler
    assert result.settings["FOO"] == "runner"


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_spider_custom_settings_override_runner(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    class MySpider(DefaultSpider):
        custom_settings = {"FOO": "spider"}

    runner = runner_cls({"FOO": "runner"})
    crawler = Crawler(MySpider)
    runner.create_crawler(crawler)
    assert crawler.settings["FOO"] == "spider"


def test_create_crawler_instance_consistent_with_spider_class() -> None:
    runner = AsyncCrawlerRunner({"FOO": "runner"})

    crawler_from_class = runner.create_crawler(DefaultSpider)

    pre_built = Crawler(DefaultSpider)
    runner.create_crawler(pre_built)

    assert crawler_from_class.settings["FOO"] == "runner"
    assert pre_built.settings["FOO"] == "runner"


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_create_crawler_rejects_spider_object(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    runner = runner_cls()
    with pytest.raises(ValueError, match="cannot be a spider object"):
        runner.create_crawler(DefaultSpider())  # type: ignore[arg-type]


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_crawl_rejects_spider_object(runner_cls: type[CrawlerRunnerBase]) -> None:
    runner = runner_cls()
    with pytest.raises(ValueError, match="cannot be a spider object"):
        runner.crawl(DefaultSpider())  # type: ignore[arg-type]


@coroutine_test
async def test_crawlerrunner_accepts_crawler(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer
) -> None:
    crawler = Crawler(SimpleSpider, get_reactor_settings())
    runner = CrawlerRunner()
    with caplog.at_level(logging.DEBUG):
        await maybe_deferred_to_future(
            runner.crawl(
                crawler,
                mockserver.url("/status?n=200"),
                mockserver=mockserver,
            )
        )
    assert "Got response 200" in caplog.text


@coroutine_test
async def test_crawl_multiple(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer
) -> None:
    settings_dict = get_reactor_settings()
    runner_cls = (
        CrawlerRunner
        if settings_dict.get("TWISTED_REACTOR_ENABLED", True)
        else AsyncCrawlerRunner
    )
    runner = runner_cls(settings_dict)
    runner.crawl(
        SimpleSpider,
        mockserver.url("/status?n=200"),
        mockserver=mockserver,
    )
    runner.crawl(
        SimpleSpider,
        mockserver.url("/status?n=503"),
        mockserver=mockserver,
    )

    with caplog.at_level(logging.DEBUG):
        await ensure_awaitable(runner.join())

    assert "Got response 200" in caplog.text
    assert "Gave up retrying" in caplog.text
