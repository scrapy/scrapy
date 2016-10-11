"""
RefererMiddleware: populates Request referer field, based on the Response which
originated it.
"""
from six.moves.urllib.parse import ParseResult, urlunparse

from scrapy.http import Request
from scrapy.exceptions import NotConfigured
from scrapy.utils.python import to_native_str
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object


LOCAL_SCHEMES = ('about', 'blob', 'data', 'filesystem',)

POLICY_NO_REFERRER = "no-referrer"
POLICY_NO_REFERRER_WHEN_DOWNGRADE = "no-referrer-when-downgrade"
POLICY_SAME_ORIGIN = "same-origin"
POLICY_ORIGIN = "origin"
POLICY_ORIGIN_WHEN_CROSS_ORIGIN = "origin-when-cross-origin"
POLICY_UNSAFE_URL = "unsafe-url"
POLICY_SCRAPY_DEFAULT = "scrapy-default"


class ReferrerPolicy(object):

    NOREFERRER_SCHEMES = LOCAL_SCHEMES

    def referrer(self, response, request):
        raise NotImplementedError()

    def stripped_referrer(self, req_or_resp):
        stripped = self.strip_url(req_or_resp)
        if stripped is not None:
            return urlunparse(stripped)

    def origin_referrer(self, req_or_resp):
        stripped = self.strip_url(req_or_resp, origin_only=True)
        if stripped is not None:
            return urlunparse(stripped)

    def strip_url(self, req_or_resp, origin_only=False):
        """
        https://www.w3.org/TR/referrer-policy/#strip-url

        If url is null, return no referrer.
        If url's scheme is a local scheme, then return no referrer.
        Set url's username to the empty string.
        Set url's password to null.
        Set url's fragment to null.
        If the origin-only flag is true, then:
            Set url's path to null.
            Set url's query to null.
        Return url.
        """
        if req_or_resp.url is None or not req_or_resp.url:
            return None
        parsed = urlparse_cached(req_or_resp)

        if parsed.scheme in self.NOREFERRER_SCHEMES:
            return None

        netloc = parsed.netloc
        # strip username and password if present
        if parsed.username or parsed.password:
            netloc = netloc.replace('{p.username}:{p.password}@'.format(p=parsed), '')

        # strip standard protocol numbers
        # Note: strictly speaking, standard port numbers should only be
        # stripped when comparing origins
        if parsed.port:
            if (parsed.scheme, parsed.port) in (('http', 80), ('https', 443)):
                netloc = netloc.replace(':{p.port}'.format(p=parsed), '')

        return ParseResult(parsed.scheme,
                           netloc,
                           '/' if origin_only else parsed.path,
                           '' if origin_only else parsed.params,
                           '' if origin_only else parsed.query,
                           '')

    def origin(self, req_or_resp):
        """Return (scheme, host, path) tuple for a request or response URL."""
        return tuple(self.strip_url(req_or_resp, origin_only=True)[:3])


class NoReferrerPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer

    The simplest policy is "no-referrer", which specifies that no referrer information
    is to be sent along with requests made from a particular request client to any origin.
    The header will be omitted entirely.
    """
    name = POLICY_NO_REFERRER

    def referrer(self, response, request):
        return None


class NoReferrerWhenDowngradePolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

    The "no-referrer-when-downgrade" policy sends a full URL
    along with requests from a TLS-protected environment settings object
    to a a priori authenticated URL,
    and requests from request clients which are not TLS-protected to any origin.

    Requests from TLS-protected request clients to non-a priori authenticated URLs,
    on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.

    This is a user agent's default behavior, if no policy is otherwise specified.
    """
    name = POLICY_NO_REFERRER_WHEN_DOWNGRADE

    def referrer(self, response, request):
        # https://www.w3.org/TR/referrer-policy/#determine-requests-referrer:
        #
        # If environment is TLS-protected
        # and the origin of request's current URL is not an a priori authenticated URL,
        # then return no referrer.
        if urlparse_cached(response).scheme in ('https', 'ftps') and \
            urlparse_cached(request).scheme in ('http',):
                return None
        return self.stripped_referrer(response)


class SameOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-same-origin

    The "same-origin" policy specifies that a full URL, stripped for use as a referrer,
    is sent as referrer information when making same-origin requests from a particular request client.

    Cross-origin requests, on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.
    """
    name = POLICY_SAME_ORIGIN

    def referrer(self, response, request):
        if self.origin(response) == self.origin(request):
            return self.stripped_referrer(response)


class OriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-origin

    The "origin" policy specifies that only the ASCII serialization
    of the origin of the request client is sent as referrer information
    when making both same-origin requests and cross-origin requests
    from a particular request client.
    """
    name = POLICY_ORIGIN

    def referrer(self, response, request):
        return self.origin_referrer(response)


class OriginWhenCrossOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-origin-when-cross-origin

    The "origin-when-cross-origin" policy specifies that a full URL,
    stripped for use as a referrer, is sent as referrer information
    when making same-origin requests from a particular request client,
    and only the ASCII serialization of the origin of the request client
    is sent as referrer information when making cross-origin requests
    from a particular request client.
    """
    name = POLICY_ORIGIN_WHEN_CROSS_ORIGIN

    def referrer(self, response, request):
        origin = self.origin(response)
        if origin == self.origin(request):
            return self.stripped_referrer(response)
        else:
            return urlunparse(origin + ('', '', ''))


class UnsafeUrlPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-unsafe-url

    The "unsafe-url" policy specifies that a full URL, stripped for use as a referrer,
    is sent along with both cross-origin requests
    and same-origin requests made from a particular request client.

    Note: The policy's name doesn't lie; it is unsafe.
    This policy will leak origins and paths from TLS-protected resources
    to insecure origins.
    Carefully consider the impact of setting such a policy for potentially sensitive documents.
    """
    name = POLICY_UNSAFE_URL

    def referrer(self, response, request):
        return self.stripped_referrer(response)


class LegacyPolicy(ReferrerPolicy):
    def referrer(self, response, request):
        return response.url


class DefaultReferrerPolicy(NoReferrerWhenDowngradePolicy):

    NOREFERRER_SCHEMES = LOCAL_SCHEMES + ('file', 's3')
    name = POLICY_SCRAPY_DEFAULT


_policy_classes = {p.name: p for p in (
    NoReferrerPolicy,
    NoReferrerWhenDowngradePolicy,
    SameOriginPolicy,
    OriginPolicy,
    OriginWhenCrossOriginPolicy,
    UnsafeUrlPolicy,
    DefaultReferrerPolicy,
)}

class RefererMiddleware(object):

    def __init__(self, settings={}):
        policy = settings.get('REFERER_POLICY')
        if policy is not None:
            try:
                self.default_policy = load_object(policy)
            except ValueError:
                try:
                    self.default_policy = _policy_classes[policy]
                except:
                    raise NotConfigured("Unknown referrer policy name %r" % policy)
        else:
            self.default_policy = DefaultReferrerPolicy

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('REFERER_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings)

    def policy(self, response, request):
        # policy set in request's meta dict takes precedence over default policy
        policy_name = request.meta.get('referrer_policy')
        if policy_name is None:
            policy_name = to_native_str(
                response.headers.get('Referrer-Policy', '').decode('latin1'))

        cls = _policy_classes.get(policy_name.lower(), self.default_policy)
        return cls()

    def process_spider_output(self, response, result, spider):
        def _set_referer(r):
            if isinstance(r, Request):
                referrer = self.policy(response, r).referrer(response, r)
                if referrer is not None:
                    r.headers.setdefault('Referer', referrer)
            return r
        return (_set_referer(r) for r in result or ())

