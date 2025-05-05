import copy

import pytest

from scrapy.http import Headers


class TestHeaders:
    def assertSortedEqual(self, first, second, msg=None):
        assert sorted(first) == sorted(second), msg

    def test_basics(self):
        h = Headers({"Content-Type": "text/html", "Content-Length": 1234})
        assert h["Content-Type"]
        assert h["Content-Length"]

        with pytest.raises(KeyError):
            h["Accept"]
        assert h.get("Accept") is None
        assert h.getlist("Accept") == []

        assert h.get("Accept", "*/*") == b"*/*"
        assert h.getlist("Accept", "*/*") == [b"*/*"]
        assert h.getlist("Accept", ["text/html", "images/jpeg"]) == [
            b"text/html",
            b"images/jpeg",
        ]

    def test_single_value(self):
        h = Headers()
        h["Content-Type"] = "text/html"
        assert h["Content-Type"] == b"text/html"
        assert h.get("Content-Type") == b"text/html"
        assert h.getlist("Content-Type") == [b"text/html"]

    def test_multivalue(self):
        h = Headers()
        h["X-Forwarded-For"] = hlist = ["ip1", "ip2"]
        assert h["X-Forwarded-For"] == b"ip2"
        assert h.get("X-Forwarded-For") == b"ip2"
        assert h.getlist("X-Forwarded-For") == [b"ip1", b"ip2"]
        assert h.getlist("X-Forwarded-For") is not hlist

    def test_multivalue_for_one_header(self):
        h = Headers((("a", "b"), ("a", "c")))
        assert h["a"] == b"c"
        assert h.get("a") == b"c"
        assert h.getlist("a") == [b"b", b"c"]

    def test_encode_utf8(self):
        h = Headers({"key": "\xa3"}, encoding="utf-8")
        key, val = dict(h).popitem()
        assert isinstance(key, bytes), key
        assert isinstance(val[0], bytes), val[0]
        assert val[0] == b"\xc2\xa3"

    def test_encode_latin1(self):
        h = Headers({"key": "\xa3"}, encoding="latin1")
        key, val = dict(h).popitem()
        assert val[0] == b"\xa3"

    def test_encode_multiple(self):
        h = Headers({"key": ["\xa3"]}, encoding="utf-8")
        key, val = dict(h).popitem()
        assert val[0] == b"\xc2\xa3"

    def test_delete_and_contains(self):
        h = Headers()
        h["Content-Type"] = "text/html"
        assert "Content-Type" in h
        del h["Content-Type"]
        assert "Content-Type" not in h

    def test_setdefault(self):
        h = Headers()
        hlist = ["ip1", "ip2"]
        olist = h.setdefault("X-Forwarded-For", hlist)
        assert h.getlist("X-Forwarded-For") is not hlist
        assert h.getlist("X-Forwarded-For") is olist

        h = Headers()
        olist = h.setdefault("X-Forwarded-For", "ip1")
        assert h.getlist("X-Forwarded-For") == [b"ip1"]
        assert h.getlist("X-Forwarded-For") is olist

    def test_iterables(self):
        idict = {"Content-Type": "text/html", "X-Forwarded-For": ["ip1", "ip2"]}

        h = Headers(idict)
        assert dict(h) == {
            b"Content-Type": [b"text/html"],
            b"X-Forwarded-For": [b"ip1", b"ip2"],
        }
        self.assertSortedEqual(h.keys(), [b"X-Forwarded-For", b"Content-Type"])
        self.assertSortedEqual(
            h.items(),
            [(b"X-Forwarded-For", [b"ip1", b"ip2"]), (b"Content-Type", [b"text/html"])],
        )
        self.assertSortedEqual(h.values(), [b"ip2", b"text/html"])

    def test_update(self):
        h = Headers()
        h.update({"Content-Type": "text/html", "X-Forwarded-For": ["ip1", "ip2"]})
        assert h.getlist("Content-Type") == [b"text/html"]
        assert h.getlist("X-Forwarded-For") == [b"ip1", b"ip2"]

    def test_copy(self):
        h1 = Headers({"header1": ["value1", "value2"]})
        h2 = copy.copy(h1)
        assert h1 == h2
        assert h1.getlist("header1") == h2.getlist("header1")
        assert h1.getlist("header1") is not h2.getlist("header1")
        assert isinstance(h2, Headers)

    def test_appendlist(self):
        h1 = Headers({"header1": "value1"})
        h1.appendlist("header1", "value3")
        assert h1.getlist("header1") == [b"value1", b"value3"]

        h1 = Headers()
        h1.appendlist("header1", "value1")
        h1.appendlist("header1", "value3")
        assert h1.getlist("header1") == [b"value1", b"value3"]

    def test_setlist(self):
        h1 = Headers({"header1": "value1"})
        assert h1.getlist("header1") == [b"value1"]
        h1.setlist("header1", [b"value2", b"value3"])
        assert h1.getlist("header1") == [b"value2", b"value3"]

    def test_setlistdefault(self):
        h1 = Headers({"header1": "value1"})
        h1.setlistdefault("header1", ["value2", "value3"])
        h1.setlistdefault("header2", ["value2", "value3"])
        assert h1.getlist("header1") == [b"value1"]
        assert h1.getlist("header2") == [b"value2", b"value3"]

    def test_none_value(self):
        h1 = Headers()
        h1["foo"] = "bar"
        h1["foo"] = None
        h1.setdefault("foo", "bar")
        assert h1.get("foo") is None
        assert h1.getlist("foo") == []

    def test_int_value(self):
        h1 = Headers({"hey": 5})
        h1["foo"] = 1
        h1.setdefault("bar", 2)
        h1.setlist("buz", [1, "dos", 3])
        assert h1.getlist("foo") == [b"1"]
        assert h1.getlist("bar") == [b"2"]
        assert h1.getlist("buz") == [b"1", b"dos", b"3"]
        assert h1.getlist("hey") == [b"5"]

    def test_invalid_value(self):
        with pytest.raises(TypeError, match="Unsupported value type"):
            Headers({"foo": object()})
        with pytest.raises(TypeError, match="Unsupported value type"):
            Headers()["foo"] = object()
        with pytest.raises(TypeError, match="Unsupported value type"):
            Headers().setdefault("foo", object())
        with pytest.raises(TypeError, match="Unsupported value type"):
            Headers().setlist("foo", [object()])
