from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider
from scrapy.http import JsonRequest, Response
from scrapy.utils.request import request_from_dict

if TYPE_CHECKING:
    from twisted.python.failure import Failure


class CustomRequest(Request):
    pass


@pytest.fixture
def spider() -> MethodsSpider:
    return MethodsSpider()


def _assert_serializes_ok(request: Request, spider: Spider | None = None) -> None:
    d = request.to_dict(spider=spider)
    request2 = request_from_dict(d, spider=spider)
    _assert_same_request(request, request2)


def _assert_same_request(r1: Request, r2: Request) -> None:
    assert r1.__class__ == r2.__class__
    assert r1.url == r2.url
    assert r1.callback == r2.callback
    assert r1.errback == r2.errback
    assert r1.method == r2.method
    assert r1.body == r2.body
    assert r1.headers == r2.headers
    assert r1.cookies == r2.cookies
    assert r1.meta == r2.meta
    assert r1.cb_kwargs == r2.cb_kwargs
    assert r1.encoding == r2.encoding
    assert r1._encoding == r2._encoding
    assert r1.priority == r2.priority
    assert r1.dont_filter == r2.dont_filter
    assert r1.flags == r2.flags
    if isinstance(r1, JsonRequest):
        assert isinstance(r2, JsonRequest)
        assert r1.dumps_kwargs == r2.dumps_kwargs


def test_basic() -> None:
    r = Request("http://www.example.com")
    _assert_serializes_ok(r)


def test_all_attributes(spider: MethodsSpider) -> None:
    r = Request(
        url="http://www.example.com",
        callback=spider.parse_item,
        errback=spider.handle_error,
        method="POST",
        body=b"some body",
        headers={"content-encoding": "text/html; charset=latin-1"},
        cookies={"currency": "руб"},
        encoding="latin-1",
        priority=20,
        meta={"a": "b"},
        cb_kwargs={"k": "v"},
        flags=["testFlag"],
    )
    _assert_serializes_ok(r, spider=spider)


def test_latin1_body() -> None:
    r = Request("http://www.example.com", body=b"\xa3")
    _assert_serializes_ok(r)


def test_utf8_body() -> None:
    r = Request("http://www.example.com", body=b"\xc2\xa3")
    _assert_serializes_ok(r)


def test_request_class(spider: MethodsSpider) -> None:
    r1 = CustomRequest("http://www.example.com")
    _assert_serializes_ok(r1, spider=spider)
    r2 = JsonRequest("http://www.example.com", dumps_kwargs={"indent": 4})
    _assert_serializes_ok(r2, spider=spider)


def test_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider.parse_item,
        errback=spider.handle_error,
    )
    _assert_serializes_ok(r, spider=spider)


def test_reference_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider.parse_item_reference,  # type: ignore[arg-type,misc]
        errback=spider.handle_error_reference,  # type: ignore[arg-type,misc]
    )
    _assert_serializes_ok(r, spider=spider)
    request_dict = r.to_dict(spider=spider)
    assert request_dict["callback"] == "parse_item_reference"
    assert request_dict["errback"] == "handle_error_reference"


def test_private_reference_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider._MethodsSpider__parse_item_reference,  # type: ignore[attr-defined]
        errback=spider._MethodsSpider__handle_error_reference,  # type: ignore[attr-defined]
    )
    _assert_serializes_ok(r, spider=spider)
    request_dict = r.to_dict(spider=spider)
    assert request_dict["callback"] == "_MethodsSpider__parse_item_reference"
    assert request_dict["errback"] == "_MethodsSpider__handle_error_reference"


def test_private_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider._MethodsSpider__parse_item_private,  # type: ignore[attr-defined]
        errback=spider.handle_error,
    )
    _assert_serializes_ok(r, spider=spider)


def test_mixin_private_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider._SpiderMixin__mixin_callback,  # type: ignore[attr-defined]
        errback=spider.handle_error,
    )
    _assert_serializes_ok(r, spider=spider)


def test_delegated_callback_serialization(spider: MethodsSpider) -> None:
    r = Request(
        "http://www.example.com",
        callback=spider.delegated_callback,
        errback=spider.handle_error,
    )
    _assert_serializes_ok(r, spider=spider)


def test_unserializable_callback1(spider: MethodsSpider) -> None:
    r = Request("http://www.example.com", callback=lambda x: x)  # type: ignore[misc]
    with pytest.raises(
        ValueError, match="is not an instance method in: <MethodsSpider"
    ):
        r.to_dict(spider=spider)


def test_unserializable_callback2(spider: MethodsSpider) -> None:
    r = Request("http://www.example.com", callback=spider.parse_item)
    with pytest.raises(ValueError, match="is not an instance method in: None"):
        r.to_dict(spider=None)


def test_unserializable_callback3() -> None:
    """Parser method is removed or replaced dynamically."""

    class MySpider(Spider):
        name = "my_spider"

        def parse(self, response: Response) -> None:
            pass

    spider = MySpider()
    r = Request("http://www.example.com", callback=spider.parse)
    spider.parse = None  # type: ignore[method-assign,assignment]
    with pytest.raises(ValueError, match="is not an instance method in: <MySpider"):
        r.to_dict(spider=spider)


def test_callback_not_available() -> None:
    """Callback method is not available in the spider passed to from_dict"""
    spider = SpiderDelegation()
    r = Request("http://www.example.com", callback=spider.delegated_callback)
    d = r.to_dict(spider=spider)  # type: ignore[arg-type]
    with pytest.raises(
        ValueError, match="Method 'delegated_callback' not found in: <Spider"
    ):
        request_from_dict(d, spider=Spider("foo"))


class SpiderMixin:
    def __mixin_callback(  # pylint: disable=unused-private-member
        self, response: Response
    ) -> None:
        pass


class SpiderDelegation:
    def delegated_callback(self, response: Response) -> None:
        pass


def parse_item(response: Response) -> None:
    pass


def handle_error(failure: Failure) -> None:
    pass


def private_parse_item(response: Response) -> None:
    pass


def private_handle_error(failure: Failure) -> None:
    pass


class MethodsSpider(Spider, SpiderMixin):
    name = "test"
    parse_item_reference = parse_item
    handle_error_reference = handle_error
    __parse_item_reference = private_parse_item
    __handle_error_reference = private_handle_error

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.delegated_callback = SpiderDelegation().delegated_callback

    def parse_item(self, response: Response) -> None:
        pass

    def handle_error(self, failure: Failure) -> None:
        pass

    def __parse_item_private(  # pylint: disable=unused-private-member
        self, response: Response
    ) -> None:
        pass
