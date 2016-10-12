from unittest import TestCase

from scrapy.exceptions import NotConfigured
from scrapy.http import Response, Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.spidermiddlewares.referer import RefererMiddleware, \
    POLICY_NO_REFERRER, POLICY_NO_REFERRER_WHEN_DOWNGRADE, \
    POLICY_SAME_ORIGIN, POLICY_ORIGIN, POLICY_ORIGIN_WHEN_CROSS_ORIGIN, \
    POLICY_SCRAPY_DEFAULT, POLICY_UNSAFE_URL, \
    DefaultReferrerPolicy, \
    NoReferrerPolicy, NoReferrerWhenDowngradePolicy, \
    OriginWhenCrossOriginPolicy, OriginPolicy, \
    SameOriginPolicy, UnsafeUrlPolicy, ReferrerPolicy


class TestRefererMiddleware(TestCase):

    req_meta = {}
    resp_headers = {}
    settings = {}
    scenarii = [
        ('http://scrapytest.org', 'http://scrapytest.org/',  b'http://scrapytest.org'),
    ]

    def setUp(self):
        self.spider = Spider('foo')
        settings = Settings(self.settings)
        self.mw = RefererMiddleware(settings)

    def get_request(self, target):
        return Request(target, meta=self.req_meta)

    def get_response(self, origin):
        return Response(origin, headers=self.resp_headers)

    def test(self):

        for origin, target, referrer in self.scenarii:
            response = self.get_response(origin)
            request = self.get_request(target)

            out = list(self.mw.process_spider_output(response, [request], self.spider))
            self.assertEquals(out[0].headers.get('Referer'), referrer)


class MixinDefault(object):
    """
    Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

    with some additional filtering of s3://
    """
    scenarii = [
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
    ]


class MixinNoReferrer(object):
    scenarii = [
        ('https://example.com/page.html',       'https://example.com/', None),
        ('http://www.example.com/',             'https://scrapy.org/',  None),
        ('http://www.example.com/',             'http://scrapy.org/',   None),
        ('https://www.example.com/',            'http://scrapy.org/',   None),
        ('file:///home/path/to/somefile.html',  'http://scrapy.org/',   None),
    ]


class MixinNoReferrerWhenDowngrade(object):
    scenarii = [
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
    ]


class MixinSameOrigin(object):
    scenarii = [
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
    ]


class MixinOrigin(object):
    scenarii = [
        # TLS or non-TLS to TLS or non-TLS: referrer origin is sent (yes, even for downgrades)
        ('https://example.com/page.html',   'https://example.com/not-page.html',    b'https://example.com/'),
        ('https://example.com/page.html',   'https://scrapy.org',                   b'https://example.com/'),
        ('https://example.com/page.html',   'http://scrapy.org',                    b'https://example.com/'),
        ('http://example.com/page.html',    'http://scrapy.org',                    b'http://example.com/'),

        # test for user/password stripping
        ('https://user:password@example.com/page.html', 'http://scrapy.org', b'https://example.com/'),
    ]


class MixinOriginWhenCrossOrigin(object):
    scenarii = [
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
    ]


class MixinUnsafeUrl(object):
    scenarii = [
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
    ]


class TestRefererMiddlewareDefault(MixinDefault, TestRefererMiddleware):
    pass


# --- Tests using settings to set policy using class path
class TestRefererMiddlewareSettingsNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerPolicy'}


class TestRefererMiddlewareSettingsNoReferrerWhenDowngrade(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}


class TestRefererMiddlewareSettingsSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}


class TestRefererMiddlewareSettingsOrigin(MixinOrigin, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.OriginPolicy'}


class TestRefererMiddlewareSettingsOriginWhenCrossOrigin(MixinOriginWhenCrossOrigin, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}


class TestRefererMiddlewareSettingsUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.UnsafeUrlPolicy'}


class CustomPythonOrgPolicy(ReferrerPolicy):
    """
    A dummy policy that returns referrer as http(s)://python.org
    depending on the scheme of the target URL.
    """
    def referrer(self, response, request):
        from scrapy.utils.httpobj import urlparse_cached

        scheme = urlparse_cached(request).scheme
        if scheme == 'https':
            return b'https://python.org/'
        elif scheme == 'http':
            return b'http://python.org/'


class TestRefererMiddlewareSettingsCustomPolicy(TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'tests.test_spidermiddleware_referer.CustomPythonOrgPolicy'}
    scenarii = [
        ('https://example.com/',    'https://scrapy.org/',  b'https://python.org/'),
        ('http://example.com/',     'http://scrapy.org/',   b'http://python.org/'),
        ('http://example.com/',     'https://scrapy.org/',  b'https://python.org/'),
        ('https://example.com/',    'http://scrapy.org/',   b'http://python.org/'),
        ('file:///home/path/to/somefile.html',  'https://scrapy.org/', b'https://python.org/'),
        ('file:///home/path/to/somefile.html',  'http://scrapy.org/',  b'http://python.org/'),

    ]

# --- Tests using Request meta dict to set policy
class TestRefererMiddlewareDefaultMeta(MixinDefault, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_SCRAPY_DEFAULT}


class TestRefererMiddlewareNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_NO_REFERRER}


class TestRefererMiddlewareNoReferrerWhenDowngrade(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_NO_REFERRER_WHEN_DOWNGRADE}


class TestRefererMiddlewareSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_SAME_ORIGIN}


class TestRefererMiddlewareOrigin(MixinOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_ORIGIN}


class TestRefererMiddlewareOriginWhenCrossOrigin(MixinOriginWhenCrossOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_ORIGIN_WHEN_CROSS_ORIGIN}


class TestRefererMiddlewareUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRefererMiddlewareMetaPredecence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRefererMiddlewareMetaPredecence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}
    req_meta = {'referrer_policy': POLICY_NO_REFERRER}


class TestRefererMiddlewareMetaPredecence003(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRefererMiddlewareSettingsPolicyByName(TestCase):

    def test_valid_name(self):
        for s, p in [
                (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
                (POLICY_NO_REFERRER, NoReferrerPolicy),
                (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
                (POLICY_SAME_ORIGIN, SameOriginPolicy),
                (POLICY_ORIGIN, OriginPolicy),
                (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
                (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
            ]:
            settings = Settings({'REFERER_POLICY': s})
            mw = RefererMiddleware(settings)
            self.assertEquals(mw.default_policy, p)

    def test_valid_name_casevariants(self):
        for s, p in [
                (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
                (POLICY_NO_REFERRER, NoReferrerPolicy),
                (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
                (POLICY_SAME_ORIGIN, SameOriginPolicy),
                (POLICY_ORIGIN, OriginPolicy),
                (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
                (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
            ]:
            settings = Settings({'REFERER_POLICY': s.upper()})
            mw = RefererMiddleware(settings)
            self.assertEquals(mw.default_policy, p)

    def test_invalid_name(self):
        settings = Settings({'REFERER_POLICY': 'some-custom-unknown-policy'})
        with self.assertRaises(NotConfigured):
            mw = RefererMiddleware(settings)


class TestRefererMiddlewarePolicyHeaderPredecence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}
    resp_headers = {'Referrer-Policy': POLICY_UNSAFE_URL.upper()}

class TestRefererMiddlewarePolicyHeaderPredecence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}
    resp_headers = {'Referrer-Policy': POLICY_NO_REFERRER.swapcase()}

class TestRefererMiddlewarePolicyHeaderPredecence003(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    settings = {'REFERER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}
    resp_headers = {'Referrer-Policy': POLICY_NO_REFERRER_WHEN_DOWNGRADE.title()}
