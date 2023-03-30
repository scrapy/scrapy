import re
import time
from http.cookiejar import CookieJar, DefaultCookiePolicy
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode

IPV4_RE = re.compile(r"\.\d+$", re.ASCII)


class CustomCookieJar:
    def __init__(self, policy=None, check_expired_frequency=10000):
        self.policy = policy or DefaultCookiePolicy()
        self.jar = CookieJar(self.policy)
        self.jar._cookies_lock = _DummyLock()
        self.check_expired_frequency = check_expired_frequency
        self.processed = 0

    def extract_cookies(self, response, request):
        wrapped_request = WrappedRequest(request)
        wrapped_response = WrappedResponse(response)
        return self.jar.extract_cookies(wrapped_response, wrapped_request)

    def add_cookie_header(self, request):
        wrapped_request = WrappedRequest(request)
        self.policy._now = self.jar._now = int(time.time())
        req_host = urlparse_cached(request).hostname

        if not req_host:
            return

        hosts = potential_domain_matches(req_host)
        if "." not in req_host:
            hosts += [req_host + ".local"]

        cookies = [self.jar._cookies_for_domain(host, wrapped_request) for host in hosts if host in self.jar._cookies]
        attrs = self.jar._cookie_attrs(cookies)
        if attrs and not wrapped_request.has_header("Cookie"):
            wrapped_request.add_unredirected_header("Cookie", "; ".join(attrs))

        self.processed += 1
        if self.processed % self.check_expired_frequency == 0:
            self.jar.clear_expired_cookies()

    def __getattr__(self, name):
        return getattr(self.jar, name)


class _DummyLock:
    def acquire(self):
        pass

    def release(self):
        pass


class WrappedRequest:
    def __init__(self, request):
        self.request = request

    def __getattr__(self, name):
        return getattr(self.request, name)

    def add_unredirected_header(self, name, value):
        self.request.headers.appendlist(name, value)


class WrappedResponse:
    def __init__(self, response):
        self.response = response

    def __getattr__(self, name):
        return getattr(self.response, name)

    def info(self):
        return self

    def get_all(self, name, default=None):
        return [
            to_unicode(v, errors="replace") for v in self.response.headers.getlist(name)
        ]


def potential_domain_matches(domain):
    matches = [domain]
    try:
        start = domain.index(".") + 1
        end = domain.rindex(".")
        while start < end:
            matches.append(domain[start:])
            start = domain.index(".", start) + 1
    except ValueError:
        pass

    return matches + ["." + d for d in matches]