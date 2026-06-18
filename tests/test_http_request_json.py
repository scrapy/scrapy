from __future__ import annotations

import json
import warnings
from unittest import mock

from scrapy.http import JsonRequest
from scrapy.utils.python import to_bytes
from tests.test_http_request import TestRequest


class TestJsonRequest(TestRequest):
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
        assert r3.body == to_bytes(json.dumps(data))

        # empty data
        r4 = self.request_class(url="http://www.example.com/", data=[])
        assert r4.body == to_bytes(json.dumps([]))

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
        with warnings.catch_warnings(record=True) as _warnings:
            r5 = self.request_class(url="http://www.example.com/", body=body, data=data)
            assert r5.body == body
            assert r5.method == "GET"
            assert len(_warnings) == 1
            assert "data will be ignored" in str(_warnings[0].message)

    def test_empty_body_data(self):
        """passing any body value and data should result a warning"""
        data = {
            "name": "value",
        }
        with warnings.catch_warnings(record=True) as _warnings:
            r6 = self.request_class(url="http://www.example.com/", body=b"", data=data)
            assert r6.body == b""
            assert r6.method == "GET"
            assert len(_warnings) == 1
            assert "data will be ignored" in str(_warnings[0].message)

    def test_body_none_data(self):
        data = {
            "name": "value",
        }
        with warnings.catch_warnings(record=True) as _warnings:
            r7 = self.request_class(url="http://www.example.com/", body=None, data=data)
            assert r7.body == to_bytes(json.dumps(data))
            assert r7.method == "POST"
            assert len(_warnings) == 0

    def test_body_data_none(self):
        with warnings.catch_warnings(record=True) as _warnings:
            r8 = self.request_class(url="http://www.example.com/", body=None, data=None)
            assert r8.method == "GET"
            assert len(_warnings) == 0

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
        assert r2.body == to_bytes(json.dumps(data2))

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

        with warnings.catch_warnings(record=True) as _warnings:
            r1.replace(data=data2, body=body2)
            assert "Both body and data passed. data will be ignored" in str(
                _warnings[0].message
            )
