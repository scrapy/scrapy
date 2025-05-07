"""
RefererMiddleware: populates Request referer field, based on the Response which
originated it.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from w3lib.url import safe_url_string

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_unicode
from scrapy.utils.url import strip_url

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


LOCAL_SCHEMES: tuple[str, ...] = (
    "about",
    "blob",
    "data",
    "filesystem",
)

POLICY_NO_REFERRER = "no-referrer"
POLICY_NO_REFERRER_WHEN_DOWNGRADE = "no-referrer-when-downgrade"
POLICY_SAME_ORIGIN = "same-origin"
POLICY_ORIGIN = "origin"
POLICY_STRICT_ORIGIN = "strict-origin"
POLICY_ORIGIN_WHEN_CROSS_ORIGIN = "origin-when-cross-origin"
POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN = "strict-origin-when-cross-origin"
POLICY_UNSAFE_URL = "unsafe-url"
POLICY_SCRAPY_DEFAULT = "scrapy-default"


class ReferrerPolicy:
    NOREFERRER_SCHEMES: tuple[str, ...] = LOCAL_SCHEMES
    name: str

    def referrer(self, response_url: str, request_url: str) -> str | None:
        raise NotImplementedError

    def stripped_referrer(self, url: str) -> str | None:
        if urlparse(url).scheme not in self.NOREFERRER_SCHEMES:
            return self.strip_url(url)
        return None

    def origin_referrer(self, url: str) -> str | None:
        if urlparse(url).scheme not in self.NOREFERRER_SCHEMES:
            return self.origin(url)
        return None

    def strip_url(self, url: str, origin_only: bool = False) -> str | None:
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
        if not url:
            return None
        return strip_url(
            url,
            strip_credentials=True,
            strip_fragment=True,
            strip_default_port=True,
            origin_only=origin_only,
        )

    def origin(self, url: str) -> str | None:
        """Return serialized origin (scheme, host, path) for a request or response URL."""
        return self.strip_url(url, origin_only=True)

    def potentially_trustworthy(self, url: str) -> bool:
        # Note: this does not follow https://w3c.github.io/webappsec-secure-contexts/#is-url-trustworthy
        parsed_url = urlparse(url)
        if parsed_url.scheme in ("data",):
            return False
        return self.tls_protected(url)

    def tls_protected(self, url: str) -> bool:
        return urlparse(url).scheme in ("https", "ftps")


class NoReferrerPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer

    The simplest policy is "no-referrer", which specifies that no referrer information
    is to be sent along with requests made from a particular request client to any origin.
    The header will be omitted entirely.
    """

    name: str = POLICY_NO_REFERRER

    def referrer(self, response_url: str, request_url: str) -> str | None:
        return None


class NoReferrerWhenDowngradePolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

    The "no-referrer-when-downgrade" policy sends a full URL along with requests
    from a TLS-protected environment settings object to a potentially trustworthy URL,
    and requests from clients which are not TLS-protected to any origin.

    Requests from TLS-protected clients to non-potentially trustworthy URLs,
    on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.

    This is a user agent's default behavior, if no policy is otherwise specified.
    """

    name: str = POLICY_NO_REFERRER_WHEN_DOWNGRADE

    def referrer(self, response_url: str, request_url: str) -> str | None:
        if not self.tls_protected(response_url) or self.tls_protected(request_url):
            return self.stripped_referrer(response_url)
        return None


class SameOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-same-origin

    The "same-origin" policy specifies that a full URL, stripped for use as a referrer,
    is sent as referrer information when making same-origin requests from a particular request client.

    Cross-origin requests, on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.
    """

    name: str = POLICY_SAME_ORIGIN

    def referrer(self, response_url: str, request_url: str) -> str | None:
        if self.origin(response_url) == self.origin(request_url):
            return self.stripped_referrer(response_url)
        return None


class OriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-origin

    The "origin" policy specifies that only the ASCII serialization
    of the origin of the request client is sent as referrer information
    when making both same-origin requests and cross-origin requests
    from a particular request client.
    """

    name: str = POLICY_ORIGIN

    def referrer(self, response_url: str, request_url: str) -> str | None:
        return self.origin_referrer(response_url)


class StrictOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin

    The "strict-origin" policy sends the ASCII serialization
    of the origin of the request client when making requests:
    - from a TLS-protected environment settings object to a potentially trustworthy URL, and
    - from non-TLS-protected environment settings objects to any origin.

    Requests from TLS-protected request clients to non- potentially trustworthy URLs,
    on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.
    """

    name: str = POLICY_STRICT_ORIGIN

    def referrer(self, response_url: str, request_url: str) -> str | None:
        if (
            self.tls_protected(response_url)
            and self.potentially_trustworthy(request_url)
        ) or not self.tls_protected(response_url):
            return self.origin_referrer(response_url)
        return None


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

    name: str = POLICY_ORIGIN_WHEN_CROSS_ORIGIN

    def referrer(self, response_url: str, request_url: str) -> str | None:
        origin = self.origin(response_url)
        if origin == self.origin(request_url):
            return self.stripped_referrer(response_url)
        return origin


