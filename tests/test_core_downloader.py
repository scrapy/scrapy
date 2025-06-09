from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, cast

import OpenSSL.SSL
import pytest
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.protocols.policies import WrappingFactory
from twisted.trial import unittest
from twisted.web import server, static
from twisted.web.client import Agent, BrowserLikePolicyForHTTPS, readBody
from twisted.web.client import Response as TxResponse
from twisted.web.iweb import IBodyProducer

from scrapy.core.downloader import Slot
from scrapy.core.downloader.contextfactory import (
    ScrapyClientContextFactory,
    load_context_factory_from_settings,
)
from scrapy.core.downloader.handlers.http11 import _RequestBodyProducer
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler
from tests.mockserver import PayloadResource, ssl_context_factory


class TestSlot:
    def test_repr(self):
        slot = Slot(concurrency=8, delay=0.1, randomize_delay=True)
        assert repr(slot) == "Slot(concurrency=8, delay=0.10, randomize_delay=True)"


class TestContextFactoryBase(unittest.TestCase):
    context_factory = None

    def _listen(self, site):
        return reactor.listenSSL(
            0,
            site,
            contextFactory=self.context_factory or ssl_context_factory(),
            interface="127.0.0.1",
        )

    def getURL(self, path):
        return f"https://127.0.0.1:{self.portno}/{path}"

    def setUp(self):
        self.tmpname = Path(mkdtemp())
        (self.tmpname / "file").write_bytes(b"0123456789")
        r = static.File(str(self.tmpname))
        r.putChild(b"payload", PayloadResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = self._listen(self.wrapper)
        self.portno = self.port.getHost().port

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        shutil.rmtree(self.tmpname)

    @staticmethod
    async def get_page(
        url: str,
        client_context_factory: BrowserLikePolicyForHTTPS,
        body: str | None = None,
    ) -> bytes:
        agent = Agent(reactor, contextFactory=client_context_factory)
        body_producer = _RequestBodyProducer(body.encode()) if body else None
        response: TxResponse = cast(
            TxResponse,
            await maybe_deferred_to_future(
                agent.request(
                    b"GET",
                    url.encode(),
                    bodyProducer=cast(IBodyProducer, body_producer),
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
    @deferred_f_from_coro_f
    async def testPayload(self):
        s = "0123456789" * 10
        crawler = get_crawler()
        settings = Settings()
        client_context_factory = load_context_factory_from_settings(settings, crawler)
        body = await self.get_page(
            self.getURL("payload"), client_context_factory, body=s
        )
        assert body == to_bytes(s)

    def test_override_getContext(self):
        class MyFactory(ScrapyClientContextFactory):
            def getContext(
                self, hostname: Any = None, port: Any = None
            ) -> OpenSSL.SSL.Context:
                ctx: OpenSSL.SSL.Context = super().getContext(hostname, port)
                return ctx

        with warnings.catch_warnings(record=True) as w:
            MyFactory()
            assert len(w) == 1
            assert (
                "Overriding ScrapyClientContextFactory.getContext() is deprecated"
                in str(w[0].message)
            )


class TestContextFactoryTLSMethod(TestContextFactoryBase):
    async def _assert_factory_works(
        self, client_context_factory: ScrapyClientContextFactory
    ) -> None:
        s = "0123456789" * 10
        body = await self.get_page(
            self.getURL("payload"), client_context_factory, body=s
        )
        assert body == to_bytes(s)

    @deferred_f_from_coro_f
    async def test_setting_default(self):
        crawler = get_crawler()
        settings = Settings()
        client_context_factory = load_context_factory_from_settings(settings, crawler)
        assert client_context_factory._ssl_method == OpenSSL.SSL.SSLv23_METHOD
        await self._assert_factory_works(client_context_factory)

    def test_setting_none(self):
        crawler = get_crawler()
        settings = Settings({"DOWNLOADER_CLIENT_TLS_METHOD": None})
        with pytest.raises(KeyError):
            load_context_factory_from_settings(settings, crawler)

    def test_setting_bad(self):
        crawler = get_crawler()
        settings = Settings({"DOWNLOADER_CLIENT_TLS_METHOD": "bad"})
        with pytest.raises(KeyError):
            load_context_factory_from_settings(settings, crawler)

    @deferred_f_from_coro_f
    async def test_setting_explicit(self):
        crawler = get_crawler()
        settings = Settings({"DOWNLOADER_CLIENT_TLS_METHOD": "TLSv1.2"})
        client_context_factory = load_context_factory_from_settings(settings, crawler)
        assert client_context_factory._ssl_method == OpenSSL.SSL.TLSv1_2_METHOD
        await self._assert_factory_works(client_context_factory)

    @deferred_f_from_coro_f
    async def test_direct_from_crawler(self):
        # the setting is ignored
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "bad"})
        client_context_factory = build_from_crawler(ScrapyClientContextFactory, crawler)
        assert client_context_factory._ssl_method == OpenSSL.SSL.SSLv23_METHOD
        await self._assert_factory_works(client_context_factory)

    @deferred_f_from_coro_f
    async def test_direct_init(self):
        client_context_factory = ScrapyClientContextFactory(OpenSSL.SSL.TLSv1_2_METHOD)
        assert client_context_factory._ssl_method == OpenSSL.SSL.TLSv1_2_METHOD
        await self._assert_factory_works(client_context_factory)
