"""
Tests borrowed from the twisted.web.client tests.
"""

from __future__ import annotations

from urllib.parse import urlparse

import OpenSSL.SSL
import pytest
from pytest_twisted import async_yield_fixture
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks
from twisted.internet.testing import StringTransport
from twisted.protocols.policies import WrappingFactory
from twisted.web import resource, server, static, util
from twisted.web.client import _makeGetterFactory

from scrapy.core.downloader import webclient as client
from scrapy.core.downloader.contextfactory import ScrapyClientContextFactory
from scrapy.http import Headers, Request
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes, to_unicode
from scrapy.utils.test import get_crawler
from tests.mockserver import (
    BrokenDownloadResource,
    ErrorResource,
    ForeverTakingResource,
    HostHeaderResource,
    NoLengthResource,
    PayloadResource,
    ssl_context_factory,
)
from tests.test_core_downloader import TestContextFactoryBase


def getPage(url, contextFactory=None, response_transform=None, *args, **kwargs):
    """Adapted version of twisted.web.client.getPage"""

    def _clientfactory(url, *args, **kwargs):
        url = to_unicode(url)
        timeout = kwargs.pop("timeout", 0)
        f = client.ScrapyHTTPClientFactory(
            Request(url, *args, **kwargs), timeout=timeout
        )
        f.deferred.addCallback(response_transform or (lambda r: r.body))
        return f

    return _makeGetterFactory(
        to_bytes(url),
        _clientfactory,
        contextFactory=contextFactory,
        *args,
        **kwargs,
    ).deferred


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestScrapyHTTPPageGetter:
    def test_earlyHeaders(self):
        # basic test stolen from twisted HTTPageGetter
        factory = client.ScrapyHTTPClientFactory(
            Request(
                url="http://foo/bar",
                body="some data",
                headers={
                    "Host": "example.net",
                    "User-Agent": "fooble",
                    "Cookie": "blah blah",
                    "Content-Length": "12981",
                    "Useful": "value",
                },
            )
        )

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Content-Length: 9\r\n"
            b"Useful: value\r\n"
            b"Connection: close\r\n"
            b"User-Agent: fooble\r\n"
            b"Host: example.net\r\n"
            b"Cookie: blah blah\r\n"
            b"\r\n"
            b"some data",
        )

        # test minimal sent headers
        factory = client.ScrapyHTTPClientFactory(Request("http://foo/bar"))
        self._test(factory, b"GET /bar HTTP/1.0\r\nHost: foo\r\n\r\n")

        # test a simple POST with body and content-type
        factory = client.ScrapyHTTPClientFactory(
            Request(
                method="POST",
                url="http://foo/bar",
                body="name=value",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )

        self._test(
            factory,
            b"POST /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"Connection: close\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"name=value",
        )

        # test a POST method with no body provided
        factory = client.ScrapyHTTPClientFactory(
            Request(method="POST", url="http://foo/bar")
        )

        self._test(
            factory,
            b"POST /bar HTTP/1.0\r\nHost: foo\r\nContent-Length: 0\r\n\r\n",
        )

        # test with single and multivalued headers
        factory = client.ScrapyHTTPClientFactory(
            Request(
                url="http://foo/bar",
                headers={
                    "X-Meta-Single": "single",
                    "X-Meta-Multivalued": ["value1", "value2"],
                },
            )
        )

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"X-Meta-Multivalued: value1\r\n"
            b"X-Meta-Multivalued: value2\r\n"
            b"X-Meta-Single: single\r\n"
            b"\r\n",
        )

        # same test with single and multivalued headers but using Headers class
        factory = client.ScrapyHTTPClientFactory(
            Request(
                url="http://foo/bar",
                headers=Headers(
                    {
                        "X-Meta-Single": "single",
                        "X-Meta-Multivalued": ["value1", "value2"],
                    }
                ),
            )
        )

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"X-Meta-Multivalued: value1\r\n"
            b"X-Meta-Multivalued: value2\r\n"
            b"X-Meta-Single: single\r\n"
            b"\r\n",
        )

    def _test(self, factory, testvalue):
        transport = StringTransport()
        protocol = client.ScrapyHTTPPageGetter()
        protocol.factory = factory
        protocol.makeConnection(transport)
        assert set(transport.value().splitlines()) == set(testvalue.splitlines())
        return testvalue

    def test_non_standard_line_endings(self):
        # regression test for: http://dev.scrapy.org/ticket/258
        factory = client.ScrapyHTTPClientFactory(Request(url="http://foo/bar"))
        protocol = client.ScrapyHTTPPageGetter()
        protocol.factory = factory
        protocol.headers = Headers()
        protocol.dataReceived(b"HTTP/1.0 200 OK\n")
        protocol.dataReceived(b"Hello: World\n")
        protocol.dataReceived(b"Foo: Bar\n")
        protocol.dataReceived(b"\n")
        assert protocol.headers == Headers({"Hello": ["World"], "Foo": ["Bar"]})


