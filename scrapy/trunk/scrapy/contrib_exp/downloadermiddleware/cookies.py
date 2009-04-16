from pydispatch import dispatcher

from collections import defaultdict
from cookielib import CookieJar

from scrapy.core import signals
from scrapy.utils.misc import dict_updatedefault
from scrapy import log

class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""

    def __init__(self):
        self.cookies = defaultdict(CookieJar)
        dispatcher.connect(self.domain_closed, signals.domain_closed)

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        jar = self.cookies[spider.domain_name]
        wreq = _WrappedRequest(request)

        # TODO: Merge cookies in request with jar here
        # for key, value in request.cookies.items():
        #     jar.set_cookie(..)

        # set Cookie header with cookies in jar
        jar.add_cookie_header(wreq)

        print request.url.netloc, '    Cookie: ', request.headers.get('Cookie'), request.cookies

    def process_response(self, request, response, spider):
        print request.url.netloc, 'Set-Cookie:', response.headers.get('Set-Cookie'), request.cookies

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        wreq = _WrappedRequest(request)
        wrsp = _WrappedResponse(response)
        jar = self.cookies[spider.domain_name]

        jar.extract_cookies(wrsp, wreq)

        # TODO: set current cookies in jar to response.cookies?
        return response

    def domain_closed(self, domain):
        if domain in self.cookies:
            del self.cookies[domain]


class _WrappedRequest(object):
    """Wraps a scrapy Request class with methods defined by urllib2.Request class to interact with CookieJar class

    see http://docs.python.org/library/urllib2.html#urllib2.Request
    """

    def __init__(self, request):
        self.request = request

    def get_full_url(self):
        return self.request.url

    def get_host(self):
        return self.request.url.netloc

    def get_type(self):
        return self.request.url.scheme

    def is_unverifiable(self):
        """Unverifiable should indicate whether the request is unverifiable, as defined by RFC 2965.

        It defaults to False. An unverifiable request is one whose URL the user did not have the
        option to approve. For example, if the request is for an image in an
        HTML document, and the user had no option to approve the automatic
        fetching of the image, this should be true.
        """
        return self.request.meta.get('is_unverifiable', False)

    def get_origin_req_host(self):
        return self.request.hostname

    def has_header(self, name):
        return name in self.request.headers

    def header_items(self):
        return self.request.headers.items()

    def add_unredirected_header(self, name, value):
        # XXX: review please, not sure how to handle this
        self.request.headers[name] = value


class _WrappedResponse(object):

    def __init__(self, response):
        self.response = response

    def info(self):
        return self

    def getheaders(self, name):
        return self.response.headers.getlist(name)
