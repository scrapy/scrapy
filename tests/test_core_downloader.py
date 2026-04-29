from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import OpenSSL.SSL
import pytest
from pytest_twisted import async_yield_fixture
from twisted.internet.defer import CancelledError, Deferred
from twisted.web import server, static
from twisted.web.client import Agent, BrowserLikePolicyForHTTPS, readBody
from twisted.web.client import Response as TxResponse

from scrapy import Request
from scrapy.core.downloader import Downloader, Slot
from scrapy.core.downloader.contextfactory import (
    _load_context_factory_from_settings,
    _ScrapyClientContextFactory,
)
from scrapy.core.downloader.handlers.http11 import _RequestBodyProducer
from scrapy.exceptions import DownloadCancelledError, ScrapyDeprecationWarning
from scrapy.utils._deps_compat import PYOPENSSL_SET_CIPHER_LIST_TMP_CONN
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http_resources import PayloadResource
from tests.mockserver.utils import ssl_context_factory
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from twisted.internet.ssl import ContextFactory
    from twisted.python.failure import Failure
    from twisted.web.iweb import IBodyProducer


class TestSlot:
    def test_repr(self):
        slot = Slot(concurrency=8, delay=0.1, randomize_delay=True)
        assert repr(slot) == "Slot(concurrency=8, delay=0.1, randomize_delay=True)"


@pytest.mark.requires_reactor  # this test is related to the Twisted HTTP code
class TestContextFactoryBase:
    context_factory: ContextFactory | None = None

    @async_yield_fixture
    async def server_url(self, tmp_path):
        (tmp_path / "file").write_bytes(b"0123456789")
        r = static.File(str(tmp_path))
        r.putChild(b"payload", PayloadResource())
        site = server.Site(r, timeout=None)
        port = self._listen(site)
        portno = port.getHost().port

        yield f"https://127.0.0.1:{portno}/"

        await port.stopListening()

    def _listen(self, site):
        from twisted.internet import reactor

        return reactor.listenSSL(
            0,
            site,
            contextFactory=self.context_factory or ssl_context_factory(),
            interface="127.0.0.1",
        )

    @staticmethod
    async def get_page(
        url: str,
        client_context_factory: BrowserLikePolicyForHTTPS,
        body: str | None = None,
    ) -> bytes:
        from twisted.internet import reactor

        agent = Agent(reactor, contextFactory=client_context_factory)
        body_producer = _RequestBodyProducer(body.encode()) if body else None
        response: TxResponse = cast(
            "TxResponse",
            await maybe_deferred_to_future(
                agent.request(
                    b"GET",
                    url.encode(),
                    bodyProducer=cast("IBodyProducer", body_producer),
                )
            ),
        )
        with warnings.catch_warnings():
            # https://github.com/twisted/twisted/issues/8227
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*does not have an abortConnection method",
            )
            d: Deferred[bytes] = readBody(response)  # type: ignore[arg-type]
        return await maybe_deferred_to_future(d)


class TestContextFactory(TestContextFactoryBase):
    @coroutine_test
    async def test_payload(self, server_url: str) -> None:
        s = "0123456789" * 10
        crawler = get_crawler()
        client_context_factory = _load_context_factory_from_settings(crawler)
        body = await self.get_page(
            server_url + "payload", client_context_factory, body=s
        )
        assert body == to_bytes(s)

    def test_no_context_sharing(self) -> None:
        """Every call to creatorForNetloc() should give a fresh context."""
        crawler = get_crawler()
        client_context_factory: _ScrapyClientContextFactory = (
            _load_context_factory_from_settings(crawler)
        )
        creator1 = client_context_factory.creatorForNetloc(b"website1.tld", 443)
        assert creator1._hostnameBytes == b"website1.tld"
        creator2 = client_context_factory.creatorForNetloc(b"website2.tld", 443)
        assert creator2._hostnameBytes == b"website2.tld"
        assert creator1._ctx is not creator2._ctx

    @pytest.mark.skipif(
        PYOPENSSL_SET_CIPHER_LIST_TMP_CONN,
        reason="Fails or doesn't make sense on this pyOpenSSL version",
    )
    def test_no_immutable_ctx_warning(self) -> None:
        """There should be no pyOpenSSL context modification warning.

        pyOpenSSL < 25.1.0 doesn't produce this warning, and on 25.1.0 it's
        always produced due to
        https://github.com/scrapy/scrapy/issues/6859#issuecomment-4294917851.
        """
        crawler = get_crawler()
        client_context_factory: _ScrapyClientContextFactory = (
            _load_context_factory_from_settings(crawler)
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                category=DeprecationWarning,
                message="Attempting to mutate a Context after a Connection was created",
            )
            client_context_factory.creatorForNetloc(b"website.tld", 443)


