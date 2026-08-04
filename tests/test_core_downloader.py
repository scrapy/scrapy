from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, cast

import OpenSSL.SSL
import pytest
from pytest_twisted import async_yield_fixture
from twisted.internet.endpoints import HostnameEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.protocol import Protocol as TxProtocol
from twisted.internet.ssl import AcceptableCiphers, optionsForClientTLS
from twisted.protocols.tls import TLSMemoryBIOFactory, TLSMemoryBIOProtocol
from twisted.web import server, static
from twisted.web.client import (
    URI,
    Agent,
    BrowserLikePolicyForHTTPS,
    _StandardEndpointFactory,
    readBody,
)
from twisted.web.client import Response as TxResponse

from scrapy import Request, Spider
from scrapy.core.downloader import Downloader, Slot, tls
from scrapy.core.downloader._idna_patch import (
    _install_twisted_idna_fallbacks,
    _safe_hostname_bytes,
)
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
from tests import IDNA_REJECTED_HOSTNAMES
from tests.mockserver.http_resources import PayloadResource, put_child
from tests.mockserver.utils import ssl_context_factory
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred
    from twisted.internet.interfaces import IListeningPort
    from twisted.web.iweb import IBodyProducer

    from scrapy.http import Response


@pytest.fixture(autouse=True, scope="module")
def _twisted_idna_fallbacks() -> None:
    """The download handlers install these when built; the tests below exercise
    the patched Twisted helpers directly, so they need them installed too."""
    _install_twisted_idna_fallbacks()


class TestSlot:
    def test_repr(self):
        slot = Slot(concurrency=8, delay=0.1, randomize_delay=True)
        assert repr(slot) == "Slot(concurrency=8, delay=0.1, randomize_delay=True)"


