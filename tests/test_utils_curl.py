import unittest

from scrapy.utils.curl import curl_to_request_kwargs
from scrapy import Request


class ParseCurlCmdTest(unittest.TestCase):
    maxDiff = 5000

    def test_basic(self):
        curl_cmd = (
            "curl 'http://httpbin.org/get'"
            " -H 'Accept-Encoding: gzip, deflate'"
            " -H 'Accept-Language: en-US,en;q=0.9,ru;q=0.8,es;q=0.7'"
            " -H 'Upgrade-Insecure-Requests: 1'"
            " -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 Safari/537.36' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'"
            " -H 'Referer: http://httpbin.org/'"
            " -H 'Cookie: _gauges_unique_year=1; _gauges_unique=1; _gauges_unique_month=1; _gauges_unique_hour=1; _gauges_unique_day=1'"
            " -H 'Connection: keep-alive'"
            " --compressed"
        ).strip()

        result = curl_to_request_kwargs(curl_cmd)
        self.assertEqual(result, {
            'method': 'GET',
            'url': 'http://httpbin.org/get',
            'headers': [
                ('Accept-Encoding', 'gzip, deflate'),
                ('Accept-Language', 'en-US,en;q=0.9,ru;q=0.8,es;q=0.7'),
                ('Upgrade-Insecure-Requests', '1'),
                ('User-Agent',
                 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 Safari/537.36'),
                ('Accept',
                 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'),
                ('Referer', 'http://httpbin.org/'),
                ('Connection', 'keep-alive')
            ],
            'cookies': dict([
                ('_gauges_unique_year', '1'),
                ('_gauges_unique_hour', '1'),
                ('_gauges_unique_day', '1'),
                ('_gauges_unique', '1'),
                ('_gauges_unique_month', '1')
            ]),
        })
        Request(**result)

    def test_post_data(self):
        curl_cmd = """
        curl 'http://httpbin.org/post' -H 'Cookie: _gauges_unique_year=1; _gauges_unique=1; _gauges_unique_month=1; _gauges_unique_hour=1; _gauges_unique_day=1' -H 'Origin: http://httpbin.org' -H 'Accept-Encoding: gzip, deflate' -H 'Accept-Language: en-US,en;q=0.9,ru;q=0.8,es;q=0.7' -H 'Upgrade-Insecure-Requests: 1' -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 Safari/537.36' -H 'Content-Type: application/x-www-form-urlencoded' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8' -H 'Cache-Control: max-age=0' -H 'Referer: http://httpbin.org/forms/post' -H 'Connection: keep-alive' --data 'custname=John+Smith&custtel=500&custemail=jsmith%40example.org&size=small&topping=cheese&topping=onion&delivery=12%3A15&comments=' --compressed
        """.strip()
        result = curl_to_request_kwargs(curl_cmd)
        self.assertEqual(result, {
            'method': 'GET',
            'url': 'http://httpbin.org/post',
            'body': 'custname=John+Smith&custtel=500&custemail=jsmith%40example.org&size=small&topping=cheese&topping=onion&delivery=12%3A15&comments=',
            'cookies': dict([
                ('_gauges_unique_year', '1'),
                ('_gauges_unique_hour', '1'),
                ('_gauges_unique_day', '1'),
                ('_gauges_unique', '1'),
                ('_gauges_unique_month', '1')
            ]),
            'headers': [
                ('Origin', 'http://httpbin.org'),
                ('Accept-Encoding', 'gzip, deflate'),
                ('Accept-Language', 'en-US,en;q=0.9,ru;q=0.8,es;q=0.7'),
                ('Upgrade-Insecure-Requests', '1'),
                ('User-Agent',
                 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 Safari/537.36'),
                ('Content-Type', 'application/x-www-form-urlencoded'),
                ('Accept',
                 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'),
                ('Cache-Control', 'max-age=0'),
                ('Referer', 'http://httpbin.org/forms/post'),
                ('Connection', 'keep-alive')
            ],
        })
        Request(**result)

    def test_too_few_arguments_error(self):
        self.assertRaisesRegexp(
            ValueError,
            'too few arguments|the following arguments are required:\s*url',
            lambda: curl_to_request_kwargs('foobarbaz'))

    def test_unknown_arg_error(self):
        self.assertRaisesRegexp(
            ValueError, 'Unrecognized arguments:.*--bar.*--baz',
            lambda: curl_to_request_kwargs('foo --bar --baz url'))

    def test_list_args(self):
        result = curl_to_request_kwargs(['curl', 'http://example.org'])
        self.assertEqual(
            result, {
                'method': 'GET',
                'url': 'http://example.org',
            }
        )
