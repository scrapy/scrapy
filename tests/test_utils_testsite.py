import pytest
from twisted.web.client import Agent, readBody
from twisted.internet import defer, reactor

from scrapy.utils import testsite


@pytest.mark.twisted
@defer.inlineCallbacks
def test_text_endpoint_returns_works():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"text")
    body = yield readBody(response)

    assert body == b"Works"
    site.stopListening()


@pytest.mark.twisted
@defer.inlineCallbacks
def test_html_endpoint_contains_expected_tags():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"html")
    body = yield readBody(response)

    assert b"class='one'" in body
    assert b"Works" in body
    assert b"World" in body
    site.stopListening()


@pytest.mark.twisted
@defer.inlineCallbacks
def test_enc_gb18030_endpoint_encoding_declared():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"enc-gb18030")

    content_type = response.headers.getRawHeaders(b"content-type")[0].decode()
    assert "charset=gb18030" in content_type
    body = yield readBody(response)
    assert b"gb18030" in body
    site.stopListening()


@pytest.mark.twisted
@defer.inlineCallbacks
def test_redirect_endpoint_follows_location_header():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"redirect")

    headers = response.headers.getRawHeaders(b"location")
    assert headers is not None
    # Compare against bytes instead of str
    assert headers[0].endswith(b"/redirected")
    site.stopListening()


@pytest.mark.twisted
@defer.inlineCallbacks
def test_redirect_no_meta_refresh_has_no_refresh_tag():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"redirect-no-meta-refresh")
    body = yield readBody(response)

    assert b"http-equiv" not in body
    assert b"do-not-refresh-me" in body
    site.stopListening()


@pytest.mark.twisted
@defer.inlineCallbacks
def test_redirected_endpoint_returns_expected_body():
    site = reactor.listenTCP(0, testsite.test_site(), interface="127.0.0.1")
    port = site.getHost().port
    base_url = f"http://127.0.0.1:{port}/"

    agent = Agent(reactor)
    response = yield agent.request(b"GET", base_url.encode() + b"redirected")
    body = yield readBody(response)

    assert body == b"Redirected here"
    site.stopListening()