@pytest.mark.requires_reactor  # this test is related to the Twisted HTTP code
class TestContextFactoryBase:
    @async_yield_fixture
    async def server_url(self, tmp_path):
        (tmp_path / "file").write_bytes(b"0123456789")
        r = static.File(str(tmp_path))
        put_child(r, b"payload", PayloadResource())
        site = server.Site(r, timeout=None)
        port = self._listen(site)
        portno = port.getHost().port

        yield f"https://127.0.0.1:{portno}/"

        await port.stopListening()

    def _listen(self, site: server.Site) -> IListeningPort:
        from twisted.internet import reactor

        return reactor.listenSSL(
            0,
            site,
            contextFactory=ssl_context_factory(),
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

    @pytest.mark.parametrize("hostname", [h.encode() for h in IDNA_REJECTED_HOSTNAMES])
    def test_idna_rejected_hostname(
        self, factory: _ScrapyClientContextFactory, hostname: bytes
    ) -> None:
        """Hostnames rejected by the idna package, such as punycode emoji
        domains or domains with underscores, should work."""
        creator = factory.creatorForNetloc(hostname, 443)
        assert creator._hostnameBytes == hostname
        assert creator._hostnameASCII == hostname.decode("ascii")
        assert creator._hostnameIsDnsName is True
        conn = creator.clientConnectionForTLS(self._get_dummy_protocol())
        assert conn is not None

    @pytest.mark.parametrize("hostname", [h.encode() for h in IDNA_REJECTED_HOSTNAMES])
    def test_idna_rejected_hostname_verify_certificates(self, hostname: bytes) -> None:
        """Same as test_idna_rejected_hostname() but with certificate
        verification enabled, which uses plain optionsForClientTLS()."""
        crawler = get_crawler(settings_dict={"DOWNLOAD_VERIFY_CERTIFICATES": True})
        factory = cast(
            "_ScrapyClientContextFactory", _load_context_factory_from_settings(crawler)
        )
        creator = factory.creatorForNetloc(hostname, 443)
        assert creator._hostnameBytes == hostname
        assert creator._hostnameASCII == hostname.decode("ascii")

    def test_ctx_flags(self, factory: _ScrapyClientContextFactory) -> None:
        """The context should have the expected flags set."""
        creator = factory.creatorForNetloc(b"website.tld", 443)
        conn = creator.clientConnectionForTLS(self._get_dummy_protocol())
        ctx = conn.get_context()
        # fragile but pyOpenSSL doesn't have Context.get_options()
        options = OpenSSL.SSL._lib.SSL_CTX_get_options(ctx._context)  # type: ignore[attr-defined]
        assert options & 0x4  # OP_LEGACY_SERVER_CONNECT


class TestContextFactoryCiphers(TestContextFactoryBase):
    async def _assert_factory_works(
        self, server_url: str, client_context_factory: _ScrapyClientContextFactory
    ) -> None:
        s = "0123456789" * 10
        body = await self.get_page(
            server_url + "payload", client_context_factory, body=s
        )
        assert body == to_bytes(s)

    def test_default(self) -> None:
        """The default 'DEFAULT' value is passed to Twisted as is."""
        crawler = get_crawler()
        factory = build_from_crawler(_ScrapyClientContextFactory, crawler)
        assert factory.tls_ciphers is not None
        # OpenSSLAcceptableCiphers has no __eq__, so compare the parsed ciphers.
        assert (
            factory.tls_ciphers._ciphers
            == AcceptableCiphers.fromOpenSSLCipherString("DEFAULT")._ciphers
        )
        assert factory._get_cert_options_kwargs()["acceptableCiphers"] is not None

    def test_custom(self) -> None:
        crawler = get_crawler(
            settings_dict={"DOWNLOADER_CLIENT_TLS_CIPHERS": "CAMELLIA256-SHA"}
        )
        factory = build_from_crawler(_ScrapyClientContextFactory, crawler)
        assert factory.tls_ciphers is not None
        assert (
            factory.tls_ciphers._ciphers
            == AcceptableCiphers.fromOpenSSLCipherString("CAMELLIA256-SHA")._ciphers
        )

    @coroutine_test
    async def test_none(self, server_url: str) -> None:
        """A None value enables the Twisted default ciphers."""
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_CIPHERS": None})
        factory = build_from_crawler(_ScrapyClientContextFactory, crawler)
        assert factory.tls_ciphers is None
        assert factory._get_cert_options_kwargs()["acceptableCiphers"] is None
        await self._assert_factory_works(server_url, factory)


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
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match="Setting DOWNLOADER_CLIENT_TLS_METHOD to a non-default value is deprecated",
            ),
            pytest.raises(KeyError),
        ):
            _load_context_factory_from_settings(crawler)

    def test_setting_bad(self):
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "bad"})
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match="Setting DOWNLOADER_CLIENT_TLS_METHOD to a non-default value is deprecated",
            ),
            pytest.raises(KeyError),
        ):
            _load_context_factory_from_settings(crawler)

    @pytest.mark.filterwarnings(
        r"ignore:Passing method to twisted\.internet\.ssl\.CertificateOptions:DeprecationWarning"
    )
    @coroutine_test
    async def test_setting_explicit(self, server_url: str) -> None:
        crawler = get_crawler(settings_dict={"DOWNLOADER_CLIENT_TLS_METHOD": "TLSv1.2"})
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="Setting DOWNLOADER_CLIENT_TLS_METHOD to a non-default value is deprecated",
        ):
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

    @pytest.mark.filterwarnings(
        r"ignore:Passing method to twisted\.internet\.ssl\.CertificateOptions:DeprecationWarning"
    )
    @coroutine_test
    async def test_direct_init(self, server_url: str) -> None:
        client_context_factory = _ScrapyClientContextFactory(OpenSSL.SSL.TLSv1_2_METHOD)
        assert client_context_factory._ssl_method == OpenSSL.SSL.TLSv1_2_METHOD
        await self._assert_factory_works(server_url, client_context_factory)


@pytest.mark.parametrize(
    ("concurrency", "active", "expected"),
    [
        (2, 1, False),
        (2, 2, True),
        (0, 0, False),
        (0, 2, False),
    ],
)
def test_needs_backout(concurrency: int, active: int, expected: bool) -> None:
    crawler = get_crawler(settings_dict={"CONCURRENT_REQUESTS": concurrency})
    downloader = Downloader(crawler)
    downloader.active = {Request(f"https://example.com/{i}") for i in range(active)}
    assert downloader.needs_backout() is expected
    downloader.close()


