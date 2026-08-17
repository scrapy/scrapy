import copy

import pytest

from scrapy.http import Headers


def test_basics() -> None:
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


def test_single_value() -> None:
    h = Headers()
    h["Content-Type"] = "text/html"
    assert h["Content-Type"] == b"text/html"
    assert h.get("Content-Type") == b"text/html"
    assert h.getlist("Content-Type") == [b"text/html"]


def test_multivalue() -> None:
    h = Headers()
    h["X-Forwarded-For"] = hlist = ["ip1", "ip2"]
    assert h["X-Forwarded-For"] == b"ip2"
    assert h.get("X-Forwarded-For") == b"ip2"
    assert h.getlist("X-Forwarded-For") == [b"ip1", b"ip2"]
    assert h.getlist("X-Forwarded-For") is not hlist  # type: ignore[comparison-overlap]


def test_multivalue_for_one_header() -> None:
    h = Headers((("a", "b"), ("a", "c")))
    assert h["a"] == b"c"
    assert h.get("a") == b"c"
    assert h.getlist("a") == [b"b", b"c"]


def test_encode_utf8() -> None:
    h = Headers({"key": "\xa3"}, encoding="utf-8")
    key, val = dict(h.items()).popitem()
    assert isinstance(key, bytes), key
    assert isinstance(val[0], bytes), val[0]
    assert val[0] == b"\xc2\xa3"


def test_encode_latin1() -> None:
    h = Headers({"key": "\xa3"}, encoding="latin1")
    _, val = dict(h.items()).popitem()
    assert val[0] == b"\xa3"


def test_encode_multiple() -> None:
    h = Headers({"key": ["\xa3"]}, encoding="utf-8")
    _, val = dict(h.items()).popitem()
    assert val[0] == b"\xc2\xa3"


def test_key_case_kept() -> None:
    h = Headers({"accept": "text/html", "access_token": "foo"})
    assert sorted(h.keys()) == [b"accept", b"access_token"]


def test_key_case_of_first_spelling_wins() -> None:
    h = Headers({"accept": "a", "Accept": "b"})
    assert h.getlist("ACCEPT") == [b"a", b"b"]
    assert list(h.keys()) == [b"accept"]

    h["ACCEPT"] = "c"
    h.appendlist("aCCept", "d")
    h.update({"ACCEPT": "e"})
    assert list(h.keys()) == [b"accept"]
    assert h.getlist("accept") == [b"e"]

    del h["ACCEPT"]
    h["ACCEPT"] = "f"
    assert list(h.keys()) == [b"ACCEPT"]


def test_delete_and_contains() -> None:
    h = Headers()
    h["Content-Type"] = "text/html"
    assert "Content-Type" in h
    del h["Content-Type"]
    assert "Content-Type" not in h


def test_setdefault() -> None:
    h = Headers()
    hlist = ["ip1", "ip2"]
    olist = h.setdefault("X-Forwarded-For", hlist)
    assert h.getlist("X-Forwarded-For") is not hlist  # type: ignore[comparison-overlap]
    assert h.getlist("X-Forwarded-For") is olist

    h = Headers()
    olist = h.setdefault("X-Forwarded-For", "ip1")
    assert h.getlist("X-Forwarded-For") == [b"ip1"]
    assert h.getlist("X-Forwarded-For") is olist


def test_iterables() -> None:
    idict = {"Content-Type": "text/html", "X-Forwarded-For": ["ip1", "ip2"]}

    h = Headers(idict)
    assert dict(h.items()) == {
        b"Content-Type": [b"text/html"],
        b"X-Forwarded-For": [b"ip1", b"ip2"],
    }
    assert sorted(h.keys()) == [b"Content-Type", b"X-Forwarded-For"]
    assert sorted(h.items()) == [
        (b"Content-Type", [b"text/html"]),
        (b"X-Forwarded-For", [b"ip1", b"ip2"]),
    ]
    assert set(h.values()) == {b"ip2", b"text/html"}


def test_update() -> None:
    h = Headers()
    h.update({"Content-Type": "text/html", "X-Forwarded-For": ["ip1", "ip2"]})
    assert h.getlist("Content-Type") == [b"text/html"]
    assert h.getlist("X-Forwarded-For") == [b"ip1", b"ip2"]


def test_copy() -> None:
    h1 = Headers({"header1": ["value1", "value2"]})
    h2 = copy.copy(h1)
    assert h1 == h2
    assert h1.getlist("header1") == h2.getlist("header1")
    assert h1.getlist("header1") is not h2.getlist("header1")
    assert isinstance(h2, Headers)


def test_appendlist() -> None:
    h1 = Headers({"header1": "value1"})
    h1.appendlist("header1", "value3")
    assert h1.getlist("header1") == [b"value1", b"value3"]

    h1 = Headers()
    h1.appendlist("header1", "value1")
    h1.appendlist("header1", "value3")
    assert h1.getlist("header1") == [b"value1", b"value3"]


def test_setlist() -> None:
    h1 = Headers({"header1": "value1"})
    assert h1.getlist("header1") == [b"value1"]
    h1.setlist("header1", [b"value2", b"value3"])
    assert h1.getlist("header1") == [b"value2", b"value3"]


def test_setlistdefault() -> None:
    h1 = Headers({"header1": "value1"})
    h1.setlistdefault("header1", ["value2", "value3"])
    h1.setlistdefault("header2", ["value2", "value3"])
    assert h1.getlist("header1") == [b"value1"]
    assert h1.getlist("header2") == [b"value2", b"value3"]


def test_none_value() -> None:
    h1 = Headers()
    h1["foo"] = "bar"
    h1["foo"] = None
    h1.setdefault("foo", "bar")
    assert h1["foo"] is None
    assert h1.get("foo") is None
    assert h1.getlist("foo") == []


def test_int_value() -> None:
    h1 = Headers({"hey": 5})
    h1["foo"] = 1
    h1.setdefault("bar", 2)
    h1.setlist("buz", [1, "dos", 3])
    assert h1.getlist("foo") == [b"1"]
    assert h1.getlist("bar") == [b"2"]
    assert h1.getlist("buz") == [b"1", b"dos", b"3"]
    assert h1.getlist("hey") == [b"5"]


def test_invalid_value() -> None:
    with pytest.raises(TypeError, match="Unsupported value type"):
        Headers({"foo": object()})
    with pytest.raises(TypeError, match="Unsupported value type"):
        Headers()["foo"] = object()
    with pytest.raises(TypeError, match="Unsupported value type"):
        Headers().setdefault("foo", object())
    with pytest.raises(TypeError, match="Unsupported value type"):
        Headers().setlist("foo", [object()])  # type: ignore[list-item]
