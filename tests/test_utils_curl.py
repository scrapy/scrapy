import unittest
import warnings

from w3lib.http import basic_auth_header

from scrapy import Request
from scrapy.utils.curl import curl_to_request_kwargs


class CurlToRequestKwargsTest(unittest.TestCase):
    maxDiff = 5000

    def _test_command(self, curl_command, expected_result):
        result = curl_to_request_kwargs(curl_command)
        self.assertEqual(result, expected_result)
        try:
            Request(**result)
        except TypeError as e:
            self.fail("Request kwargs are not correct {}".format(e))

    def test_get(self):
        curl_command = "curl http://example.org/"
        expected_result = {"method": "GET", "url": "http://example.org/"}
        self._test_command(curl_command, expected_result)

    def test_get_without_scheme(self):
        curl_command = "curl www.example.org"
        expected_result = {"method": "GET", "url": "http://www.example.org"}
        self._test_command(curl_command, expected_result)

    def test_get_basic_auth(self):
        curl_command = 'curl "https://api.test.com/" -u ' \
                       '"some_username:some_password"'
        expected_result = {
            "method": "GET",
            "url": "https://api.test.com/",
            "headers": [
                (
                    "Authorization",
                    basic_auth_header("some_username", "some_password")
                )
            ],
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
            "ges_unique_hour=1; _gauges_unique_day=1' -H 'Connection: keep-ali"
            "ve' --compressed"
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
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML"
                    ", like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.32"
                    "02.75 Safari/537.36",
                ),
                (
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,ima"
                    "ge/webp,image/apng,*/*;q=0.8",
                ),
                ("Referer", "http://httpbin.org/"),
                ("Connection", "keep-alive"),
            ],
            "cookies": {
                '_gauges_unique_year': '1',
                '_gauges_unique_hour': '1',
                '_gauges_unique_day': '1',
                '_gauges_unique': '1',
                '_gauges_unique_month': '1'
            },
        }
        self._test_command(curl_command, expected_result)

    def test_post(self):
        curl_command = (
            "curl 'http://httpbin.org/post' -X POST -H 'Cookie: _gauges_unique"
            "_year=1; _gauges_unique=1; _gauges_unique_month=1; _gauges_unique"
            "_hour=1; _gauges_unique_day=1' -H 'Origin: http://httpbin.org' -H"
            " 'Accept-Encoding: gzip, deflate' -H 'Accept-Language: en-US,en;q"
            "=0.9,ru;q=0.8,es;q=0.7' -H 'Upgrade-Insecure-Requests: 1' -H 'Use"
            "r-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTM"
            "L, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 S"
            "afari/537.36' -H 'Content-Type: application/x-www-form-urlencoded"
            "' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0"
            ".9,image/webp,image/apng,*/*;q=0.8' -H 'Cache-Control: max-age=0'"
            " -H 'Referer: http://httpbin.org/forms/post' -H 'Connection: keep"
            "-alive' --data 'custname=John+Smith&custtel=500&custemail=jsmith%"
            "40example.org&size=small&topping=cheese&topping=onion&delivery=12"
            "%3A15&comments=' --compressed"
        )
        expected_result = {
            "method": "POST",
            "url": "http://httpbin.org/post",
            "body": "custname=John+Smith&custtel=500&custemail=jsmith%40exampl"
                    "e.org&size=small&topping=cheese&topping=onion&delivery=12"
                    "%3A15&comments=",
            "cookies": {
                '_gauges_unique_year': '1',
                '_gauges_unique_hour': '1',
                '_gauges_unique_day': '1',
                '_gauges_unique': '1',
                '_gauges_unique_month': '1'
            },
            "headers": [
                ("Origin", "http://httpbin.org"),
                ("Accept-Encoding", "gzip, deflate"),
                ("Accept-Language", "en-US,en;q=0.9,ru;q=0.8,es;q=0.7"),
                ("Upgrade-Insecure-Requests", "1"),
                (
                    "User-Agent",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML"
                    ", like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.32"
                    "02.75 Safari/537.36",
                ),
                ("Content-Type", "application/x-www-form-urlencoded"),
                (
                    "Accept",
                    "text/html,application/xhtml+xml,application/xml;q=0.9,ima"
                    "ge/webp,image/apng,*/*;q=0.8",
                ),
                ("Cache-Control", "max-age=0"),
                ("Referer", "http://httpbin.org/forms/post"),
                ("Connection", "keep-alive"),
            ],
        }
        self._test_command(curl_command, expected_result)

    def test_patch(self):
        curl_command = (
            'curl "https://example.com/api/fake" -u "username:password" -H "Ac'
            'cept: application/vnd.go.cd.v4+json" -H "Content-Type: applicatio'
            'n/json" -X PATCH -d \'{"hostname": "agent02.example.com",  "agent'
            '_config_state": "Enabled", "resources": ["Java","Linux"], "enviro'
            'nments": ["Dev"]}\''
        )
        expected_result = {
            "method": "PATCH",
            "url": "https://example.com/api/fake",
            "headers": [
                ("Accept", "application/vnd.go.cd.v4+json"),
                ("Content-Type", "application/json"),
                ("Authorization", basic_auth_header("username", "password")),
            ],
            "body": '{"hostname": "agent02.example.com",  "agent_config_state"'
                    ': "Enabled", "resources": ["Java","Linux"], "environments'
                    '": ["Dev"]}',
        }
        self._test_command(curl_command, expected_result)

    def test_delete(self):
        curl_command = 'curl -X "DELETE" https://www.url.com/page'
        expected_result = {
            "method": "DELETE", "url": "https://www.url.com/page"
        }
        self._test_command(curl_command, expected_result)

    def test_get_silent(self):
        curl_command = 'curl --silent "www.example.com"'
        expected_result = {"method": "GET", "url": "http://www.example.com"}
        self.assertEqual(curl_to_request_kwargs(curl_command), expected_result)

    def test_too_few_arguments_error(self):
        self.assertRaisesRegex(
            ValueError,
            r"too few arguments|the following arguments are required:\s*url",
            lambda: curl_to_request_kwargs("curl"),
        )

    def test_ignore_unknown_options(self):
        # case 1: ignore_unknown_options=True:
        with warnings.catch_warnings():  # avoid warning when executing tests
            warnings.simplefilter('ignore')
            curl_command = 'curl --bar --baz http://www.example.com'
            expected_result = \
                {"method": "GET", "url": "http://www.example.com"}
            self.assertEqual(curl_to_request_kwargs(curl_command), expected_result)

        # case 2: ignore_unknown_options=False (raise exception):
        self.assertRaisesRegex(
            ValueError,
            "Unrecognized options:.*--bar.*--baz",
            lambda: curl_to_request_kwargs(
                "curl --bar --baz http://www.example.com",
                ignore_unknown_options=False
            ),
        )

    def test_must_start_with_curl_error(self):
        self.assertRaises(
            ValueError,
            lambda: curl_to_request_kwargs("carl -X POST http://example.org")
        )