class EncodingResource(resource.Resource):
    out_encoding = "cp1251"

    def render(self, request):
        body = to_unicode(request.content.read())
        request.setHeader(b"content-encoding", self.out_encoding)
        return body.encode(self.out_encoding)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestWebClient:
    def _listen(self, site):
        from twisted.internet import reactor

        return reactor.listenTCP(0, site, interface="127.0.0.1")

    @pytest.fixture
    def wrapper(self, tmp_path):
        (tmp_path / "file").write_bytes(b"0123456789")
        r = static.File(str(tmp_path))
        r.putChild(b"redirect", util.Redirect(b"/file"))
        r.putChild(b"wait", ForeverTakingResource())
        r.putChild(b"error", ErrorResource())
        r.putChild(b"nolength", NoLengthResource())
        r.putChild(b"host", HostHeaderResource())
        r.putChild(b"payload", PayloadResource())
        r.putChild(b"broken", BrokenDownloadResource())
        r.putChild(b"encoding", EncodingResource())
        site = server.Site(r, timeout=None)
        return WrappingFactory(site)

    @async_yield_fixture
    async def server_port(self, wrapper):
        port = self._listen(wrapper)

        yield port.getHost().port

        await port.stopListening()

    @pytest.fixture
    def server_url(self, server_port):
        return f"http://127.0.0.1:{server_port}/"

    @inlineCallbacks
    def testPayload(self, server_url):
        s = "0123456789" * 10
        body = yield getPage(server_url + "payload", body=s)
        assert body == to_bytes(s)

    @inlineCallbacks
    def testHostHeader(self, server_port, server_url):
        # if we pass Host header explicitly, it should be used, otherwise
        # it should extract from url
        body = yield getPage(server_url + "host")
        assert body == to_bytes(f"127.0.0.1:{server_port}")
        body = yield getPage(server_url + "host", headers={"Host": "www.example.com"})
        assert body == to_bytes("www.example.com")

    @inlineCallbacks
    def test_getPage(self, server_url):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the body of the response if the default method B{GET} is used.
        """
        body = yield getPage(server_url + "file")
        assert body == b"0123456789"

    @inlineCallbacks
    def test_getPageHead(self, server_url):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the empty string if the method is C{HEAD} and there is a successful
        response code.
        """

        def _getPage(method):
            return getPage(server_url + "file", method=method)

        body = yield _getPage("head")
        assert body == b""
        body = yield _getPage("HEAD")
        assert body == b""

    @inlineCallbacks
    def test_timeoutNotTriggering(self, server_port, server_url):
        """
        When a non-zero timeout is passed to L{getPage} and the page is
        retrieved before the timeout period elapses, the L{Deferred} is
        called back with the contents of the page.
        """
        body = yield getPage(server_url + "host", timeout=100)
        assert body == to_bytes(f"127.0.0.1:{server_port}")

    @inlineCallbacks
    def test_timeoutTriggering(self, wrapper, server_url):
        """
        When a non-zero timeout is passed to L{getPage} and that many
        seconds elapse before the server responds to the request. the
        L{Deferred} is errbacked with a L{error.TimeoutError}.
        """
        with pytest.raises(defer.TimeoutError):
            yield getPage(server_url + "wait", timeout=0.000001)
        # Clean up the server which is hanging around not doing
        # anything.
        connected = list(wrapper.protocols.keys())
        # There might be nothing here if the server managed to already see
        # that the connection was lost.
        if connected:
            connected[0].transport.loseConnection()

    @inlineCallbacks
    def testNotFound(self, server_url):
        body = yield getPage(server_url + "notsuchfile")
        assert b"404 - No Such Resource" in body

    @inlineCallbacks
    def testFactoryInfo(self, server_url):
        from twisted.internet import reactor

        url = server_url + "file"
        parsed = urlparse(url)
        factory = client.ScrapyHTTPClientFactory(Request(url))
        reactor.connectTCP(parsed.hostname, parsed.port, factory)
        yield factory.deferred
        assert factory.status == b"200"
        assert factory.version.startswith(b"HTTP/")
        assert factory.message == b"OK"
        assert factory.response_headers[b"content-length"] == b"10"

    @inlineCallbacks
    def testRedirect(self, server_url):
        body = yield getPage(server_url + "redirect")
        assert (
            body
            == b'\n<html>\n    <head>\n        <meta http-equiv="refresh" content="0;URL=/file">\n'
            b'    </head>\n    <body bgcolor="#FFFFFF" text="#000000">\n    '
            b'<a href="/file">click here</a>\n    </body>\n</html>\n'
        )

    @inlineCallbacks
    def test_encoding(self, server_url):
        """Test that non-standart body encoding matches
        Content-Encoding header"""
        original_body = b"\xd0\x81\xd1\x8e\xd0\xaf"
        response = yield getPage(
            server_url + "encoding", body=original_body, response_transform=lambda r: r
        )
        content_encoding = to_unicode(response.headers[b"Content-Encoding"])
        assert content_encoding == EncodingResource.out_encoding
        assert response.body.decode(content_encoding) == to_unicode(original_body)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestWebClientSSL(TestContextFactoryBase):
    @inlineCallbacks
    def testPayload(self, server_url):
        s = "0123456789" * 10
        body = yield getPage(server_url + "payload", body=s)
        assert body == to_bytes(s)


