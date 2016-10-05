"""
RefererMiddleware: populates Request referer field, based on the Response which
originated it.
"""
from six.moves.urllib.parse import urlsplit, urlunsplit

from scrapy.http import Request
from scrapy.exceptions import NotConfigured
from scrapy.utils.python import to_native_str


LOCAL_SCHEMES = ('about', 'blob', 'data', 'filesystem',)

class ReferrerPolicy(object):

    NOREFERRER_SCHEMES = LOCAL_SCHEMES

    def referrer(self, response, request):
        raise NotImplementedError()

    def strip_url(self, url, origin_only=False):
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
        if url is None or not url:
            return None
        parsed = urlsplit(url, allow_fragments=True)

        if parsed.scheme in self.NOREFERRER_SCHEMES:
            return None
        if parsed.username or parsed.password:
            netloc = parsed.netloc.replace('{p.username}:{p.password}@'.format(p=parsed), '')
        else:
            netloc = parsed.netloc
        return urlunsplit((
            parsed.scheme,
            netloc,
            '' if origin_only else parsed.path,
            '' if origin_only else parsed.query,
            ''))


class NoReferrerPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer

    The simplest policy is "no-referrer", which specifies that no referrer information
    is to be sent along with requests made from a particular request client to any origin.
    The header will be omitted entirely.
    """
    name = "no-referrer"

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
    name = "no-referrer-when-downgrade"

    def referrer(self, response, request):
        target_url = request.url

        referrer_source = response.url
        referrer_url = self.strip_url(referrer_source)

        # https://www.w3.org/TR/referrer-policy/#determine-requests-referrer:
        #
        # If environment is TLS-protected
        # and the origin of request's current URL is not an a priori authenticated URL,
        # then return no referrer.
        if urlsplit(referrer_source).scheme in ('https', 'ftps') and \
            urlsplit(target_url).scheme in ('http',):
                return None
        return referrer_url


class SameOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-same-origin

    The "same-origin" policy specifies that a full URL, stripped for use as a referrer,
    is sent as referrer information when making same-origin requests from a particular request client.

    Cross-origin requests, on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.
    """
    name = "same-origin"

    def referrer(self, response, request):
        target_url = request.url
        referrer_source = response.url
        if urlsplit(referrer_source).netloc == urlsplit(target_url).netloc:
            return self.strip_url(referrer_source)
        else:
            return None


class OriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-origin

    The "origin" policy specifies that only the ASCII serialization
    of the origin of the request client is sent as referrer information
    when making both same-origin requests and cross-origin requests
    from a particular request client.
    """
    name = "origin"

    def referrer(self, response, request):
        return self.strip_url(referrer_source, origin_only=True)


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
    name = "origin-when-cross-origin"

    def referrer(self, response, request):
        target_url = request.url
        referrer_source = response.url

        # same origin --> send full referrer
        # different origin --> send only "origin" as referrer
        if urlsplit(referrer_source).netloc != urlsplit(target_url).netloc:
            origin_only = True
        return self.strip_url(referrer_source, origin_only=origin_only)


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
    name = "unsafe-url"

    def referrer(self, response, request):
        referrer_source = response.url
        return self.strip_url(referrer_source)


class LegacyPolicy(ReferrerPolicy):
    def referrer(self, response, request):
        return response.url


class DefaultReferrerPolicy(NoReferrerWhenDowngradePolicy):

    NOREFERRER_SCHEMES = LOCAL_SCHEMES + ('file', 's3')


_policies = {p.name: p for p in (
    NoReferrerPolicy,
    NoReferrerWhenDowngradePolicy,
    SameOriginPolicy,
    OriginPolicy,
    OriginWhenCrossOriginPolicy,
    UnsafeUrlPolicy,
)}

class RefererMiddleware(object):

    def __init__(self, policy_class=DefaultReferrerPolicy):
        self.default_policy = policy_class

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('REFERER_ENABLED'):
            raise NotConfigured
        return cls()

    def policy(self, response, request):
        policy_name = request.meta.get('referrer_policy')
        if policy_name is None:
            policy_name = to_native_str(response.headers.get('Referrer-Policy', '').decode('latin1'))

        policy_class = _policies.get(policy_name.lower(), self.default_policy)
        return policy_class()

    def process_spider_output(self, response, result, spider):
        def _set_referer(r):
            if isinstance(r, Request):
                referrer = self.policy(response, r).referrer(response, r)
                if referrer is not None:
                    r.headers.setdefault('Referer', referrer)
            return r
        return (_set_referer(r) for r in result or ())

