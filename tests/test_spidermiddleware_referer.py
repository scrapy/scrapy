from urllib.parse import urlparse
from unittest import TestCase
import warnings

from scrapy.http import Response, Request
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.spidermiddlewares.referer import (
    DefaultReferrerPolicy,
    NoReferrerPolicy,
    NoReferrerWhenDowngradePolicy,
    OriginPolicy,
    OriginWhenCrossOriginPolicy,
    POLICY_NO_REFERRER,
    POLICY_NO_REFERRER_WHEN_DOWNGRADE,
    POLICY_ORIGIN,
    POLICY_ORIGIN_WHEN_CROSS_ORIGIN,
    POLICY_SAME_ORIGIN,
    POLICY_SCRAPY_DEFAULT,
    POLICY_STRICT_ORIGIN,
    POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
    POLICY_UNSAFE_URL,
    RefererMiddleware,
    ReferrerPolicy,
    SameOriginPolicy,
    StrictOriginPolicy,
    StrictOriginWhenCrossOriginPolicy,
    UnsafeUrlPolicy,
)


class TestRefererMiddleware(TestCase):

    req_meta = {}
    resp_headers = {}
    settings = {}
    scenarii = [
        ('http://scrapytest.org', 'http://scrapytest.org/', b'http://scrapytest.org'),
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
            self.assertEqual(out[0].headers.get('Referer'), referrer)


class MixinDefault:
    """
    Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

    with some additional filtering of s3://
    """
    scenarii = [
        ('https://example.com/', 'https://scrapy.org/', b'https://example.com/'),
        ('http://example.com/', 'http://scrapy.org/', b'http://example.com/'),
        ('http://example.com/', 'https://scrapy.org/', b'http://example.com/'),
        ('https://example.com/', 'http://scrapy.org/', None),

        # no credentials leak
        ('http://user:password@example.com/', 'https://scrapy.org/', b'http://example.com/'),

        # no referrer leak for local schemes
        ('file:///home/path/to/somefile.html', 'https://scrapy.org/', None),
        ('file:///home/path/to/somefile.html', 'http://scrapy.org/', None),

        # no referrer leak for s3 origins
        ('s3://mybucket/path/to/data.csv', 'https://scrapy.org/', None),
        ('s3://mybucket/path/to/data.csv', 'http://scrapy.org/', None),
    ]


class MixinNoReferrer:
    scenarii = [
        ('https://example.com/page.html', 'https://example.com/', None),
        ('http://www.example.com/', 'https://scrapy.org/', None),
        ('http://www.example.com/', 'http://scrapy.org/', None),
        ('https://www.example.com/', 'http://scrapy.org/', None),
        ('file:///home/path/to/somefile.html', 'http://scrapy.org/', None),
    ]


class MixinNoReferrerWhenDowngrade:
    scenarii = [
        # TLS to TLS: send non-empty referrer
        ('https://example.com/page.html', 'https://not.example.com/', b'https://example.com/page.html'),
        ('https://example.com/page.html', 'https://scrapy.org/', b'https://example.com/page.html'),
        ('https://example.com:443/page.html', 'https://scrapy.org/', b'https://example.com/page.html'),
        ('https://example.com:444/page.html', 'https://scrapy.org/', b'https://example.com:444/page.html'),
        ('ftps://example.com/urls.zip', 'https://scrapy.org/', b'ftps://example.com/urls.zip'),

        # TLS to non-TLS: do not send referrer
        ('https://example.com/page.html', 'http://not.example.com/', None),
        ('https://example.com/page.html', 'http://scrapy.org/', None),
        ('ftps://example.com/urls.zip', 'http://scrapy.org/', None),

        # non-TLS to TLS or non-TLS: send referrer
        ('http://example.com/page.html', 'https://not.example.com/', b'http://example.com/page.html'),
        ('http://example.com/page.html', 'https://scrapy.org/', b'http://example.com/page.html'),
        ('http://example.com:8080/page.html', 'https://scrapy.org/', b'http://example.com:8080/page.html'),
        ('http://example.com:80/page.html', 'http://not.example.com/', b'http://example.com/page.html'),
        ('http://example.com/page.html', 'http://scrapy.org/', b'http://example.com/page.html'),
        ('http://example.com:443/page.html', 'http://scrapy.org/', b'http://example.com:443/page.html'),
        ('ftp://example.com/urls.zip', 'http://scrapy.org/', b'ftp://example.com/urls.zip'),
        ('ftp://example.com/urls.zip', 'https://scrapy.org/', b'ftp://example.com/urls.zip'),

        # test for user/password stripping
        ('http://user:password@example.com/page.html', 'https://not.example.com/', b'http://example.com/page.html'),
    ]


class MixinSameOrigin:
    scenarii = [
        # Same origin (protocol, host, port): send referrer
        ('https://example.com/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('https://example.com:443/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com:80/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com:80/not-page.html', b'http://example.com/page.html'),
        (
            'http://example.com:8888/page.html',
            'http://example.com:8888/not-page.html',
            b'http://example.com:8888/page.html',
        ),

        # Different host: do NOT send referrer
        ('https://example.com/page.html', 'https://not.example.com/otherpage.html', None),
        ('http://example.com/page.html', 'http://not.example.com/otherpage.html', None),
        ('http://example.com/page.html', 'http://www.example.com/otherpage.html', None),

        # Different port: do NOT send referrer
        ('https://example.com:444/page.html', 'https://example.com/not-page.html', None),
        ('http://example.com:81/page.html', 'http://example.com/not-page.html', None),
        ('http://example.com/page.html', 'http://example.com:81/not-page.html', None),

        # Different protocols: do NOT send refferer
        ('https://example.com/page.html', 'http://example.com/not-page.html', None),
        ('https://example.com/page.html', 'http://not.example.com/', None),
        ('ftps://example.com/urls.zip', 'https://example.com/not-page.html', None),
        ('ftp://example.com/urls.zip', 'http://example.com/not-page.html', None),
        ('ftps://example.com/urls.zip', 'https://example.com/not-page.html', None),

        # test for user/password stripping
        ('https://user:password@example.com/page.html', 'http://example.com/not-page.html', None),
        (
            'https://user:password@example.com/page.html',
            'https://example.com/not-page.html',
            b'https://example.com/page.html',
        ),
    ]


class MixinOrigin:
    scenarii = [
        # TLS or non-TLS to TLS or non-TLS: referrer origin is sent (yes, even for downgrades)
        ('https://example.com/page.html', 'https://example.com/not-page.html', b'https://example.com/'),
        ('https://example.com/page.html', 'https://scrapy.org', b'https://example.com/'),
        ('https://example.com/page.html', 'http://scrapy.org', b'https://example.com/'),
        ('http://example.com/page.html', 'http://scrapy.org', b'http://example.com/'),

        # test for user/password stripping
        ('https://user:password@example.com/page.html', 'http://scrapy.org', b'https://example.com/'),
    ]


class MixinStrictOrigin:
    scenarii = [
        # TLS or non-TLS to TLS or non-TLS: referrer origin is sent but not for downgrades
        ('https://example.com/page.html', 'https://example.com/not-page.html', b'https://example.com/'),
        ('https://example.com/page.html', 'https://scrapy.org', b'https://example.com/'),
        ('http://example.com/page.html', 'http://scrapy.org', b'http://example.com/'),

        # downgrade: send nothing
        ('https://example.com/page.html', 'http://scrapy.org', None),

        # upgrade: send origin
        ('http://example.com/page.html', 'https://scrapy.org', b'http://example.com/'),

        # test for user/password stripping
        ('https://user:password@example.com/page.html', 'https://scrapy.org', b'https://example.com/'),
        ('https://user:password@example.com/page.html', 'http://scrapy.org', None),
    ]


class MixinOriginWhenCrossOrigin:
    scenarii = [
        # Same origin (protocol, host, port): send referrer
        ('https://example.com/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('https://example.com:443/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com:80/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com:80/not-page.html', b'http://example.com/page.html'),
        (
            'http://example.com:8888/page.html',
            'http://example.com:8888/not-page.html',
            b'http://example.com:8888/page.html',
        ),

        # Different host: send origin as referrer
        ('https://example2.com/page.html', 'https://scrapy.org/otherpage.html', b'https://example2.com/'),
        ('https://example2.com/page.html', 'https://not.example2.com/otherpage.html', b'https://example2.com/'),
        ('http://example2.com/page.html', 'http://not.example2.com/otherpage.html', b'http://example2.com/'),
        # exact match required
        ('http://example2.com/page.html', 'http://www.example2.com/otherpage.html', b'http://example2.com/'),

        # Different port: send origin as referrer
        ('https://example3.com:444/page.html', 'https://example3.com/not-page.html', b'https://example3.com:444/'),
        ('http://example3.com:81/page.html', 'http://example3.com/not-page.html', b'http://example3.com:81/'),

        # Different protocols: send origin as referrer
        ('https://example4.com/page.html', 'http://example4.com/not-page.html', b'https://example4.com/'),
        ('https://example4.com/page.html', 'http://not.example4.com/', b'https://example4.com/'),
        ('ftps://example4.com/urls.zip', 'https://example4.com/not-page.html', b'ftps://example4.com/'),
        ('ftp://example4.com/urls.zip', 'http://example4.com/not-page.html', b'ftp://example4.com/'),
        ('ftps://example4.com/urls.zip', 'https://example4.com/not-page.html', b'ftps://example4.com/'),

        # test for user/password stripping
        (
            'https://user:password@example5.com/page.html',
            'https://example5.com/not-page.html',
            b'https://example5.com/page.html',
        ),
        # TLS to non-TLS downgrade: send origin
        (
            'https://user:password@example5.com/page.html',
            'http://example5.com/not-page.html',
            b'https://example5.com/',
        ),
    ]


class MixinStrictOriginWhenCrossOrigin:
    scenarii = [
        # Same origin (protocol, host, port): send referrer
        ('https://example.com/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('https://example.com:443/page.html', 'https://example.com/not-page.html', b'https://example.com/page.html'),
        ('http://example.com:80/page.html', 'http://example.com/not-page.html', b'http://example.com/page.html'),
        ('http://example.com/page.html', 'http://example.com:80/not-page.html', b'http://example.com/page.html'),
        (
            'http://example.com:8888/page.html',
            'http://example.com:8888/not-page.html',
            b'http://example.com:8888/page.html',
        ),

        # Different host: send origin as referrer
        ('https://example2.com/page.html', 'https://scrapy.org/otherpage.html', b'https://example2.com/'),
        ('https://example2.com/page.html', 'https://not.example2.com/otherpage.html', b'https://example2.com/'),
        ('http://example2.com/page.html', 'http://not.example2.com/otherpage.html', b'http://example2.com/'),
        # exact match required
        ('http://example2.com/page.html', 'http://www.example2.com/otherpage.html', b'http://example2.com/'),

        # Different port: send origin as referrer
        ('https://example3.com:444/page.html', 'https://example3.com/not-page.html', b'https://example3.com:444/'),
        ('http://example3.com:81/page.html', 'http://example3.com/not-page.html', b'http://example3.com:81/'),

        # downgrade
        ('https://example4.com/page.html', 'http://example4.com/not-page.html', None),
        ('https://example4.com/page.html', 'http://not.example4.com/', None),

        # non-TLS to non-TLS
        ('ftp://example4.com/urls.zip', 'http://example4.com/not-page.html', b'ftp://example4.com/'),

        # upgrade
        ('http://example4.com/page.html', 'https://example4.com/not-page.html', b'http://example4.com/'),
        ('http://example4.com/page.html', 'https://not.example4.com/', b'http://example4.com/'),

        # Different protocols: send origin as referrer
        ('ftps://example4.com/urls.zip', 'https://example4.com/not-page.html', b'ftps://example4.com/'),
        ('ftps://example4.com/urls.zip', 'https://example4.com/not-page.html', b'ftps://example4.com/'),

        # test for user/password stripping
        (
            'https://user:password@example5.com/page.html',
            'https://example5.com/not-page.html',
            b'https://example5.com/page.html',
        ),

        # TLS to non-TLS downgrade: send nothing
        ('https://user:password@example5.com/page.html', 'http://example5.com/not-page.html', None),
    ]


class MixinUnsafeUrl:
    scenarii = [
        # TLS to TLS: send referrer
        ('https://example.com/sekrit.html', 'http://not.example.com/', b'https://example.com/sekrit.html'),
        ('https://example1.com/page.html', 'https://not.example1.com/', b'https://example1.com/page.html'),
        ('https://example1.com/page.html', 'https://scrapy.org/', b'https://example1.com/page.html'),
        ('https://example1.com:443/page.html', 'https://scrapy.org/', b'https://example1.com/page.html'),
        ('https://example1.com:444/page.html', 'https://scrapy.org/', b'https://example1.com:444/page.html'),
        ('ftps://example1.com/urls.zip', 'https://scrapy.org/', b'ftps://example1.com/urls.zip'),

        # TLS to non-TLS: send referrer (yes, it's unsafe)
        ('https://example2.com/page.html', 'http://not.example2.com/', b'https://example2.com/page.html'),
        ('https://example2.com/page.html', 'http://scrapy.org/', b'https://example2.com/page.html'),
        ('ftps://example2.com/urls.zip', 'http://scrapy.org/', b'ftps://example2.com/urls.zip'),

        # non-TLS to TLS or non-TLS: send referrer (yes, it's unsafe)
        ('http://example3.com/page.html', 'https://not.example3.com/', b'http://example3.com/page.html'),
        ('http://example3.com/page.html', 'https://scrapy.org/', b'http://example3.com/page.html'),
        ('http://example3.com:8080/page.html', 'https://scrapy.org/', b'http://example3.com:8080/page.html'),
        ('http://example3.com:80/page.html', 'http://not.example3.com/', b'http://example3.com/page.html'),
        ('http://example3.com/page.html', 'http://scrapy.org/', b'http://example3.com/page.html'),
        ('http://example3.com:443/page.html', 'http://scrapy.org/', b'http://example3.com:443/page.html'),
        ('ftp://example3.com/urls.zip', 'http://scrapy.org/', b'ftp://example3.com/urls.zip'),
        ('ftp://example3.com/urls.zip', 'https://scrapy.org/', b'ftp://example3.com/urls.zip'),

        # test for user/password stripping
        (
            'http://user:password@example4.com/page.html',
            'https://not.example4.com/',
            b'http://example4.com/page.html',
        ),
        (
            'https://user:password@example4.com/page.html',
            'http://scrapy.org/',
            b'https://example4.com/page.html',
        ),
    ]


class TestRefererMiddlewareDefault(MixinDefault, TestRefererMiddleware):
    pass


# --- Tests using settings to set policy using class path
class TestSettingsNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerPolicy'}


class TestSettingsNoReferrerWhenDowngrade(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}


class TestSettingsSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}


class TestSettingsOrigin(MixinOrigin, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginPolicy'}


class TestSettingsStrictOrigin(MixinStrictOrigin, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.StrictOriginPolicy'}


class TestSettingsOriginWhenCrossOrigin(MixinOriginWhenCrossOrigin, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}


class TestSettingsStrictOriginWhenCrossOrigin(MixinStrictOriginWhenCrossOrigin, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.StrictOriginWhenCrossOriginPolicy'}


class TestSettingsUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.UnsafeUrlPolicy'}


class CustomPythonOrgPolicy(ReferrerPolicy):
    """
    A dummy policy that returns referrer as http(s)://python.org
    depending on the scheme of the target URL.
    """
    def referrer(self, response, request):
        scheme = urlparse(request).scheme
        if scheme == 'https':
            return b'https://python.org/'
        elif scheme == 'http':
            return b'http://python.org/'


class TestSettingsCustomPolicy(TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'tests.test_spidermiddleware_referer.CustomPythonOrgPolicy'}
    scenarii = [
        ('https://example.com/', 'https://scrapy.org/', b'https://python.org/'),
        ('http://example.com/', 'http://scrapy.org/', b'http://python.org/'),
        ('http://example.com/', 'https://scrapy.org/', b'https://python.org/'),
        ('https://example.com/', 'http://scrapy.org/', b'http://python.org/'),
        ('file:///home/path/to/somefile.html', 'https://scrapy.org/', b'https://python.org/'),
        ('file:///home/path/to/somefile.html', 'http://scrapy.org/', b'http://python.org/'),

    ]


# --- Tests using Request meta dict to set policy
class TestRequestMetaDefault(MixinDefault, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_SCRAPY_DEFAULT}


class TestRequestMetaNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_NO_REFERRER}


class TestRequestMetaNoReferrerWhenDowngrade(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_NO_REFERRER_WHEN_DOWNGRADE}


class TestRequestMetaSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_SAME_ORIGIN}


class TestRequestMetaOrigin(MixinOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_ORIGIN}


class TestRequestMetaSrictOrigin(MixinStrictOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_STRICT_ORIGIN}


class TestRequestMetaOriginWhenCrossOrigin(MixinOriginWhenCrossOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_ORIGIN_WHEN_CROSS_ORIGIN}


class TestRequestMetaStrictOriginWhenCrossOrigin(MixinStrictOriginWhenCrossOrigin, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN}


class TestRequestMetaUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRequestMetaPredecence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRequestMetaPredecence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}
    req_meta = {'referrer_policy': POLICY_NO_REFERRER}


class TestRequestMetaPredecence003(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}
    req_meta = {'referrer_policy': POLICY_UNSAFE_URL}


class TestRequestMetaSettingFallback(TestCase):

    params = [
        (
            # When an unknown policy is referenced in Request.meta
            # (here, a typo error),
            # the policy defined in settings takes precedence
            {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'},
            {},
            {'referrer_policy': 'ssscrapy-default'},
            OriginWhenCrossOriginPolicy,
            True
        ),
        (
            # same as above but with string value for settings policy
            {'REFERRER_POLICY': 'origin-when-cross-origin'},
            {},
            {'referrer_policy': 'ssscrapy-default'},
            OriginWhenCrossOriginPolicy,
            True
        ),
        (
            # request meta references a wrong policy but it is set,
            # so the Referrer-Policy header in response is not used,
            # and the settings' policy is applied
            {'REFERRER_POLICY': 'origin-when-cross-origin'},
            {'Referrer-Policy': 'unsafe-url'},
            {'referrer_policy': 'ssscrapy-default'},
            OriginWhenCrossOriginPolicy,
            True
        ),
        (
            # here, request meta does not set the policy
            # so response headers take precedence
            {'REFERRER_POLICY': 'origin-when-cross-origin'},
            {'Referrer-Policy': 'unsafe-url'},
            {},
            UnsafeUrlPolicy,
            False
        ),
        (
            # here, request meta does not set the policy,
            # but response headers also use an unknown policy,
            # so the settings' policy is used
            {'REFERRER_POLICY': 'origin-when-cross-origin'},
            {'Referrer-Policy': 'unknown'},
            {},
            OriginWhenCrossOriginPolicy,
            True
        )
    ]

    def test(self):

        origin = 'http://www.scrapy.org'
        target = 'http://www.example.com'

        for settings, response_headers, request_meta, policy_class, check_warning in self.params[3:]:
            mw = RefererMiddleware(Settings(settings))

            response = Response(origin, headers=response_headers)
            request = Request(target, meta=request_meta)

            with warnings.catch_warnings(record=True) as w:
                policy = mw.policy(response, request)
                self.assertIsInstance(policy, policy_class)

                if check_warning:
                    self.assertEqual(len(w), 1)
                    self.assertEqual(w[0].category, RuntimeWarning, w[0].message)


class TestSettingsPolicyByName(TestCase):

    def test_valid_name(self):
        for s, p in [
            (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
            (POLICY_NO_REFERRER, NoReferrerPolicy),
            (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
            (POLICY_SAME_ORIGIN, SameOriginPolicy),
            (POLICY_ORIGIN, OriginPolicy),
            (POLICY_STRICT_ORIGIN, StrictOriginPolicy),
            (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
            (POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN, StrictOriginWhenCrossOriginPolicy),
            (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
        ]:
            settings = Settings({'REFERRER_POLICY': s})
            mw = RefererMiddleware(settings)
            self.assertEqual(mw.default_policy, p)

    def test_valid_name_casevariants(self):
        for s, p in [
            (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
            (POLICY_NO_REFERRER, NoReferrerPolicy),
            (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
            (POLICY_SAME_ORIGIN, SameOriginPolicy),
            (POLICY_ORIGIN, OriginPolicy),
            (POLICY_STRICT_ORIGIN, StrictOriginPolicy),
            (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
            (POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN, StrictOriginWhenCrossOriginPolicy),
            (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
        ]:
            settings = Settings({'REFERRER_POLICY': s.upper()})
            mw = RefererMiddleware(settings)
            self.assertEqual(mw.default_policy, p)

    def test_invalid_name(self):
        settings = Settings({'REFERRER_POLICY': 'some-custom-unknown-policy'})
        with self.assertRaises(RuntimeError):
            RefererMiddleware(settings)


class TestPolicyHeaderPredecence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.SameOriginPolicy'}
    resp_headers = {'Referrer-Policy': POLICY_UNSAFE_URL.upper()}


class TestPolicyHeaderPredecence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy'}
    resp_headers = {'Referrer-Policy': POLICY_NO_REFERRER.swapcase()}


class TestPolicyHeaderPredecence003(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}
    resp_headers = {'Referrer-Policy': POLICY_NO_REFERRER_WHEN_DOWNGRADE.title()}


class TestPolicyHeaderPredecence004(MixinNoReferrerWhenDowngrade, TestRefererMiddleware):
    """
    The empty string means "no-referrer-when-downgrade"
    """
    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy'}
    resp_headers = {'Referrer-Policy': ''}


class TestReferrerOnRedirect(TestRefererMiddleware):

    settings = {'REFERRER_POLICY': 'scrapy.spidermiddlewares.referer.UnsafeUrlPolicy'}
    scenarii = [
        (
            'http://scrapytest.org/1',      # parent
            'http://scrapytest.org/2',      # target
            (
                # redirections: code, URL
                (301, 'http://scrapytest.org/3'),
                (301, 'http://scrapytest.org/4'),
            ),
            b'http://scrapytest.org/1',  # expected initial referer
            b'http://scrapytest.org/1',  # expected referer for the redirection request
        ),
        (
            'https://scrapytest.org/1',
            'https://scrapytest.org/2',
            (
                # redirecting to non-secure URL
                (301, 'http://scrapytest.org/3'),
            ),
            b'https://scrapytest.org/1',
            b'https://scrapytest.org/1',
        ),
        (
            'https://scrapytest.org/1',
            'https://scrapytest.com/2',
            (
                # redirecting to non-secure URL: different origin
                (301, 'http://scrapytest.com/3'),
            ),
            b'https://scrapytest.org/1',
            b'https://scrapytest.org/1',
        ),
    ]

    def setUp(self):
        self.spider = Spider('foo')
        settings = Settings(self.settings)
        self.referrermw = RefererMiddleware(settings)
        self.redirectmw = RedirectMiddleware(settings)

    def test(self):

        for parent, target, redirections, init_referrer, final_referrer in self.scenarii:
            response = self.get_response(parent)
            request = self.get_request(target)

            out = list(self.referrermw.process_spider_output(response, [request], self.spider))
            self.assertEqual(out[0].headers.get('Referer'), init_referrer)

            for status, url in redirections:
                response = Response(request.url, headers={'Location': url}, status=status)
                request = self.redirectmw.process_response(request, response, self.spider)
                self.referrermw.request_scheduled(request, self.spider)

            assert isinstance(request, Request)
            self.assertEqual(request.headers.get('Referer'), final_referrer)


class TestReferrerOnRedirectNoReferrer(TestReferrerOnRedirect):
    """
    No Referrer policy never sets the "Referer" header.
    HTTP redirections should not change that.
    """
    settings = {'REFERRER_POLICY': 'no-referrer'}
    scenarii = [
        (
            'http://scrapytest.org/1',      # parent
            'http://scrapytest.org/2',      # target
            (
                # redirections: code, URL
                (301, 'http://scrapytest.org/3'),
                (301, 'http://scrapytest.org/4'),
            ),
            None,  # expected initial "Referer"
            None,  # expected "Referer" for the redirection request
        ),
        (
            'https://scrapytest.org/1',
            'https://scrapytest.org/2',
            (
                (301, 'http://scrapytest.org/3'),
            ),
            None,
            None,
        ),
        (
            'https://scrapytest.org/1',
            'https://example.com/2',    # different origin
            (
                (301, 'http://scrapytest.com/3'),
            ),
            None,
            None,
        ),
    ]


class TestReferrerOnRedirectSameOrigin(TestReferrerOnRedirect):
    """
    Same Origin policy sends the full URL as "Referer" if the target origin
    is the same as the parent response (same protocol, same domain, same port).

    HTTP redirections to a different domain or a lower secure level
    should have the "Referer" removed.
    """
    settings = {'REFERRER_POLICY': 'same-origin'}
    scenarii = [
        (
            'http://scrapytest.org/101',      # origin
            'http://scrapytest.org/102',      # target
            (
                # redirections: code, URL
                (301, 'http://scrapytest.org/103'),
                (301, 'http://scrapytest.org/104'),
            ),
            b'http://scrapytest.org/101',  # expected initial "Referer"
            b'http://scrapytest.org/101',  # expected referer for the redirection request
        ),
        (
            'https://scrapytest.org/201',
            'https://scrapytest.org/202',
            (
                # redirecting from secure to non-secure URL == different origin
                (301, 'http://scrapytest.org/203'),
            ),
            b'https://scrapytest.org/201',
            None,
        ),
        (
            'https://scrapytest.org/301',
            'https://scrapytest.org/302',
            (
                # different domain == different origin
                (301, 'http://example.com/303'),
            ),
            b'https://scrapytest.org/301',
            None,
        ),
    ]


class TestReferrerOnRedirectStrictOrigin(TestReferrerOnRedirect):
    """
    Strict Origin policy will always send the "origin" as referrer
    (think of it as the parent URL without the path part),
    unless the security level is lower and no "Referer" is sent.

    Redirections from secure to non-secure URLs should have the
    "Referrer" header removed if necessary.
    """
    settings = {'REFERRER_POLICY': POLICY_STRICT_ORIGIN}
    scenarii = [
        (
            'http://scrapytest.org/101',
            'http://scrapytest.org/102',
            (
                (301, 'http://scrapytest.org/103'),
                (301, 'http://scrapytest.org/104'),
            ),
            b'http://scrapytest.org/',  # send origin
            b'http://scrapytest.org/',  # redirects to same origin: send origin
        ),
        (
            'https://scrapytest.org/201',
            'https://scrapytest.org/202',
            (
                # redirecting to non-secure URL: no referrer
                (301, 'http://scrapytest.org/203'),
            ),
            b'https://scrapytest.org/',
            None,
        ),
        (
            'https://scrapytest.org/301',
            'https://scrapytest.org/302',
            (
                # redirecting to non-secure URL (different domain): no referrer
                (301, 'http://example.com/303'),
            ),
            b'https://scrapytest.org/',
            None,
        ),
        (
            'http://scrapy.org/401',
            'http://example.com/402',
            (
                (301, 'http://scrapytest.org/403'),
            ),
            b'http://scrapy.org/',
            b'http://scrapy.org/',
        ),
        (
            'https://scrapy.org/501',
            'https://example.com/502',
            (
                # HTTPS all along, so origin referrer is kept as-is
                (301, 'https://google.com/503'),
                (301, 'https://facebook.com/504'),
            ),
            b'https://scrapy.org/',
            b'https://scrapy.org/',
        ),
        (
            'https://scrapytest.org/601',
            'http://scrapytest.org/602',                # TLS to non-TLS: no referrer
            (
                (301, 'https://scrapytest.org/603'),    # TLS URL again: (still) no referrer
            ),
            None,
            None,
        ),
    ]


class TestReferrerOnRedirectOriginWhenCrossOrigin(TestReferrerOnRedirect):
    """
    Origin When Cross-Origin policy sends the full URL as "Referer",
    unless the target's origin is different (different domain, different protocol)
    in which case only the origin is sent.

    Redirections to a different origin should strip the "Referer"
    to the parent origin.
    """
    settings = {'REFERRER_POLICY': POLICY_ORIGIN_WHEN_CROSS_ORIGIN}
    scenarii = [
        (
            'http://scrapytest.org/101',      # origin
            'http://scrapytest.org/102',      # target + redirection
            (
                # redirections: code, URL
                (301, 'http://scrapytest.org/103'),
                (301, 'http://scrapytest.org/104'),
            ),
            b'http://scrapytest.org/101',  # expected initial referer
            b'http://scrapytest.org/101',  # expected referer for the redirection request
        ),
        (
            'https://scrapytest.org/201',
            'https://scrapytest.org/202',
            (
                # redirecting to non-secure URL: send origin
                (301, 'http://scrapytest.org/203'),
            ),
            b'https://scrapytest.org/201',
            b'https://scrapytest.org/',
        ),
        (
            'https://scrapytest.org/301',
            'https://scrapytest.org/302',
            (
                # redirecting to non-secure URL (different domain): send origin
                (301, 'http://example.com/303'),
            ),
            b'https://scrapytest.org/301',
            b'https://scrapytest.org/',
        ),
        (
            'http://scrapy.org/401',
            'http://example.com/402',
            (
                (301, 'http://scrapytest.org/403'),
            ),
            b'http://scrapy.org/',
            b'http://scrapy.org/',
        ),
        (
            'https://scrapy.org/501',
            'https://example.com/502',
            (
                # all different domains: send origin
                (301, 'https://google.com/503'),
                (301, 'https://facebook.com/504'),
            ),
            b'https://scrapy.org/',
            b'https://scrapy.org/',
        ),
        (
            'https://scrapytest.org/301',
            'http://scrapytest.org/302',                # TLS to non-TLS: send origin
            (
                (301, 'https://scrapytest.org/303'),    # TLS URL again: send origin (also)
            ),
            b'https://scrapytest.org/',
            b'https://scrapytest.org/',
        ),
    ]


class TestReferrerOnRedirectStrictOriginWhenCrossOrigin(TestReferrerOnRedirect):
    """
    Strict Origin When Cross-Origin policy sends the full URL as "Referer",
    unless the target's origin is different (different domain, different protocol)
    in which case only the origin is sent...
    Unless there's also a downgrade in security and then the "Referer" header
    is not sent.

    Redirections to a different origin should strip the "Referer" to the parent origin,
    and from https:// to http:// will remove the "Referer" header.
    """
    settings = {'REFERRER_POLICY': POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN}
    scenarii = [
        (
            'http://scrapytest.org/101',      # origin
            'http://scrapytest.org/102',      # target + redirection
            (
                # redirections: code, URL
                (301, 'http://scrapytest.org/103'),
                (301, 'http://scrapytest.org/104'),
            ),
            b'http://scrapytest.org/101',  # expected initial referer
            b'http://scrapytest.org/101',  # expected referer for the redirection request
        ),
        (
            'https://scrapytest.org/201',
            'https://scrapytest.org/202',
            (
                # redirecting to non-secure URL: do not send the "Referer" header
                (301, 'http://scrapytest.org/203'),
            ),
            b'https://scrapytest.org/201',
            None,
        ),
        (
            'https://scrapytest.org/301',
            'https://scrapytest.org/302',
            (
                # redirecting to non-secure URL (different domain): send origin
                (301, 'http://example.com/303'),
            ),
            b'https://scrapytest.org/301',
            None,
        ),
        (
            'http://scrapy.org/401',
            'http://example.com/402',
            (
                (301, 'http://scrapytest.org/403'),
            ),
            b'http://scrapy.org/',
            b'http://scrapy.org/',
        ),
        (
            'https://scrapy.org/501',
            'https://example.com/502',
            (
                # all different domains: send origin
                (301, 'https://google.com/503'),
                (301, 'https://facebook.com/504'),
            ),
            b'https://scrapy.org/',
            b'https://scrapy.org/',
        ),
        (
            'https://scrapytest.org/601',
            'http://scrapytest.org/602',                # TLS to non-TLS: do not send "Referer"
            (
                (301, 'https://scrapytest.org/603'),    # TLS URL again: (still) send nothing
            ),
            None,
            None,
        ),
    ]