class TestWebClientCustomCiphersSSL(TestWebClientSSL):
    # we try to use a cipher that is not enabled by default in OpenSSL
    custom_ciphers = "CAMELLIA256-SHA"
    context_factory = ssl_context_factory(cipher_string=custom_ciphers)

    @inlineCallbacks
    def testPayload(self, server_url):
        s = "0123456789" * 10
        crawler = get_crawler(
            settings_dict={"DOWNLOADER_CLIENT_TLS_CIPHERS": self.custom_ciphers}
        )
        client_context_factory = build_from_crawler(ScrapyClientContextFactory, crawler)
        body = yield getPage(
            server_url + "payload", body=s, contextFactory=client_context_factory
        )
        assert body == to_bytes(s)

    @inlineCallbacks
    def testPayloadDisabledCipher(self, server_url):
        s = "0123456789" * 10
        crawler = get_crawler(
            settings_dict={
                "DOWNLOADER_CLIENT_TLS_CIPHERS": "ECDHE-RSA-AES256-GCM-SHA384"
            }
        )
        client_context_factory = build_from_crawler(ScrapyClientContextFactory, crawler)
        with pytest.raises(OpenSSL.SSL.Error):
            yield getPage(
                server_url + "payload", body=s, contextFactory=client_context_factory
            )
