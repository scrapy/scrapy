import xmlrpc.client
from typing import Any

import pytest

from scrapy import Request
from scrapy.http import XmlRpcRequest
from scrapy.utils.python import to_bytes
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
        assert r.body == to_bytes(
            xmlrpc.client.dumps(**kwargs), encoding=kwargs.get("encoding", "utf-8")
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
