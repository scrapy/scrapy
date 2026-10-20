import contextvars
import xmlrpc.client
from collections.abc import Callable, Coroutine, Generator
from contextlib import AbstractContextManager
from functools import partial
from typing import Any

import pytest

from scrapy import Request
from scrapy.http import XmlRpcRequest
from scrapy.http.request import (
    _active_crawler,
    _active_crawler_scope,
    _in_download_handler,
    _in_download_handler_scope,
)
from scrapy.utils.test import get_crawler
from tests.utils.bases.http_request import TestRequestBase


class TestRequest(TestRequestBase):
    request_class = Request


class TestXmlRpcRequest(TestRequestBase):
    request_class = XmlRpcRequest
    default_method = "POST"
    default_headers = {b"Content-Type": [b"text/xml"]}

    def _test_request(self, **kwargs: Any) -> None:
        r = self.request_class("http://scrapytest.org/rpc2", **kwargs)
        assert r.headers[b"Content-Type"] == b"text/xml"
        assert r.body == xmlrpc.client.dumps(**kwargs).encode(
            encoding=kwargs.get("encoding", "utf-8")
        )
        assert r.method == "POST"
        assert r.encoding == kwargs.get("encoding", "utf-8")
        assert r.dont_filter

    def test_xmlrpc_dumps(self):
        self._test_request(params=("value",))
        self._test_request(params=("username", "password"), methodname="login")
        self._test_request(params=("response",), methodresponse="login")
        self._test_request(params=("pas£",), encoding="utf-8")
        self._test_request(params=(None,), allow_none=1)
        with pytest.raises(TypeError):
            self._test_request()
        with pytest.raises(TypeError):
            self._test_request(params=(None,))

    def test_latin1(self):
        self._test_request(params=("pas£",), encoding="latin1")


class _Suspend:
    def __await__(self) -> Generator[None]:
        yield


@pytest.mark.parametrize(
    ("make_scope", "var"),
    [
        (lambda: partial(_active_crawler_scope, get_crawler()), _active_crawler),
        (lambda: _in_download_handler_scope, _in_download_handler),
    ],
    ids=["active_crawler", "in_download_handler"],
)
def test_scope_closed_elsewhere(
    make_scope: Callable[[], Callable[[], AbstractContextManager[None]]],
    var: contextvars.ContextVar[Any],
) -> None:
    scope = make_scope()

    async def inner() -> None:
        with scope():
            await _Suspend()

    def outer() -> Coroutine[Any, Any, None]:
        with scope():
            coro = inner()
            coro.send(None)
        return coro

    def run() -> None:
        default = var.get()
        coro = contextvars.copy_context().run(outer)
        coro.close()
        assert var.get() == default

    contextvars.Context().run(run)
