import operator
from itertools import groupby
from collections import defaultdict
from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.http import Response
from scrapy.utils.cookies import CookieJar
from scrapy.core.exceptions import HttpException
from scrapy import log


class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""

    def __init__(self):
        self.jars = defaultdict(CookieJar)
        dispatcher.connect(self.domain_closed, signals.domain_closed)

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        jar = self.jars[spider.domain_name]
        cookies = _get_cookies(jar, request)
        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        # set Cookie header
        jar.add_cookie_header(request)

    def process_response(self, request, response, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        jar = self.jars[spider.domain_name]
        jar.extract_cookies(response, request)

        # TODO: set current cookies in jar to response.cookies?
        return response

    # cookies should be set on non-200 responses too
    def process_exception(self, request, exception, spider):
        if isinstance(exception, HttpException):
            self.process_response(request, exception.response, spider)

    def domain_closed(self, domain):
        self.jars.pop(domain, None)


def _get_cookies(jar, request):
    headers = {'Set-Cookie': ['%s=%s;' % (k, v) for k, v in request.cookies.iteritems()]}
    response = Response(request.url, headers=headers)
    cookies = jar.make_cookies(response, request)
    return cookies
    

