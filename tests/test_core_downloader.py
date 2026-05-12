from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, cast

import OpenSSL.SSL
import pytest
from pytest_twisted import async_yield_fixture
from twisted.internet.protocol import Factory
from twisted.internet.protocol import Protocol as TxProtocol
from twisted.internet.ssl import optionsForClientTLS
from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol
from twisted.web import server, static
from twisted.web.client import Agent, BrowserLikePolicyForHTTPS, readBody
from twisted.web.client import Response as TxResponse

from scrapy.core.downloader import Downloader, Slot
from scrapy.core.downloader.contextfactory import (
    _load_context_factory_from_settings,
    _ScrapyClientContextFactory,
)
from scrapy.core.downloader.handlers.http11 import _RequestBodyProducer
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._deps_compat import (
    PYOPENSSL_SET_CIPHER_LIST_TMP_CONN,
    TWISTED_TLS_NEW_IMPL,
)
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.http_resources import PayloadResource
from tests.mockserver.utils import ssl_context_factory
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred
    from twisted.internet.ssl import ContextFactory
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
    @pytest.fixture
    def factory(self) -> _ScrapyClientContextFactory:
        crawler = get_crawler()
        return _load_context_factory_from_settings(crawler)

    @staticmethod
    def _get_dummy_protocol() -> TLSMemoryBIOProtocol:
        # from Twisted src/twisted/web/test/test_agent.py::dummyTLSProtocol()
        factory = TLSMemoryBIOFactory(
            optionsForClientTLS("example.com"), True, Factory.forProtocol(TxProtocol)
        )
        return factory.buildProtocol(None)

    @coroutine_test
    async def test_payload(
        self, factory: _ScrapyClientContextFactory, server_url: str
    ) -> None:
        s = "0123456789" * 10
        body = await self.get_page(server_url + "payload", factory, body=s)
        assert body == to_bytes(s)

    @pytest.mark.skipif(
        TWISTED_TLS_NEW_IMPL,
        reason="The context is not stored on this Twisted version",
    )
    def test_no_context_sharing(self, factory: _ScrapyClientContextFactory) -> None:
        """Every call to creatorForNetloc() should give a fresh context."""
        creator1 = factory.creatorForNetloc(b"website1.tld", 443)
        assert creator1._hostnameBytes == b"website1.tld"
        creator2 = factory.creatorForNetloc(b"website2.tld", 443)
        assert creator2._hostnameBytes == b"website2.tld"
        assert creator1._ctx is not creator2._ctx  # type: ignore[attr-defined]

    def test_no_context_sharing_with_conn(
        self, factory: _ScrapyClientContextFactory
    ) -> None:
        """Like test_no_context_sharing() but get the context from a connection."""
        creator1 = factory.creatorForNetloc(b"website1.tld", 443)
        assert creator1._hostnameBytes == b"website1.tld"
        conn1 = creator1.clientConnectionForTLS(self._get_dummy_protocol())

        creator2 = factory.creatorForNetloc(b"website2.tld", 443)
        assert creator2._hostnameBytes == b"website2.tld"
        conn2 = creator2.clientConnectionForTLS(self._get_dummy_protocol())

        assert conn1.get_context() is not conn2.get_context()

    @pytest.mark.skipif(
        PYOPENSSL_SET_CIPHER_LIST_TMP_CONN,
        reason="Fails or doesn't make sense on this pyOpenSSL version",
    )
    def test_no_immutable_ctx_warning(
        self, factory: _ScrapyClientContextFactory
    ) -> None:
        """There should be no pyOpenSSL context modification warning.

        pyOpenSSL < 25.1.0 doesn't produce this warning, and on 25.1.0 it's
        always produced due to
        https://github.com/scrapy/scrapy/issues/6859#issuecomment-4294917851.
        """
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                category=DeprecationWarning,
                message="Attempting to mutate a Context after a Connection was created",
            )
            factory.creatorForNetloc(b"website.tld", 443)

    def test_ctx_flags(self, factory: _ScrapyClientContextFactory) -> None:
        """The context should have the expected flags set."""
        creator = factory.creatorForNetloc(b"website.tld", 443)
        conn = creator.clientConnectionForTLS(self._get_dummy_protocol())
        ctx = conn.get_context()
        # fragile but pyOpenSSL doesn't have Context.get_options()
        options = OpenSSL.SSL._lib.SSL_CTX_get_options(ctx._context)  # type: ignore[attr-defined]
        assert options & 0x4  # OP_LEGACY_SERVER_CONNECT


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