class TestContextFactoryTLSMethod(TestContextFactoryBase):
    async def _assert_factory_works(
        self, server_url: str, client_context_factory: _ScrapyClientContextFactory
    ) -> None:
        s = "0123456789" * 10
        body = await self.get_page(
            server_url + "payload", client_context_factory, body=s
        )
        assert body == to_bytes(s)

    @coroutine_test
    async def test_setting_default(self, server_url: str) -> None:
        crawler = get_crawler()
        client_context_factory = _load_context_factory_from_settings(crawler)
        assert client_context_factory._ssl_method == OpenSSL.SSL.SSLv23_METHOD
        await self._assert_factory_works(server_url, client_context_factory)

    def test_setting_none(self):
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": None})
        with pytest.raises(KeyError):
            _load_context_factory_from_settings(crawler)

    def test_setting_bad(self):
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "bad"})
        with pytest.raises(KeyError):
            _load_context_factory_from_settings(crawler)

    @coroutine_test
    async def test_setting_explicit(self, server_url: str) -> None:
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "TLSv1.2"})
        client_context_factory = _load_context_factory_from_settings(crawler)
        assert client_context_factory._ssl_method == OpenSSL.SSL.TLSv1_2_METHOD
        await self._assert_factory_works(server_url, client_context_factory)

    @coroutine_test
    async def test_direct_from_crawler(self, server_url: str) -> None:
        # the setting is ignored
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "bad"})
        client_context_factory = build_from_crawler(
            _ScrapyClientContextFactory, crawler
        )
        assert client_context_factory._ssl_method == OpenSSL.SSL.SSLv23_METHOD
        await self._assert_factory_works(server_url, client_context_factory)

    @coroutine_test
    async def test_direct_init(self, server_url: str) -> None:
        client_context_factory = _ScrapyClientContextFactory(OpenSSL.SSL.TLSv1_2_METHOD)
        assert client_context_factory._ssl_method == OpenSSL.SSL.TLSv1_2_METHOD
        await self._assert_factory_works(server_url, client_context_factory)


@coroutine_test
async def test_fetch_deprecated_spider_arg():
    class CustomDownloader(Downloader):
        def fetch(self, request, spider):  # pylint: disable=signature-differs
            return super().fetch(request, spider)

    crawler = get_crawler(DefaultSpider, {"DOWNLOADER": CustomDownloader})
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"The fetch\(\) method of .+\.CustomDownloader requires a spider argument",
    ):
        await crawler.crawl_async()


@coroutine_test
async def test_stop_async_drops_queued_requests() -> None:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    slot = Slot(concurrency=1, delay=0, randomize_delay=False)
    downloader.slots["example.com"] = slot

    request = Request("https://example.com")
    queue_dfd: Deferred = Deferred()
    failures: list[Failure] = []
    queue_dfd.addErrback(failures.append)
    slot.queue.append((request, queue_dfd))

    dropped = await downloader.stop_async()
    assert dropped == 1
    assert len(failures) == 1
    assert failures[0].check(DownloadCancelledError)


@coroutine_test
async def test_stop_async_rejects_new_requests() -> None:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)

    await downloader.stop_async()

    with pytest.raises(
        DownloadCancelledError,
        match="not accepting new requests",
    ):
        await downloader._enqueue_request(Request("https://example.com"))


@coroutine_test
async def test_wait_for_download_errbacks_queue_deferred_on_error() -> None:
    crawler = get_crawler(DefaultSpider)
    downloader = Downloader(crawler)
    slot = Slot(concurrency=1, delay=0, randomize_delay=False)

    queue_dfd: Deferred = Deferred()
    failures: list[Failure] = []
    queue_dfd.addErrback(failures.append)

    with patch.object(downloader, "_download", side_effect=RuntimeError("boom")):
        await downloader._wait_for_download(
            slot,
            Request("https://example.com"),
            queue_dfd,
        )

    assert len(failures) == 1
    assert failures[0].check(RuntimeError)


@coroutine_test
async def test_wait_for_download_keeps_called_queue_deferred_on_error() -> None:
    crawler = get_crawler(DefaultSpider)
    downloader = Downloader(crawler)
    slot = Slot(concurrency=1, delay=0, randomize_delay=False)

    queue_dfd: Deferred = Deferred()
    queue_dfd.callback(None)

    with patch.object(downloader, "_download", side_effect=RuntimeError("boom")):
        await downloader._wait_for_download(
            slot,
            Request("https://example.com"),
            queue_dfd,
        )

    assert queue_dfd.called


@coroutine_test
async def test_stop_async_skips_called_queued_deferred() -> None:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    downloader = Downloader(crawler)
    slot = Slot(concurrency=1, delay=0, randomize_delay=False)
    downloader.slots["example.com"] = slot

    queue_dfd: Deferred = Deferred()
    queue_dfd.callback(None)
    slot.queue.append((Request("https://example.com"), queue_dfd))

    dropped = await downloader.stop_async()
    assert dropped == 1


@coroutine_test
async def test_stop_async_cancels_pending_download_tasks() -> None:
    crawler = get_crawler(DefaultSpider)
    downloader = Downloader(crawler)

    done_dfd: Deferred = Deferred()
    done_dfd.callback(None)

    pending_dfd: Deferred = Deferred()
    failures: list[Failure] = []
    pending_dfd.addErrback(failures.append)

    downloader._download_tasks[Request("https://done.example")] = done_dfd
    downloader._download_tasks[Request("https://pending.example")] = pending_dfd

    dropped = await downloader.stop_async()

    assert dropped == 1
    assert len(failures) == 1
    assert failures[0].check(CancelledError)
