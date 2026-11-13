from __future__ import annotations

import json
import warnings
from decimal import Decimal
from unittest import mock

import pytest

from scrapy.http import JsonRequest
from tests.utils.bases.http_request import TestRequestBase


class TestJsonRequest(TestRequestBase):
    request_class = JsonRequest
    default_method = "GET"
    default_headers = {
        b"Content-Type": [b"application/json"],
        b"Accept": [b"application/json, text/javascript, */*; q=0.01"],
    }

    def test_data(self):
        r1 = self.request_class(url="http://www.example.com/")
        assert r1.body == b""

        body = b"body"
        r2 = self.request_class(url="http://www.example.com/", body=body)
        assert r2.body == body

        data = {
            "name": "value",
        }
        r3 = self.request_class(url="http://www.example.com/", data=data)
        assert r3.body == json.dumps(data).encode()

        # empty data
        r4 = self.request_class(url="http://www.example.com/", data=[])
        assert r4.body == json.dumps([]).encode()

    def test_data_method(self):
        # data is not passed
        r1 = self.request_class(url="http://www.example.com/")
        assert r1.method == "GET"

        body = b"body"
        r2 = self.request_class(url="http://www.example.com/", body=body)
        assert r2.method == "GET"

        data = {
            "name": "value",
        }
        r3 = self.request_class(url="http://www.example.com/", data=data)
        assert r3.method == "POST"

        # method passed explicitly
        r4 = self.request_class(url="http://www.example.com/", data=data, method="GET")
        assert r4.method == "GET"

        r5 = self.request_class(url="http://www.example.com/", data=[])
        assert r5.method == "POST"

    def test_body_data(self):
        """passing both body and data should result a warning"""
        body = b"body"
        data = {
            "name": "value",
        }
        with pytest.warns(UserWarning, match="data will be ignored"):
            r5 = self.request_class(url="http://www.example.com/", body=body, data=data)
        assert r5.body == body
        assert r5.method == "GET"

    def test_empty_body_data(self):
        """passing any body value and data should result a warning"""
        data = {
            "name": "value",
        }
        with pytest.warns(UserWarning, match="data will be ignored"):
            r6 = self.request_class(url="http://www.example.com/", body=b"", data=data)
        assert r6.body == b""
        assert r6.method == "GET"

    def test_body_none_data(self):
        data = {
            "name": "value",
        }
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error", category=UserWarning, message="Both body and data passed"
            )
            r7 = self.request_class(url="http://www.example.com/", body=None, data=data)
        assert r7.body == json.dumps(data).encode()
        assert r7.method == "POST"

    def test_body_data_none(self):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error", category=UserWarning, message="Both body and data passed"
            )
            r8 = self.request_class(url="http://www.example.com/", body=None, data=None)
        assert r8.method == "GET"

    def test_dumps_sort_keys(self):
        """Test that sort_keys=True is passed to json.dumps by default"""
        data = {
            "name": "value",
        }
        with mock.patch("json.dumps", return_value=b"") as mock_dumps:
            self.request_class(url="http://www.example.com/", data=data)
            kwargs = mock_dumps.call_args[1]
            assert kwargs["sort_keys"] is True

    def test_dumps_kwargs(self):
        """Test that dumps_kwargs are passed to json.dumps"""
        data = {
            "name": "value",
        }
        dumps_kwargs = {
            "ensure_ascii": True,
            "allow_nan": True,
        }
        with mock.patch("json.dumps", return_value=b"") as mock_dumps:
            self.request_class(
                url="http://www.example.com/", data=data, dumps_kwargs=dumps_kwargs
            )
            kwargs = mock_dumps.call_args[1]
            assert kwargs["ensure_ascii"] is True
            assert kwargs["allow_nan"] is True

    def test_replace_data(self):
        data1 = {
            "name1": "value1",
        }
        data2 = {
            "name2": "value2",
        }
        r1 = self.request_class(url="http://www.example.com/", data=data1)
        r2 = r1.replace(data=data2)
        assert r2.body == json.dumps(data2).encode()

    def test_replace_sort_keys(self):
        """Test that replace provides sort_keys=True to json.dumps"""
        data1 = {
            "name1": "value1",
        }
        data2 = {
            "name2": "value2",
        }
        r1 = self.request_class(url="http://www.example.com/", data=data1)
        with mock.patch("json.dumps", return_value=b"") as mock_dumps:
            r1.replace(data=data2)
            kwargs = mock_dumps.call_args[1]
            assert kwargs["sort_keys"] is True

    def test_replace_dumps_kwargs(self):
        """Test that dumps_kwargs are provided to json.dumps when replace is called"""
        data1 = {
            "name1": "value1",
        }
        data2 = {
            "name2": "value2",
        }
        dumps_kwargs = {
            "ensure_ascii": True,
            "allow_nan": True,
        }
        r1 = self.request_class(
            url="http://www.example.com/", data=data1, dumps_kwargs=dumps_kwargs
        )
        with mock.patch("json.dumps", return_value=b"") as mock_dumps:
            r1.replace(data=data2)
            kwargs = mock_dumps.call_args[1]
            assert kwargs["ensure_ascii"] is True
            assert kwargs["allow_nan"] is True

    def test_replace_data_with_new_dumps_kwargs(self):
        r1 = self.request_class(url="http://www.example.com/", data={"value": 1})
        r2 = r1.replace(data={"value": Decimal("1.25")}, dumps_kwargs={"default": str})
        assert r2.body == b'{"value": "1.25"}'
        assert r2.dumps_kwargs == {"default": str, "sort_keys": True}

    @pytest.mark.parametrize(
        ("dumps_kwargs", "expected"),
        [
            ({"ensure_ascii": False}, '{"a": "é"}'.encode()),
            ({}, b'{"a": "\\u00e9"}'),
            (None, b'{"a": "\\u00e9"}'),
        ],
    )
    def test_replace_data_ignores_original_dumps_kwargs(self, dumps_kwargs, expected):
        r1 = self.request_class(
            url="http://www.example.com/",
            data={"a": 1},
            dumps_kwargs={"separators": (",", ":")},
        )
        r2 = r1.replace(data={"a": "é"}, dumps_kwargs=dumps_kwargs)
        assert r2.body == expected

    def test_replace_dumps_kwargs_only_keeps_body(self):
        """The body is already serialized, so only later replacements use the
        new dumps_kwargs."""
        r1 = self.request_class(url="http://www.example.com/", data={"value": 1})
        r2 = r1.replace(dumps_kwargs={"default": str})
        assert r2.body == r1.body
        assert r2.dumps_kwargs == {"default": str, "sort_keys": True}
        r3 = r2.replace(data={"value": Decimal("1.25")})
        assert r3.body == b'{"value": "1.25"}'

    def test_replacement_both_body_and_data_warns(self):
        """Test that we get a warning if both body and data are passed"""
        body1 = None
        body2 = b"body"
        data1 = {
            "name1": "value1",
        }
        data2 = {
            "name2": "value2",
        }
        r1 = self.request_class(url="http://www.example.com/", data=data1, body=body1)

        with pytest.warns(UserWarning, match="data will be ignored"):
            r1.replace(data=data2, body=body2)
