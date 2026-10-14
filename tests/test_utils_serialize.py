from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal
from typing import Any

import attr
import pytest
from twisted.internet import defer

from scrapy.http import Request, Response
from scrapy.utils.serialize import ScrapyJSONEncoder


class TestJsonEncoder:
    @pytest.fixture
    def encoder(self) -> ScrapyJSONEncoder:
        return ScrapyJSONEncoder(sort_keys=True)

    @pytest.mark.parametrize(
        ("input_", "output"),
        [
            pytest.param("foo", "foo", id="str"),
            pytest.param(datetime.date(2010, 1, 2), "2010-01-02", id="date"),
            pytest.param(datetime.time(10, 11, 12), "10:11:12", id="time"),
            pytest.param(
                datetime.time(10, 11, 12, 133700),
                "10:11:12.133700",
                id="time-microseconds",
            ),
            pytest.param(
                datetime.datetime(2010, 1, 2, 10, 11, 12),  # noqa: DTZ001
                "2010-01-02T10:11:12",
                id="datetime-naive",
            ),
            pytest.param(
                datetime.datetime(2010, 1, 2, 10, 11, 12, 133700, tzinfo=datetime.UTC),
                "2010-01-02T10:11:12.133700+00:00",
                id="datetime-aware",
            ),
            pytest.param(Decimal("1000.12"), "1000.12", id="decimal"),
            pytest.param(
                ["foo", datetime.date(2010, 1, 2)], ["foo", "2010-01-02"], id="list"
            ),
            pytest.param({"foo"}, ["foo"], id="set"),
            pytest.param(
                {datetime.datetime(2010, 1, 2, 10, 11, 12)},  # noqa: DTZ001
                ["2010-01-02T10:11:12"],
                id="datetime-set",
            ),
        ],
    )
    def test_encode_decode(
        self, input_: Any, output: Any, encoder: ScrapyJSONEncoder
    ) -> None:
        assert encoder.encode(input_) == json.dumps(output, sort_keys=True)

    def test_encode_deferred(self, encoder: ScrapyJSONEncoder) -> None:
        assert "Deferred" in encoder.encode(defer.Deferred())

    def test_encode_request(self, encoder: ScrapyJSONEncoder) -> None:
        r = Request("http://www.example.com/lala")
        rs = encoder.encode(r)
        assert r.method in rs
        assert r.url in rs

    def test_encode_response(self, encoder: ScrapyJSONEncoder) -> None:
        r = Response("http://www.example.com/lala")
        rs = encoder.encode(r)
        assert r.url in rs
        assert str(r.status) in rs

    def test_encode_dataclass_item(self, encoder: ScrapyJSONEncoder) -> None:
        @dataclasses.dataclass
        class TestDataClass:
            name: str
            url: str
            price: int

        item = TestDataClass(name="Product", url="http://product.org", price=1)
        encoded = encoder.encode(item)
        assert encoded == '{"name": "Product", "price": 1, "url": "http://product.org"}'

    def test_encode_attrs_item(self, encoder: ScrapyJSONEncoder) -> None:
        @attr.s
        class AttrsItem:
            name: str = attr.ib()
            url: str = attr.ib()
            price: int = attr.ib()

        item = AttrsItem(name="Product", url="http://product.org", price=1)
        encoded = encoder.encode(item)
        assert encoded == '{"name": "Product", "price": 1, "url": "http://product.org"}'
