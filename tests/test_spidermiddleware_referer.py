from unittest import TestCase

from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.spidermiddlewares.referer import RefererMiddleware, \
    POLICY_NO_REFERRER, POLICY_NO_REFERRER_WHEN_DOWNGRADE, \
    POLICY_SAME_ORIGIN, POLICY_ORIGIN, POLICY_ORIGIN_WHEN_CROSS_ORIGIN, \
    POLICY_UNSAFE_URL


class TestRefererMiddleware(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = RefererMiddleware()

    def test_process_spider_output(self):
        res = Response('http://scrapytest.org')
        reqs = [Request('http://scrapytest.org/')]

        out = list(self.mw.process_spider_output(res, reqs, self.spider))
        self.assertEquals(out[0].headers.get('Referer'),
                          b'http://scrapytest.org')

    def test_policy_default(self):
        """
        Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

        with some additional filtering of s3://
        """
        for origin, target, referrer in [
                ('https://example.com/',    'https://scrapy.org/',  b'https://example.com/'),
                ('http://example.com/',     'http://scrapy.org/',   b'http://example.com/'),
                ('http://example.com/',     'https://scrapy.org/',  b'http://example.com/'),
                ('https://example.com/',    'http://scrapy.org/',   None),

                # no credentials leak
                ('http://user:password@example.com/',  'https://scrapy.org/', b'http://example.com/'),

                # no referrer leak for local schemes
                ('file:///home/path/to/somefile.html',  'https://scrapy.org/', None),
                ('file:///home/path/to/somefile.html',  'http://scrapy.org/',  None),

                # no referrer leak for s3 origins
                ('s3://mybucket/path/to/data.csv',  'https://scrapy.org/', None),
                ('s3://mybucket/path/to/data.csv',  'http://scrapy.org/',  None),
            ]:
            response = Response(origin)
            request = Request(target)

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_no_referrer(self):

        for origin, target, referrer in [
                ('https://example.com/page.html',       'https://example.com/', None),
                ('http://www.example.com/',             'https://scrapy.org/',  None),
                ('http://www.example.com/',             'http://scrapy.org/',   None),
                ('https://www.example.com/',            'http://scrapy.org/',   None),
                ('file:///home/path/to/somefile.html',  'http://scrapy.org/',   None),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_NO_REFERRER})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_no_referrer_when_downgrade(self):

        for origin, target, referrer in [
                # TLS to TLS: send non-empty referrer
                ('https://example.com/page.html',       'https://not.example.com/', b'https://example.com/page.html'),
                ('https://example.com/page.html',       'https://scrapy.org/',      b'https://example.com/page.html'),
                ('https://example.com:443/page.html',   'https://scrapy.org/',      b'https://example.com/page.html'),
                ('https://example.com:444/page.html',   'https://scrapy.org/',      b'https://example.com:444/page.html'),
                ('ftps://example.com/urls.zip',         'https://scrapy.org/',      b'ftps://example.com/urls.zip'),

                # TLS to non-TLS: do not send referrer
                ('https://example.com/page.html',       'http://not.example.com/',  None),
                ('https://example.com/page.html',       'http://scrapy.org/',       None),
                ('ftps://example.com/urls.zip',         'http://scrapy.org/',       None),

                # non-TLS to TLS or non-TLS: send referrer
                ('http://example.com/page.html',        'https://not.example.com/', b'http://example.com/page.html'),
                ('http://example.com/page.html',        'https://scrapy.org/',      b'http://example.com/page.html'),
                ('http://example.com:8080/page.html',   'https://scrapy.org/',      b'http://example.com:8080/page.html'),
                ('http://example.com:80/page.html',     'http://not.example.com/',  b'http://example.com/page.html'),
                ('http://example.com/page.html',        'http://scrapy.org/',       b'http://example.com/page.html'),
                ('http://example.com:443/page.html',    'http://scrapy.org/',       b'http://example.com:443/page.html'),
                ('ftp://example.com/urls.zip',          'http://scrapy.org/',       b'ftp://example.com/urls.zip'),
                ('ftp://example.com/urls.zip',          'https://scrapy.org/',      b'ftp://example.com/urls.zip'),

                # test for user/password stripping
                ('http://user:password@example.com/page.html', 'https://not.example.com/', b'http://example.com/page.html'),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_NO_REFERRER_WHEN_DOWNGRADE})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_same_origin(self):

        for origin, target, referrer in [
                # Same origin (protocol, host, port): send referrer
                ('https://example.com/page.html',       'https://example.com/not-page.html',        b'https://example.com/page.html'),
                ('http://example.com/page.html',        'http://example.com/not-page.html',         b'http://example.com/page.html'),
                ('https://example.com:443/page.html',   'https://example.com/not-page.html',        b'https://example.com/page.html'),
                ('http://example.com:80/page.html',     'http://example.com/not-page.html',         b'http://example.com/page.html'),
                ('http://example.com/page.html',        'http://example.com:80/not-page.html',      b'http://example.com/page.html'),
                ('http://example.com:8888/page.html',   'http://example.com:8888/not-page.html',    b'http://example.com:8888/page.html'),

                # Different host: do NOT send referrer
                ('https://example.com/page.html',       'https://not.example.com/otherpage.html',   None),
                ('http://example.com/page.html',        'http://not.example.com/otherpage.html',    None),
                ('http://example.com/page.html',        'http://www.example.com/otherpage.html',    None),

                # Different port: do NOT send referrer
                ('https://example.com:444/page.html',   'https://example.com/not-page.html',    None),
                ('http://example.com:81/page.html',     'http://example.com/not-page.html',     None),
                ('http://example.com/page.html',        'http://example.com:81/not-page.html',  None),

                # Different protocols: do NOT send refferer
                ('https://example.com/page.html',   'http://example.com/not-page.html',     None),
                ('https://example.com/page.html',   'http://not.example.com/',              None),
                ('ftps://example.com/urls.zip',     'https://example.com/not-page.html',    None),
                ('ftp://example.com/urls.zip',      'http://example.com/not-page.html',     None),
                ('ftps://example.com/urls.zip',     'https://example.com/not-page.html',    None),

                # test for user/password stripping
                ('https://user:password@example.com/page.html', 'https://example.com/not-page.html',    b'https://example.com/page.html'),
                ('https://user:password@example.com/page.html', 'http://example.com/not-page.html',     None),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_SAME_ORIGIN})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_origin(self):

        for origin, target, referrer in [
                # TLS or non-TLS to TLS or non-TLS: referrer origin is sent (yes, even for downgrades)
                ('https://example.com/page.html',   'https://example.com/not-page.html',    b'https://example.com/'),
                ('https://example.com/page.html',   'https://scrapy.org',                   b'https://example.com/'),
                ('https://example.com/page.html',   'http://scrapy.org',                    b'https://example.com/'),
                ('http://example.com/page.html',    'http://scrapy.org',                    b'http://example.com/'),

                # test for user/password stripping
                ('https://user:password@example.com/page.html', 'http://scrapy.org', b'https://example.com/'),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_ORIGIN})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_origin_when_cross_origin(self):

        for origin, target, referrer in [
                # Same origin (protocol, host, port): send referrer
                ('https://example.com/page.html',       'https://example.com/not-page.html',        b'https://example.com/page.html'),
                ('http://example.com/page.html',        'http://example.com/not-page.html',         b'http://example.com/page.html'),
                ('https://example.com:443/page.html',   'https://example.com/not-page.html',        b'https://example.com/page.html'),
                ('http://example.com:80/page.html',     'http://example.com/not-page.html',         b'http://example.com/page.html'),
                ('http://example.com/page.html',        'http://example.com:80/not-page.html',      b'http://example.com/page.html'),
                ('http://example.com:8888/page.html',   'http://example.com:8888/not-page.html',    b'http://example.com:8888/page.html'),

                # Different host: send origin as referrer
                ('https://example2.com/page.html',  'https://scrapy.org/otherpage.html',        b'https://example2.com/'),
                ('https://example2.com/page.html',  'https://not.example2.com/otherpage.html',  b'https://example2.com/'),
                ('http://example2.com/page.html',   'http://not.example2.com/otherpage.html',   b'http://example2.com/'),
                # exact match required
                ('http://example2.com/page.html',   'http://www.example2.com/otherpage.html',   b'http://example2.com/'),

                # Different port: send origin as referrer
                ('https://example3.com:444/page.html',  'https://example3.com/not-page.html',   b'https://example3.com:444/'),
                ('http://example3.com:81/page.html',    'http://example3.com/not-page.html',    b'http://example3.com:81/'),

                # Different protocols: send origin as referrer
                ('https://example4.com/page.html',  'http://example4.com/not-page.html',    b'https://example4.com/'),
                ('https://example4.com/page.html',  'http://not.example4.com/',             b'https://example4.com/'),
                ('ftps://example4.com/urls.zip',    'https://example4.com/not-page.html',   b'ftps://example4.com/'),
                ('ftp://example4.com/urls.zip',     'http://example4.com/not-page.html',    b'ftp://example4.com/'),
                ('ftps://example4.com/urls.zip',    'https://example4.com/not-page.html',   b'ftps://example4.com/'),

                # test for user/password stripping
                ('https://user:password@example5.com/page.html', 'https://example5.com/not-page.html',  b'https://example5.com/page.html'),
                # TLS to non-TLS downgrade: send origin
                ('https://user:password@example5.com/page.html', 'http://example5.com/not-page.html',   b'https://example5.com/'),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_ORIGIN_WHEN_CROSS_ORIGIN})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)

    def test_policy_unsafe_url(self):

        for origin, target, referrer in [
                # TLS to TLS: send referrer
                ('https://example.com/sekrit.html',     'http://not.example.com/',      b'https://example.com/sekrit.html'),
                ('https://example1.com/page.html',      'https://not.example1.com/',    b'https://example1.com/page.html'),
                ('https://example1.com/page.html',      'https://scrapy.org/',          b'https://example1.com/page.html'),
                ('https://example1.com:443/page.html',  'https://scrapy.org/',          b'https://example1.com/page.html'),
                ('https://example1.com:444/page.html',  'https://scrapy.org/',          b'https://example1.com:444/page.html'),
                ('ftps://example1.com/urls.zip',        'https://scrapy.org/',          b'ftps://example1.com/urls.zip'),

                # TLS to non-TLS: send referrer (yes, it's unsafe)
                ('https://example2.com/page.html',  'http://not.example2.com/', b'https://example2.com/page.html'),
                ('https://example2.com/page.html',  'http://scrapy.org/',       b'https://example2.com/page.html'),
                ('ftps://example2.com/urls.zip',    'http://scrapy.org/',       b'ftps://example2.com/urls.zip'),

                # non-TLS to TLS or non-TLS: send referrer (yes, it's unsafe)
                ('http://example3.com/page.html',       'https://not.example3.com/',    b'http://example3.com/page.html'),
                ('http://example3.com/page.html',       'https://scrapy.org/',          b'http://example3.com/page.html'),
                ('http://example3.com:8080/page.html',  'https://scrapy.org/',          b'http://example3.com:8080/page.html'),
                ('http://example3.com:80/page.html',    'http://not.example3.com/',     b'http://example3.com/page.html'),
                ('http://example3.com/page.html',       'http://scrapy.org/',           b'http://example3.com/page.html'),
                ('http://example3.com:443/page.html',   'http://scrapy.org/',           b'http://example3.com:443/page.html'),
                ('ftp://example3.com/urls.zip',         'http://scrapy.org/',           b'ftp://example3.com/urls.zip'),
                ('ftp://example3.com/urls.zip',         'https://scrapy.org/',          b'ftp://example3.com/urls.zip'),

                # test for user/password stripping
                ('http://user:password@example4.com/page.html',     'https://not.example4.com/',    b'http://example4.com/page.html'),
                ('https://user:password@example4.com/page.html',    'http://scrapy.org/',           b'https://example4.com/page.html'),
            ]:
            response = Response(origin)
            request = Request(target, meta={'referrer_policy': POLICY_UNSAFE_URL})

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)