class TestSafeHostnameBytes:
    """Tests for the workarounds for hostnames rejected by the idna
    package."""

    @pytest.mark.parametrize(
        ("hostname", "expected"),
        [
            ("example.com", b"example.com"),
            ("xn--i-7iq.ws", b"xn--i-7iq.ws"),  # i❤.ws
            ("i❤.ws", b"xn--i-7iq.ws"),
            ("ü.example", b"xn--tda.example"),
            ("foo_bar.example", b"foo_bar.example"),
            # overlong ASCII label, rejected by the stdlib codec
            ("a" * 64 + ".com", b"a" * 64 + b".com"),
        ],
    )
    def test_valid(self, hostname: str, expected: bytes) -> None:
        assert _safe_hostname_bytes(hostname) == expected

    @pytest.mark.parametrize(
        "hostname",
        [
            "❤" * 200 + ".ws",
            # not hostnames at all: Twisted parses ":" out of a bracketless
            # IPv6 netloc on old versions
            ":",
            "[::1]",
        ],
    )
    def test_invalid(self, hostname: str) -> None:
        with pytest.raises(UnicodeError):
            _safe_hostname_bytes(hostname)

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("xn--i-7iq.ws", (False, b"xn--i-7iq.ws", "xn--i-7iq.ws")),
            ("i❤.ws", (False, b"xn--i-7iq.ws", "i❤.ws")),
            ("foo_bar.example", (False, b"foo_bar.example", "foo_bar.example")),
            ("example.com", (False, b"example.com", "example.com")),
            # bytes hostnames are decoded instead of encoded
            (b"xn--i-7iq.ws", (False, b"xn--i-7iq.ws", "i❤.ws")),
            (b"foo_bar.example", (False, b"foo_bar.example", "foo_bar.example")),
            (b"example.com", (False, b"example.com", "example.com")),
            # invalid hostnames must stay invalid, or Twisted resolves them
            # instead of failing early
            (":", (True, b":", ":")),
            ("[::1]", (True, b"[::1]", "[::1]")),
            (b":", (True, b":", ":")),
        ],
    )
    def test_host_as_bytes_and_text(
        self, host: bytes | str, expected: tuple[bool, bytes, str]
    ) -> None:
        """HostnameEndpoint should consider only invalid hostnames invalid."""
        assert HostnameEndpoint._hostAsBytesAndText(host) == expected


@pytest.mark.requires_reactor
class TestIdnaRejectedEndpoints:
    """Endpoints for hostnames rejected by the idna package, such as emoji
    domains or domains with underscores, should be connectable."""

    @pytest.mark.parametrize("scheme", ["http", "https"])
    @pytest.mark.parametrize("hostname", IDNA_REJECTED_HOSTNAMES)
    def test_endpoint_for_uri(self, scheme: str, hostname: str) -> None:
        from twisted.internet import reactor

        crawler = get_crawler()
        endpoint_factory = _StandardEndpointFactory(
            reactor, _load_context_factory_from_settings(crawler), 10, None
        )
        endpoint = endpoint_factory.endpointForURI(
            URI.fromBytes(f"{scheme}://{hostname}/".encode())
        )
        # https endpoints are wrapped by wrapClientTLS()
        hostname_endpoint = getattr(endpoint, "_wrappedEndpoint", endpoint)
        assert hostname_endpoint._badHostname is False
        assert hostname_endpoint._hostBytes == hostname.encode("ascii")
        assert hostname_endpoint._hostText == hostname


@coroutine_test
async def test_fetch_deprecated_spider_arg():
    class CustomDownloader(Downloader):
        # requiring the spider argument is what triggers the deprecation
        def fetch(  # type: ignore[override]  # pylint: disable=signature-differs
            self, request: Request, spider: Spider
        ) -> Deferred[Response | Request]:
            return super().fetch(request, spider)

    crawler = get_crawler(DefaultSpider, {"DOWNLOADER": CustomDownloader})
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"The fetch\(\) method of .+\.CustomDownloader requires a spider argument",
    ):
        await crawler.crawl_async()


def test_deprecated_tls_module_names() -> None:
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="scrapy.core.downloader.tls.METHOD_TLS is deprecated",
    ):
        assert tls.METHOD_TLS == "TLS"
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="scrapy.core.downloader.tls.openssl_methods is deprecated",
    ):
        assert isinstance(tls.openssl_methods, dict)
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="scrapy.core.downloader.tls.DEFAULT_CIPHERS is deprecated",
    ):
        assert tls.DEFAULT_CIPHERS._ciphers == (
            AcceptableCiphers.fromOpenSSLCipherString("DEFAULT")._ciphers
        )
