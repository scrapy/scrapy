import dataclasses
import datetime
import json
from decimal import Decimal

import attr
import pytest
from twisted.internet import defer

from scrapy.http import Request, Response
from scrapy.utils.serialize import ScrapyJSONEncoder


class TestJsonEncoder:
    @pytest.fixture
    def encoder(self) -> ScrapyJSONEncoder:
        return ScrapyJSONEncoder(sort_keys=True)

    def test_encode_decode(self, encoder: ScrapyJSONEncoder) -> None:
        dt = datetime.datetime(2010, 1, 2, 10, 11, 12)
        dts = "2010-01-02 10:11:12"
        d = datetime.date(2010, 1, 2)
        ds = "2010-01-02"
        t = datetime.time(10, 11, 12)
        ts = "10:11:12"
        dec = Decimal("1000.12")
        decs = "1000.12"
        s = {"foo"}
        ss = ["foo"]
        dt_set = {dt}
        dt_sets = [dts]

        for input_, output in [
            ("foo", "foo"),
            (d, ds),
            (t, ts),
            (dt, dts),
            (dec, decs),
            (["foo", d], ["foo", ds]),
            (s, ss),
            (dt_set, dt_sets),
        ]:
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
            name = attr.ib(type=str)
            url = attr.ib(type=str)
            price = attr.ib(type=int)

        item = AttrsItem(name="Product", url="http://product.org", price=1)
        encoded = encoder.encode(item)
        assert encoded == '{"name": "Product", "price": 1, "url": "http://product.org"}'
