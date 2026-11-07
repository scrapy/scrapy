from __future__ import annotations


import warnings
from typing import Any


import pytest
from w3lib.http import basic_auth_header

from scrapy import Request
from scrapy.utils.curl import curl_to_request_kwargs


class TestCurlToRequestKwargs:
    @staticmethod
    def _test_command(curl_command: str, expected_result: dict[str, Any]) -> None:
        result = curl_to_request_kwargs(curl_command)
        assert result == expected_result
        try:
            Request(**result)
        except TypeError as e:
            pytest.fail(f"Request kwargs are not correct {e}")

    def test_get(self):
        curl_command = "curl http://example.org/"
        expected_result = {"method": "GET", "url": "http://example.org/"}
        self._test_command(curl_command, expected_result)

    def test_get_url_with_escaped_space(self):
        curl_command = r"curl http://example.org/a\ b"
        expected_result = {
            "method": "GET",
            "url": "http://example.org/a b",
        }
        self._test_command(curl_command, expected_result)

    def test_get_without_scheme(self):
        curl_command = "curl www.example.org"
        expected_result = {"method": "GET", "url": "http://www.example.org"}
        self._test_command(curl_command, expected_result)

    def test_get_basic_auth(self):
        curl_command = 'curl "https://api.test.com/" -u "some_username:some_password"'
        expected_result = {
            "method": "GET",
            "url": "https://api.test.com/",
            "headers": [
                ("Authorization", basic_auth_header("some_username", "some_password"))
            ],
        }
        self._test_command(curl_command, expected_result)

    @pytest.mark.parametrize("auth", ["some_username", "some_username:"])
    def test_get_basic_auth_without_password(self, auth):
        curl_command = f'curl "https://api.test.com/" -u "{auth}"'
        expected_result = {
            "method": "GET",
            "url": "https://api.test.com/",
            "headers": [("Authorization", basic_auth_header("some_username", ""))],
        }
        self._test_command(curl_command, expected_result)

    def test_get_header_with_empty_value(self):
        curl_command = 'curl "http://example.org/" -H "X-Flag;"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "headers": [("X-Flag", "")],
        }
        self._test_command(curl_command, expected_result)

    def test_get_header_with_value_containing_colon(self):
        curl_command = 'curl "http://example.org/" -H "X-Time: 12:34:56"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "headers": [("X-Time", "12:34:56")],
        }
        self._test_command(curl_command, expected_result)

    def test_get_header_with_value_containing_colon_no_space(self):
        curl_command = 'curl "http://example.org/" -H "X-Time:12:34:56"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "headers": [("X-Time", "12:34:56")],
        }
        self._test_command(curl_command, expected_result)

    def test_get_header_without_value(self):
        curl_command = 'curl "http://example.org/" -H "X-Flag"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "headers": [("X-Flag", "")],
        }
        self._test_command(curl_command, expected_result)

    def test_get_cookie(self):
        curl_command = 'curl "http://example.org/" -H "Cookie: foo=bar"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "cookies": {"foo": "bar"},
        }
        self._test_command(curl_command, expected_result)

    def test_get_cookie_with_empty_value(self):
        curl_command = 'curl "http://example.org/" -H "Cookie: foo="'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "cookies": {"foo": ""},
        }
        self._test_command(curl_command, expected_result)

    def test_get_multiple_cookies(self):
        curl_command = 'curl "http://example.org/" -b "lorem=ipsum; dolor=sit"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "cookies": {"lorem": "ipsum", "dolor": "sit"},
        }
        self._test_command(curl_command, expected_result)

    def test_get_cookie_splitted_by_equal_sign(self):
        curl_command = 'curl "http://example.org/" -b "lorem=ips=um"'
        expected_result = {
            "method": "GET",
            "url": "http://example.org/",
            "cookies": {"lorem": "ips=um"},
        }
        self._test_command(curl_command, expected_result)

    def test_get_complex(self):
        curl_command = (
            "curl 'http://httpbin.org/get' -H 'Accept-Encoding: gzip, deflate'"
            " -H 'Accept-Language: en-US,en;q=0.9,ru;q=0.8,es;q=0.7' -H 'Upgra"
            "de-Insecure-Requests: 1' -H 'User-Agent: Mozilla/5.0 (X11; Linux "
            "x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62"
            ".0.3202.75 Chrome/62.0.3202.75 Safari/537.36' -H 'Accept: text/ht"
            "ml,application/xhtml+xml,application/xml;q=0.9,image/webp,image/a"
            "png,*/*;q=0.8' -H 'Referer: http://httpbin.org/' -H 'Cookie: _gau"
            "ges_unique_year=1; _gauges_unique=1; _gauges_unique_month=1; _gau"
            "ges_unique_hour=1' -H 'Connection: keep-alive' --compressed -b '_"
            "gauges_unique_day=1'"
        )
        expected_result = {
            "method": "GET",
            "url": "http://httpbin.org/get",
            "headers": [
                ("Accept-Encoding", "gzip, deflate"),
                ("Accept-Language", "en-US,en;q=0.9,ru;q=0.8,es;q=0.7"),
                ("Upgrade-Insecure-Requests", "1"),
                (
                    "User-Agent",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML,"
                    " like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202"
                    ".75 Safari/537.36",
                ),
                (
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,imag"
                    "e/webp,image/apng,*/*;q=0.8",
                ),
                ("Referer", "http://httpbin.org/"),
                ("Connection", "keep-alive"),
            ],
            "cookies": {
                "_gauges_unique_year": "1",
                "_gauges_unique": "1",
                "_gauges_unique_month": "1",
                "_gauges_unique_hour": "1",
                "_gauges_unique_day": "1",
            },
        }
        # double-check that expected headers parse in the same way
        self._test_command(curl_command, expected_result)

    def test_post(self):
        curl_command = (
            "curl 'http://httpbin.org/post' -H 'Accept-Encoding: gzip, deflate'"
            " -H 'Accept-Language: en-US,en;q=0.9,ru;q=0.8,es;q=0.7' -H 'Upgra"
            "de-Insecure-Requests: 1' -H 'User-Agent: Mozilla/5.0 (X11; Linux "
            "x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62"
            ".0.3202.75 Chrome/62.0.3202.75 Safari/537.36' -H 'Content-Type: ap"
            "plication/x-www-form-urlencoded; charset=UTF-8' -H 'Accept: */*' "
            "-H 'Referer: http://httpbin.org/' -H 'Cookie: _gauges_unique_yea"
            "r=1; _gauges_unique=1; _gauges_unique_month=1; _gauges_unique_ho"
            "ur=1' -H 'Connection: keep-alive' --data 'custname=dd&custtel=&"
            "custemail=&delivery=&comments=' --compressed"
        )

        expected_result = {
            "method": "POST",
            "url": "http://httpbin.org/post",
            "headers": [
                ("Accept-Encoding", "gzip, deflate"),
                ("Accept-Language", "en-US,en;q=0.9,ru;q=0.8,es;q=0.7"),
                ("Upgrade-Insecure-Requests", "1"),
                (
                    "User-Agent",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML,"
                    " like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202"
                    ".75 Safari/537.36",
                ),
                (
                    "Content-Type",
                    "application/x-www-form-urlencoded; charset=UTF-8",
                ),
                ("Accept", "*/*"),
                ("Referer", "http://httpbin.org/"),
                ("Connection", "keep-alive"),
            ],
            "cookies": {
                "_gauges_unique_year": "1",
                "_gauges_unique": "1",
                "_gauges_unique_month": "1",
                "_gauges_unique_hour": "1",
            },
            "body": "custname=dd&custtel=&custemail=&delivery=&comments=",
        }
        self._test_command(curl_command, expected_result)

    def test_patch(self):
        curl_command = "curl 'http://httpbin.org/patch' -X PATCH --data 'foo=bar'"
        expected_result = {
            "method": "PATCH",
            "url": "http://httpbin.org/patch",
            "body": "foo=bar",
        }
        self._test_command(curl_command, expected_result)

    def test_post_data_raw(self):
        curl_command = "curl 'https://www.example.org/' --data-raw $'{\"$filters\":\"Filter\\u0021\"}'"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": '{"$filters":"Filter!"}',
        }
        self._test_command(curl_command, expected_result)

    def test_post_data_raw_with_dollar(self):
        curl_command = "curl 'https://www.example.org/' --data-raw 'a=$b' --data-raw 'c=d'"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": "a=$b&c=d",
        }
        self._test_command(curl_command, expected_result)

    def test_post_data_raw_spaces(self):
        curl_command = "curl 'https://www.example.org/' --data-raw '${HOME} not home'"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": "${HOME} not home",
        }
        self._test_command(curl_command, expected_result)

    def test_post_data_raw_multiple_different_options_repeat(self):
        curl_command = "curl 'https://www.example.org/' --data 'a=b' --data-raw 'c=d'"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": "a=b&c=d",
        }
        self._test_command(curl_command, expected_result)

    def test_post_empty_data_raw(self):
        curl_command = "curl 'https://www.example.org/' --data-raw ''"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": "",
        }
        self._test_command(curl_command, expected_result)

    def test_get_empty_data_raw(self):
        curl_command = "curl 'https://www.example.org/' -d ''"
        expected_result = {
            "method": "POST",
            "url": "https://www.example.org/",
            "body": "",
        }
        self._test_command(curl_command, expected_result)

    @pytest.mark.parametrize("ignore_unknown_options", [True, False])
    def test_unknown_option(self, ignore_unknown_options):
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = curl_to_request_kwargs("curl --unknown-option example.org")
        assert result == {"method": "GET", "url": "http://example.org"}
        assert len(caught_warnings) == 1
        assert issubclass(caught_warnings[0].category, UserWarning)
        assert str(caught_warnings[0].message) == "Unrecognized options: --unknown-option"

    def test_unknown_option_raises_error_if_asked(self):
        with pytest.raises(ValueError, match="Unrecognized options: --unknown-option"):
            curl_to_request_kwargs("curl --unknown-option example.org", ignore_unknown_options=False)

    def test_unknown_options(self):
        with pytest.warns(UserWarning, match="Unrecognized options: --bar, --baz"):
            result = curl_to_request_kwargs("curl --bar --baz http://www.example.com")
        assert result == {"method": "GET", "url": "http://www.example.com"}

    def test_unknown_options_raise_error_if_asked(self):
        with pytest.raises(ValueError, match="Unrecognized options: --bar, --baz"):
            curl_to_request_kwargs(
                "curl --bar --baz http://www.example.com", ignore_unknown_options=False
            )

    @pytest.mark.parametrize(
        "curl_command",
        [
            "curl -x http://127.0.0.1:8080 https://www.example.com/get",
            "curl -A ua/1 https://www.example.com/get",
            "curl --max-time 5 https://www.example.com/get",
            "curl https://www.example.com/get -x http://127.0.0.1:8080",
            "curl --proxy=http://127.0.0.1:8080 https://www.example.com/get",
        ],
    )
    def test_unknown_option_value_is_not_the_url(self, curl_command):
        # The value of an unrecognized option is not the URL, and the real
        # URL must not be dropped in favour of it.
        expected_result = {"method": "GET", "url": "https://www.example.com/get"}
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", category=UserWarning, message="Unrecognized options:"
            )
            self._test_command(curl_command, expected_result)

    def test_unknown_option_value_reported_as_unrecognized(self):
        with pytest.warns(
            UserWarning,
            match=r"Unrecognized options: -x, http://127\.0\.0\.1:8080",
        ):
            result = curl_to_request_kwargs(
                "curl -x http://127.0.0.1:8080 https://www.example.com/get"
            )
        assert result["url"] == "https://www.example.com/get"

    def test_must_start_with_curl_error(self):
        with pytest.raises(ValueError, match="A curl command must start"):
            curl_to_request_kwargs("carl -X POST http://example.org")
