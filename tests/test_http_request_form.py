from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote_to_bytes

import pytest

from scrapy.http import FormRequest, HtmlResponse
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode
from tests.test_http_request import TestRequest


def _buildresponse(body, **kwargs):
    kwargs.setdefault("body", body)
    kwargs.setdefault("url", "http://example.com")
    kwargs.setdefault("encoding", "utf-8")
    return HtmlResponse(**kwargs)


def _qs(req, encoding="utf-8", to_unicode=False):
    qs = req.body if req.method == "POST" else req.url.partition("?")[2]
    uqs = unquote_to_bytes(qs)
    if to_unicode:
        uqs = uqs.decode(encoding)
    return parse_qs(uqs, True)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestFormRequest(TestRequest):
    request_class = FormRequest  # type: ignore[assignment]

    def assertQueryEqual(self, first, second, msg=None):
        first = to_unicode(first).split("&")
        second = to_unicode(second).split("&")
        assert sorted(first) == sorted(second), msg

    def test_empty_formdata(self):
        r1 = self.request_class("http://www.example.com", formdata={})
        assert r1.body == b""

    def test_formdata_overrides_querystring(self):
        data = (("a", "one"), ("a", "two"), ("b", "2"))
        url = self.request_class(
            "http://www.example.com/?a=0&b=1&c=3#fragment", method="GET", formdata=data
        ).url.split("#", maxsplit=1)[0]
        fs = _qs(self.request_class(url, method="GET", formdata=data))
        assert set(fs[b"a"]) == {b"one", b"two"}
        assert fs[b"b"] == [b"2"]
        assert fs.get(b"c") is None

        data = {"a": "1", "b": "2"}
        fs = _qs(
            self.request_class("http://www.example.com/", method="GET", formdata=data)
        )
        assert fs[b"a"] == [b"1"]
        assert fs[b"b"] == [b"2"]

    def test_default_encoding_bytes(self):
        # using default encoding (utf-8)
        data = {b"one": b"two", b"price": b"\xc2\xa3 100"}
        r2 = self.request_class("http://www.example.com", formdata=data)
        assert r2.method == "POST"
        assert r2.encoding == "utf-8"
        self.assertQueryEqual(r2.body, b"price=%C2%A3+100&one=two")
        assert r2.headers[b"Content-Type"] == b"application/x-www-form-urlencoded"

    def test_default_encoding_textual_data(self):
        # using default encoding (utf-8)
        data = {"µ one": "two", "price": "£ 100"}
        r2 = self.request_class("http://www.example.com", formdata=data)
        assert r2.method == "POST"
        assert r2.encoding == "utf-8"
        self.assertQueryEqual(r2.body, b"price=%C2%A3+100&%C2%B5+one=two")
        assert r2.headers[b"Content-Type"] == b"application/x-www-form-urlencoded"

    def test_default_encoding_mixed_data(self):
        # using default encoding (utf-8)
        data = {"\u00b5one": b"two", b"price\xc2\xa3": "\u00a3 100"}
        r2 = self.request_class("http://www.example.com", formdata=data)
        assert r2.method == "POST"
        assert r2.encoding == "utf-8"
        self.assertQueryEqual(r2.body, b"%C2%B5one=two&price%C2%A3=%C2%A3+100")
        assert r2.headers[b"Content-Type"] == b"application/x-www-form-urlencoded"

    def test_custom_encoding_bytes(self):
        data = {b"\xb5 one": b"two", b"price": b"\xa3 100"}
        r2 = self.request_class(
            "http://www.example.com", formdata=data, encoding="latin1"
        )
        assert r2.method == "POST"
        assert r2.encoding == "latin1"
        self.assertQueryEqual(r2.body, b"price=%A3+100&%B5+one=two")
        assert r2.headers[b"Content-Type"] == b"application/x-www-form-urlencoded"

    def test_custom_encoding_textual_data(self):
        data = {"price": "£ 100"}
        r3 = self.request_class(
            "http://www.example.com", formdata=data, encoding="latin1"
        )
        assert r3.encoding == "latin1"
        assert r3.body == b"price=%A3+100"

    def test_multi_key_values(self):
        # using multiples values for a single key
        data = {"price": "\xa3 100", "colours": ["red", "blue", "green"]}
        r3 = self.request_class("http://www.example.com", formdata=data)
        self.assertQueryEqual(
            r3.body, b"colours=red&colours=blue&colours=green&price=%C2%A3+100"
        )

    def test_from_response_post(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(
            response, formdata={"one": ["two", "three"], "six": "seven"}
        )

        assert req.method == "POST"
        assert req.headers[b"Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req)
        assert set(fs[b"test"]) == {b"val1", b"val2"}
        assert set(fs[b"one"]) == {b"two", b"three"}
        assert fs[b"test2"] == [b"xxx"]
        assert fs[b"six"] == [b"seven"]

    def test_from_response_post_nonascii_bytes_utf8(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test \xc2\xa3" value="val1">
            <input type="hidden" name="test \xc2\xa3" value="val2">
            <input type="hidden" name="test2" value="xxx \xc2\xb5">
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(
            response, formdata={"one": ["two", "three"], "six": "seven"}
        )

        assert req.method == "POST"
        assert req.headers[b"Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req, to_unicode=True)
        assert set(fs["test £"]) == {"val1", "val2"}
        assert set(fs["one"]) == {"two", "three"}
        assert fs["test2"] == ["xxx µ"]
        assert fs["six"] == ["seven"]

    def test_from_response_post_nonascii_bytes_latin1(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test \xa3" value="val1">
            <input type="hidden" name="test \xa3" value="val2">
            <input type="hidden" name="test2" value="xxx \xb5">
            </form>""",
            url="http://www.example.com/this/list.html",
            encoding="latin1",
        )
        req = self.request_class.from_response(
            response, formdata={"one": ["two", "three"], "six": "seven"}
        )

        assert req.method == "POST"
        assert req.headers[b"Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req, to_unicode=True, encoding="latin1")
        assert set(fs["test £"]) == {"val1", "val2"}
        assert set(fs["one"]) == {"two", "three"}
        assert fs["test2"] == ["xxx µ"]
        assert fs["six"] == ["seven"]

    def test_from_response_post_nonascii_unicode(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test £" value="val1">
            <input type="hidden" name="test £" value="val2">
            <input type="hidden" name="test2" value="xxx µ">
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(
            response, formdata={"one": ["two", "three"], "six": "seven"}
        )

        assert req.method == "POST"
        assert req.headers[b"Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req, to_unicode=True)
        assert set(fs["test £"]) == {"val1", "val2"}
        assert set(fs["one"]) == {"two", "three"}
        assert fs["test2"] == ["xxx µ"]
        assert fs["six"] == ["seven"]

    def test_from_response_duplicate_form_key(self):
        response = _buildresponse("<form></form>", url="http://www.example.com")
        req = self.request_class.from_response(
            response=response,
            method="GET",
            formdata=(("foo", "bar"), ("foo", "baz")),
        )
        assert urlparse_cached(req).hostname == "www.example.com"
        assert urlparse_cached(req).query == "foo=bar&foo=baz"

    def test_from_response_override_duplicate_form_key(self):
        response = _buildresponse(
            """<form action="get.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            </form>"""
        )
        req = self.request_class.from_response(
            response, formdata=(("two", "2"), ("two", "4"))
        )
        fs = _qs(req)
        assert fs[b"one"] == [b"1"]
        assert fs[b"two"] == [b"2", b"4"]

    def test_from_response_extra_headers(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>"""
        )
        req = self.request_class.from_response(
            response=response,
            formdata={"one": ["two", "three"], "six": "seven"},
            headers={"Accept-Encoding": "gzip,deflate"},
        )
        assert req.method == "POST"
        assert req.headers["Content-type"] == b"application/x-www-form-urlencoded"
        assert req.headers["Accept-Encoding"] == b"gzip,deflate"

    def test_from_response_get(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        r1 = self.request_class.from_response(
            response, formdata={"one": ["two", "three"], "six": "seven"}
        )
        assert r1.method == "GET"
        assert urlparse_cached(r1).hostname == "www.example.com"
        assert urlparse_cached(r1).path == "/this/get.php"
        fs = _qs(r1)
        assert set(fs[b"test"]) == {b"val1", b"val2"}
        assert set(fs[b"one"]) == {b"two", b"three"}
        assert fs[b"test2"] == [b"xxx"]
        assert fs[b"six"] == [b"seven"]

    def test_from_response_override_params(self):
        response = _buildresponse(
            """<form action="get.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            </form>"""
        )
        req = self.request_class.from_response(response, formdata={"two": "2"})
        fs = _qs(req)
        assert fs[b"one"] == [b"1"]
        assert fs[b"two"] == [b"2"]

    def test_from_response_drop_params(self):
        response = _buildresponse(
            """<form action="get.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            </form>"""
        )
        req = self.request_class.from_response(response, formdata={"two": None})
        fs = _qs(req)
        assert fs[b"one"] == [b"1"]
        assert b"two" not in fs

    def test_from_response_override_method(self):
        response = _buildresponse(
            """<html><body>
            <form action="/app"></form>
            </body></html>"""
        )
        request = FormRequest.from_response(response)
        assert request.method == "GET"
        request = FormRequest.from_response(response, method="POST")
        assert request.method == "POST"

    def test_from_response_override_url(self):
        response = _buildresponse(
            """<html><body>
            <form action="/app"></form>
            </body></html>"""
        )
        request = FormRequest.from_response(response)
        assert request.url == "http://example.com/app"
        request = FormRequest.from_response(response, url="http://foo.bar/absolute")
        assert request.url == "http://foo.bar/absolute"
        request = FormRequest.from_response(response, url="/relative")
        assert request.url == "http://example.com/relative"

    def test_from_response_case_insensitive(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="SuBmIt" name="clickable1" value="clicked1">
            <input type="iMaGe" name="i1" src="http://my.image.org/1.jpg">
            <input type="submit" name="clickable2" value="clicked2">
            </form>"""
        )
        req = self.request_class.from_response(response)
        fs = _qs(req)
        assert fs[b"clickable1"] == [b"clicked1"]
        assert b"i1" not in fs, fs  # xpath in _get_inputs()
        assert b"clickable2" not in fs, fs  # xpath in _get_clickable()

    def test_from_response_submit_first_clickable(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>"""
        )
        req = self.request_class.from_response(response, formdata={"two": "2"})
        fs = _qs(req)
        assert fs[b"clickable1"] == [b"clicked1"]
        assert b"clickable2" not in fs, fs
        assert fs[b"one"] == [b"1"]
        assert fs[b"two"] == [b"2"]

    def test_from_response_submit_not_first_clickable(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>"""
        )
        req = self.request_class.from_response(
            response, formdata={"two": "2"}, clickdata={"name": "clickable2"}
        )
        fs = _qs(req)
        assert fs[b"clickable2"] == [b"clicked2"]
        assert b"clickable1" not in fs, fs
        assert fs[b"one"] == [b"1"]
        assert fs[b"two"] == [b"2"]

    def test_from_response_dont_submit_image_as_input(self):
        response = _buildresponse(
            """<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="image" name="i2" src="http://my.image.org/1.jpg">
            <input type="submit" name="i3" value="i3v">
            </form>"""
        )
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v"]}

    def test_from_response_dont_submit_reset_as_input(self):
        response = _buildresponse(
            """<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="text" name="i2" value="i2v">
            <input type="reset" name="resetme">
            <input type="submit" name="i3" value="i3v">
            </form>"""
        )
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v"], b"i2": [b"i2v"]}

    def test_from_response_clickdata_does_not_ignore_image(self):
        response = _buildresponse(
            """<form>
            <input type="text" name="i1" value="i1v">
            <input id="image" name="i2" type="image" value="i2v" alt="Login" src="http://my.image.org/1.jpg">
            </form>"""
        )
        req = self.request_class.from_response(response)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v"], b"i2": [b"i2v"]}

    def test_from_response_multiple_clickdata(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable" value="clicked1">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="one" value="clicked1">
            <input type="hidden" name="two" value="clicked2">
            </form>"""
        )
        req = self.request_class.from_response(
            response, clickdata={"name": "clickable", "value": "clicked2"}
        )
        fs = _qs(req)
        assert fs[b"clickable"] == [b"clicked2"]
        assert fs[b"one"] == [b"clicked1"]
        assert fs[b"two"] == [b"clicked2"]

    def test_from_response_unicode_clickdata(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="price in \u00a3" value="\u00a3 1000">
            <input type="submit" name="price in \u20ac" value="\u20ac 2000">
            <input type="hidden" name="poundsign" value="\u00a3">
            <input type="hidden" name="eurosign" value="\u20ac">
            </form>"""
        )
        req = self.request_class.from_response(
            response, clickdata={"name": "price in \u00a3"}
        )
        fs = _qs(req, to_unicode=True)
        assert fs["price in \u00a3"]

    def test_from_response_unicode_clickdata_latin1(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="price in \u00a3" value="\u00a3 1000">
            <input type="submit" name="price in \u00a5" value="\u00a5 2000">
            <input type="hidden" name="poundsign" value="\u00a3">
            <input type="hidden" name="yensign" value="\u00a5">
            </form>""",
            encoding="latin1",
        )
        req = self.request_class.from_response(
            response, clickdata={"name": "price in \u00a5"}
        )
        fs = _qs(req, to_unicode=True, encoding="latin1")
        assert fs["price in \u00a5"]

    def test_from_response_multiple_forms_clickdata(self):
        response = _buildresponse(
            """<form name="form1">
            <input type="submit" name="clickable" value="clicked1">
            <input type="hidden" name="field1" value="value1">
            </form>
            <form name="form2">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="field2" value="value2">
            </form>
            """
        )
        req = self.request_class.from_response(
            response, formname="form2", clickdata={"name": "clickable"}
        )
        fs = _qs(req)
        assert fs[b"clickable"] == [b"clicked2"]
        assert fs[b"field2"] == [b"value2"]
        assert b"field1" not in fs, fs

    def test_from_response_override_clickable(self):
        response = _buildresponse(
            """<form><input type="submit" name="clickme" value="one"> </form>"""
        )
        req = self.request_class.from_response(
            response, formdata={"clickme": "two"}, clickdata={"name": "clickme"}
        )
        fs = _qs(req)
        assert fs[b"clickme"] == [b"two"]

    def test_from_response_dont_click(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>"""
        )
        r1 = self.request_class.from_response(response, dont_click=True)
        fs = _qs(r1)
        assert b"clickable1" not in fs, fs
        assert b"clickable2" not in fs, fs

    def test_from_response_ambiguous_clickdata(self):
        response = _buildresponse(
            """
            <form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>"""
        )
        with pytest.raises(
            ValueError,
            match=r"Multiple elements found .* matching the criteria in clickdata",
        ):
            self.request_class.from_response(response, clickdata={"type": "submit"})

    def test_from_response_non_matching_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable" value="clicked">
            </form>"""
        )
        with pytest.raises(
            ValueError, match="No clickable element matching clickdata:"
        ):
            self.request_class.from_response(
                response, clickdata={"nonexistent": "notme"}
            )

    def test_from_response_nr_index_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable1" value="clicked1">
            <input type="submit" name="clickable2" value="clicked2">
            </form>
            """
        )
        req = self.request_class.from_response(response, clickdata={"nr": 1})
        fs = _qs(req)
        assert b"clickable2" in fs
        assert b"clickable1" not in fs

    def test_from_response_invalid_nr_index_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable" value="clicked">
            </form>
            """
        )
        with pytest.raises(
            ValueError, match="No clickable element matching clickdata:"
        ):
            self.request_class.from_response(response, clickdata={"nr": 1})

    def test_from_response_errors_noform(self):
        response = _buildresponse("""<html></html>""")
        with pytest.raises(ValueError, match="No <form> element found in"):
            self.request_class.from_response(response)

    def test_from_response_invalid_html5(self):
        response = _buildresponse(
            """<!DOCTYPE html><body></html><form>"""
            """<input type="text" name="foo" value="xxx">"""
            """</form></body></html>"""
        )
        req = self.request_class.from_response(response, formdata={"bar": "buz"})
        fs = _qs(req)
        assert fs == {b"foo": [b"xxx"], b"bar": [b"buz"]}

    def test_from_response_errors_formnumber(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>"""
        )
        with pytest.raises(IndexError):
            self.request_class.from_response(response, formnumber=1)

    def test_from_response_noformname(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>"""
        )
        r1 = self.request_class.from_response(response, formdata={"two": "3"})
        assert r1.method == "POST"
        assert r1.headers["Content-type"] == b"application/x-www-form-urlencoded"
        fs = _qs(r1)
        assert fs == {b"one": [b"1"], b"two": [b"3"]}

    def test_from_response_formname_exists(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>"""
        )
        r1 = self.request_class.from_response(response, formname="form2")
        assert r1.method == "POST"
        fs = _qs(r1)
        assert fs == {b"four": [b"4"], b"three": [b"3"]}

    def test_from_response_formname_nonexistent(self):
        response = _buildresponse(
            """<form name="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>"""
        )
        r1 = self.request_class.from_response(response, formname="form3")
        assert r1.method == "POST"
        fs = _qs(r1)
        assert fs == {b"one": [b"1"]}

    def test_from_response_formname_errors_formnumber(self):
        response = _buildresponse(
            """<form name="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>"""
        )
        with pytest.raises(IndexError):
            self.request_class.from_response(response, formname="form3", formnumber=2)

    def test_from_response_formid_exists(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form id="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>"""
        )
        r1 = self.request_class.from_response(response, formid="form2")
        assert r1.method == "POST"
        fs = _qs(r1)
        assert fs == {b"four": [b"4"], b"three": [b"3"]}

    def test_from_response_formname_nonexistent_fallback_formid(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form id="form2" name="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>"""
        )
        r1 = self.request_class.from_response(
            response, formname="form3", formid="form2"
        )
        assert r1.method == "POST"
        fs = _qs(r1)
        assert fs == {b"four": [b"4"], b"three": [b"3"]}

    def test_from_response_formid_nonexistent(self):
        response = _buildresponse(
            """<form id="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form id="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>"""
        )
        r1 = self.request_class.from_response(response, formid="form3")
        assert r1.method == "POST"
        fs = _qs(r1)
        assert fs == {b"one": [b"1"]}

    def test_from_response_formid_errors_formnumber(self):
        response = _buildresponse(
            """<form id="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form id="form2" name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>"""
        )
        with pytest.raises(IndexError):
            self.request_class.from_response(response, formid="form3", formnumber=2)

    def test_from_response_select(self):
        res = _buildresponse(
            """<form>
            <select name="i1">
                <option value="i1v1">option 1</option>
                <option value="i1v2" selected>option 2</option>
            </select>
            <select name="i2">
                <option value="i2v1">option 1</option>
                <option value="i2v2">option 2</option>
            </select>
            <select>
                <option value="i3v1">option 1</option>
                <option value="i3v2">option 2</option>
            </select>
            <select name="i4" multiple>
                <option value="i4v1">option 1</option>
                <option value="i4v2" selected>option 2</option>
                <option value="i4v3" selected>option 3</option>
            </select>
            <select name="i5" multiple>
                <option value="i5v1">option 1</option>
                <option value="i5v2">option 2</option>
            </select>
            <select name="i6"></select>
            <select name="i7"/>
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req, to_unicode=True)
        assert fs == {"i1": ["i1v2"], "i2": ["i2v1"], "i4": ["i4v2", "i4v3"]}

    def test_from_response_radio(self):
        res = _buildresponse(
            """<form>
            <input type="radio" name="i1" value="i1v1">
            <input type="radio" name="i1" value="iv2" checked>
            <input type="radio" name="i2" checked>
            <input type="radio" name="i2">
            <input type="radio" name="i3" value="i3v1">
            <input type="radio" name="i3">
            <input type="radio" value="i4v1">
            <input type="radio">
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert fs == {b"i1": [b"iv2"], b"i2": [b"on"]}

    def test_from_response_checkbox(self):
        res = _buildresponse(
            """<form>
            <input type="checkbox" name="i1" value="i1v1">
            <input type="checkbox" name="i1" value="iv2" checked>
            <input type="checkbox" name="i2" checked>
            <input type="checkbox" name="i2">
            <input type="checkbox" name="i3" value="i3v1">
            <input type="checkbox" name="i3">
            <input type="checkbox" value="i4v1">
            <input type="checkbox">
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert fs == {b"i1": [b"iv2"], b"i2": [b"on"]}

    def test_from_response_input_text(self):
        res = _buildresponse(
            """<form>
            <input type="text" name="i1" value="i1v1">
            <input type="text" name="i2">
            <input type="text" value="i3v1">
            <input type="text">
            <input name="i4" value="i4v1">
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v1"], b"i2": [b""], b"i4": [b"i4v1"]}

    def test_from_response_input_hidden(self):
        res = _buildresponse(
            """<form>
            <input type="hidden" name="i1" value="i1v1">
            <input type="hidden" name="i2">
            <input type="hidden" value="i3v1">
            <input type="hidden">
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v1"], b"i2": [b""]}

    def test_from_response_input_textarea(self):
        res = _buildresponse(
            """<form>
            <textarea name="i1">i1v</textarea>
            <textarea name="i2"></textarea>
            <textarea name="i3"/>
            <textarea>i4v</textarea>
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert fs == {b"i1": [b"i1v"], b"i2": [b""], b"i3": [b""]}

    def test_from_response_descendants(self):
        res = _buildresponse(
            """<form>
            <div>
              <fieldset>
                <input type="text" name="i1">
                <select name="i2">
                    <option value="v1" selected>
                </select>
              </fieldset>
              <input type="radio" name="i3" value="i3v2" checked>
              <input type="checkbox" name="i4" value="i4v2" checked>
              <textarea name="i5"></textarea>
              <input type="hidden" name="h1" value="h1v">
              </div>
            <input type="hidden" name="h2" value="h2v">
            </form>"""
        )
        req = self.request_class.from_response(res)
        fs = _qs(req)
        assert set(fs) == {b"h2", b"i2", b"i1", b"i3", b"h1", b"i5", b"i4"}

    def test_from_response_xpath(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form action="post2.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>"""
        )
        r1 = self.request_class.from_response(
            response, formxpath="//form[@action='post.php']"
        )
        fs = _qs(r1)
        assert fs[b"one"] == [b"1"]

        r1 = self.request_class.from_response(
            response, formxpath="//form/input[@name='four']"
        )
        fs = _qs(r1)
        assert fs[b"three"] == [b"3"]

        with pytest.raises(ValueError, match="No <form> element found with"):
            self.request_class.from_response(
                response, formxpath="//form/input[@name='abc']"
            )

    def test_from_response_unicode_xpath(self):
        response = _buildresponse(b'<form name="\xd1\x8a"></form>')
        r = self.request_class.from_response(
            response, formxpath="//form[@name='\u044a']"
        )
        fs = _qs(r)
        assert not fs

        xpath = "//form[@name='\u03b1']"
        with pytest.raises(ValueError, match=re.escape(xpath)):
            self.request_class.from_response(response, formxpath=xpath)

    def test_from_response_button_submit(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button type="submit" name="button1" value="submit1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(response)
        assert req.method == "POST"
        assert req.headers["Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req)
        assert fs[b"test1"] == [b"val1"]
        assert fs[b"test2"] == [b"val2"]
        assert fs[b"button1"] == [b"submit1"]

    def test_from_response_button_notype(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button name="button1" value="submit1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(response)
        assert req.method == "POST"
        assert req.headers["Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req)
        assert fs[b"test1"] == [b"val1"]
        assert fs[b"test2"] == [b"val2"]
        assert fs[b"button1"] == [b"submit1"]

    def test_from_response_submit_novalue(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <input type="submit" name="button1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(response)
        assert req.method == "POST"
        assert req.headers["Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req)
        assert fs[b"test1"] == [b"val1"]
        assert fs[b"test2"] == [b"val2"]
        assert fs[b"button1"] == [b""]

    def test_from_response_button_novalue(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button type="submit" name="button1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html",
        )
        req = self.request_class.from_response(response)
        assert req.method == "POST"
        assert req.headers["Content-type"] == b"application/x-www-form-urlencoded"
        assert req.url == "http://www.example.com/this/post.php"
        fs = _qs(req)
        assert fs[b"test1"] == [b"val1"]
        assert fs[b"test2"] == [b"val2"]
        assert fs[b"button1"] == [b""]

    def test_html_base_form_action(self):
        response = _buildresponse(
            """
            <html>
                <head>
                    <base href=" http://b.com/">
                </head>
                <body>
                    <form action="test_form">
                    </form>
                </body>
            </html>
            """,
            url="http://a.com/",
        )
        req = self.request_class.from_response(response)
        assert req.url == "http://b.com/test_form"

    def test_spaces_in_action(self):
        resp = _buildresponse('<body><form action=" path\n"></form></body>')
        req = self.request_class.from_response(resp)
        assert req.url == "http://example.com/path"

    def test_from_response_css(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form action="post2.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>"""
        )
        r1 = self.request_class.from_response(
            response, formcss="form[action='post.php']"
        )
        fs = _qs(r1)
        assert fs[b"one"] == [b"1"]

        r1 = self.request_class.from_response(response, formcss="input[name='four']")
        fs = _qs(r1)
        assert fs[b"three"] == [b"3"]

        with pytest.raises(ValueError, match="No <form> element found with"):
            self.request_class.from_response(response, formcss="input[name='abc']")

    def test_from_response_valid_form_methods(self):
        form_methods = [
            [method, method] for method in self.request_class.valid_form_methods
        ]
        form_methods.append(["UNKNOWN", "GET"])

        for method, expected in form_methods:
            response = _buildresponse(
                f'<form action="post.php" method="{method}">'
                '<input type="hidden" name="one" value="1">'
                "</form>"
            )
            r = self.request_class.from_response(response)
            assert r.method == expected

    def test_form_response_with_invalid_formdata_type_error(self):
        """Test that a ValueError is raised for non-iterable and non-dict formdata input"""
        response = _buildresponse(
            """<html><body>
            <form action="/submit" method="post">
                <input type="text" name="test" value="value">
            </form>
            </body></html>"""
        )
        with pytest.raises(
            ValueError, match="formdata should be a dict or iterable of tuples"
        ):
            FormRequest.from_response(response, formdata=123)

    def test_form_response_with_custom_invalid_formdata_value_error(self):
        """Test that a ValueError is raised for fault-inducing iterable formdata input"""
        response = _buildresponse(
            """<html><body>
                <form action="/submit" method="post">
                    <input type="text" name="test" value="value">
                </form>
            </body></html>"""
        )

        with pytest.raises(
            ValueError, match="formdata should be a dict or iterable of tuples"
        ):
            FormRequest.from_response(response, formdata=("a",))

    def test_get_form_with_xpath_no_form_parent(self):
        """Test that _get_from raised a ValueError when an XPath selects an element
        not nested within a <form> and no <form> parent is found"""
        response = _buildresponse(
            """<html><body>
                <div id="outside-form">
                    <p>This paragraph is not inside a form.</p>
                </div>
                <form action="/submit" method="post">
                    <input type="text" name="inside-form" value="">
                </form>
            </body></html>"""
        )

        with pytest.raises(ValueError, match="No <form> element found with"):
            FormRequest.from_response(response, formxpath='//div[@id="outside-form"]/p')