class StrictOriginWhenCrossOriginPolicy(ReferrerPolicy):
    """
    https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin-when-cross-origin

    The "strict-origin-when-cross-origin" policy specifies that a full URL,
    stripped for use as a referrer, is sent as referrer information
    when making same-origin requests from a particular request client,
    and only the ASCII serialization of the origin of the request client
    when making cross-origin requests:

    - from a TLS-protected environment settings object to a potentially trustworthy URL, and
    - from non-TLS-protected environment settings objects to any origin.

    Requests from TLS-protected clients to non- potentially trustworthy URLs,
    on the other hand, will contain no referrer information.
    A Referer HTTP header will not be sent.
    """

    name: str = POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN

    def referrer(self, response_url: str, request_url: str) -> str | None:
        origin = self.origin(response_url)
        if origin == self.origin(request_url):
            return self.stripped_referrer(response_url)
        if (
            self.tls_protected(response_url)
            and self.potentially_trustworthy(request_url)
        ) or not self.tls_protected(response_url):
            return self.origin_referrer(response_url)
        return None


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

    name: str = POLICY_UNSAFE_URL

    def referrer(self, response_url: str, request_url: str) -> str | None:
        return self.stripped_referrer(response_url)


class DefaultReferrerPolicy(NoReferrerWhenDowngradePolicy):
    """
    A variant of "no-referrer-when-downgrade",
    with the addition that "Referer" is not sent if the parent request was
    using ``file://`` or ``s3://`` scheme.
    """

    NOREFERRER_SCHEMES: tuple[str, ...] = (*LOCAL_SCHEMES, "file", "s3")
    name: str = POLICY_SCRAPY_DEFAULT


_policy_classes: dict[str, type[ReferrerPolicy]] = {
    p.name: p
    for p in (
        NoReferrerPolicy,
        NoReferrerWhenDowngradePolicy,
        SameOriginPolicy,
        OriginPolicy,
        StrictOriginPolicy,
        OriginWhenCrossOriginPolicy,
        StrictOriginWhenCrossOriginPolicy,
        UnsafeUrlPolicy,
        DefaultReferrerPolicy,
    )
}

# Reference: https://www.w3.org/TR/referrer-policy/#referrer-policy-empty-string
_policy_classes[""] = NoReferrerWhenDowngradePolicy


def _load_policy_class(
    policy: str, warning_only: bool = False
) -> type[ReferrerPolicy] | None:
    """
    Expect a string for the path to the policy class,
    otherwise try to interpret the string as a standard value
    from https://www.w3.org/TR/referrer-policy/#referrer-policies
    """
    try:
        return cast(type[ReferrerPolicy], load_object(policy))
    except ValueError:
        tokens = [token.strip() for token in policy.lower().split(",")]
        # https://www.w3.org/TR/referrer-policy/#parse-referrer-policy-from-header
        for token in tokens[::-1]:
            if token in _policy_classes:
                return _policy_classes[token]

        msg = f"Could not load referrer policy {policy!r}"
        if not warning_only:
            raise RuntimeError(msg)
        warnings.warn(msg, RuntimeWarning)
        return None


class RefererMiddleware(BaseSpiderMiddleware):
    def __init__(self, settings: BaseSettings | None = None):  # pylint: disable=super-init-not-called
        self.default_policy: type[ReferrerPolicy] = DefaultReferrerPolicy
        if settings is not None:
            settings_policy = _load_policy_class(settings.get("REFERRER_POLICY"))
            assert settings_policy
            self.default_policy = settings_policy

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("REFERER_ENABLED"):
            raise NotConfigured
        mw = cls(crawler.settings)

        # Note: this hook is a bit of a hack to intercept redirections
        crawler.signals.connect(mw.request_scheduled, signal=signals.request_scheduled)

        return mw

    def policy(self, resp_or_url: Response | str, request: Request) -> ReferrerPolicy:
        """
        Determine Referrer-Policy to use from a parent Response (or URL),
        and a Request to be sent.

        - if a valid policy is set in Request meta, it is used.
        - if the policy is set in meta but is wrong (e.g. a typo error),
          the policy from settings is used
        - if the policy is not set in Request meta,
          but there is a Referrer-policy header in the parent response,
          it is used if valid
        - otherwise, the policy from settings is used.
        """
        policy_name = request.meta.get("referrer_policy")
        if policy_name is None and isinstance(resp_or_url, Response):
            policy_header = resp_or_url.headers.get("Referrer-Policy")
            if policy_header is not None:
                policy_name = to_unicode(policy_header.decode("latin1"))
        if policy_name is None:
            return self.default_policy()

        cls = _load_policy_class(policy_name, warning_only=True)
        return cls() if cls else self.default_policy()

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            # start requests
            return request
        referrer = self.policy(response, request).referrer(response.url, request.url)
        if referrer is not None:
            request.headers.setdefault("Referer", referrer)
        return request

    def request_scheduled(self, request: Request, spider: Spider) -> None:
        # check redirected request to patch "Referer" header if necessary
        redirected_urls = request.meta.get("redirect_urls", [])
        if redirected_urls:
            request_referrer = request.headers.get("Referer")
            # we don't patch the referrer value if there is none
            if request_referrer is not None:
                # the request's referrer header value acts as a surrogate
                # for the parent response URL
                #
                # Note: if the 3xx response contained a Referrer-Policy header,
                #       the information is not available using this hook
                parent_url = safe_url_string(request_referrer)
                policy_referrer = self.policy(parent_url, request).referrer(
                    parent_url, request.url
                )
                if policy_referrer != request_referrer.decode("latin1"):
                    if policy_referrer is None:
                        request.headers.pop("Referer")
                    else:
                        request.headers["Referer"] = policy_referrer
