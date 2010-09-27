from cookielib import CookieJar as _CookieJar, DefaultCookiePolicy

from scrapy.utils.httpobj import urlparse_cached

class CookieJar(object):
    def __init__(self, policy=None):
        self.jar = _CookieJar(policy or DefaultCookiePolicy())
        self.jar._cookies_lock = _DummyLock()

    def extract_cookies(self, response, request):
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        return self.jar.extract_cookies(wrsp, wreq)

    def add_cookie_header(self, request):
        wreq = WrappedRequest(request)
        self.jar.add_cookie_header(wreq)

    @property
    def _cookies(self):
        return self.jar._cookies

    def clear_session_cookies(self, *args, **kwargs):
        return self.jar.clear_session_cookies(*args, **kwargs)

    def clear(self):
        return self.jar.clear()

    def __iter__(self):
        return iter(self.jar)

    def __len__(self):
        return len(self.jar)

    def set_policy(self, pol):
        return self.jar.set_policy(pol)

    def make_cookies(self, response, request):
        wreq = WrappedRequest(request)
        wrsp = WrappedResponse(response)
        return self.jar.make_cookies(wrsp, wreq)

    def set_cookie(self, cookie):
        self.jar.set_cookie(cookie)

    def set_cookie_if_ok(self, cookie, request):
        self.jar.set_cookie_if_ok(cookie, WrappedRequest(request))


class _DummyLock(object):
    def acquire(self):
        pass

    def release(self):
        pass


class WrappedRequest(object):
    """Wraps a scrapy Request class with methods defined by urllib2.Request class to interact with CookieJar class

    see http://docs.python.org/library/urllib2.html#urllib2.Request
    """

    def __init__(self, request):
        self.request = request

    def get_full_url(self):
        return self.request.url

    def get_host(self):
        return urlparse_cached(self.request).netloc

    def get_type(self):
        return urlparse_cached(self.request).scheme

    def is_unverifiable(self):
        """Unverifiable should indicate whether the request is unverifiable, as defined by RFC 2965.

        It defaults to False. An unverifiable request is one whose URL the user did not have the
        option to approve. For example, if the request is for an image in an
        HTML document, and the user had no option to approve the automatic
        fetching of the image, this should be true.
        """
        return self.request.meta.get('is_unverifiable', False)

    def get_origin_req_host(self):
        return urlparse_cached(self.request).hostname

    def has_header(self, name):
        return name in self.request.headers

    def get_header(self, name, default=None):
        return self.request.headers.get(name, default)

    def header_items(self):
        return self.request.headers.items()

    def add_unredirected_header(self, name, value):
        self.request.headers.appendlist(name, value)
        #print 'add_unredirected_header', self.request.headers


class WrappedResponse(object):

    def __init__(self, response):
        self.response = response

    def info(self):
        return self

    def getheaders(self, name):
        return self.response.headers.getlist(name)
