import os
from collections import defaultdict

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy import log


class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""

    def __init__(self, debug=False):
        self.jars = defaultdict(CookieJar)
        self.debug = debug

    @classmethod
    def from_settings(cls, settings):
        if not settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return cls(settings.getbool('COOKIES_DEBUG'))

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_request(self, request, spider):
        if 'dont_merge_cookies' in request.meta:
            return

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = self._get_request_cookies(jar, request)
        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        # set Cookie header
        request.headers.pop('Cookie', None)
        jar.add_cookie_header(request)
        self._debug_cookie(request, spider)

    def process_response(self, request, response, spider):
        if 'dont_merge_cookies' in request.meta:
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        jar.extract_cookies(response, request)
        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request, spider):
        if self.debug:
            cl = request.headers.getlist('Cookie')
            if cl:
                msg = "Sending cookies to: %s" % request + os.linesep
                msg += os.linesep.join("Cookie: %s" % c for c in cl)
                log.msg(msg, spider=spider, level=log.DEBUG)

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = response.headers.getlist('Set-Cookie')
            if cl:
                msg = "Received cookies from: %s" % response + os.linesep
                msg += os.linesep.join("Set-Cookie: %s" % c for c in cl)
                log.msg(msg, spider=spider, level=log.DEBUG)

    def _format_cookie(self, cookie):
        # build cookie string
        cookie_str = '%s=%s' % (cookie['name'], cookie['value'])

        if cookie.get('path', None):
            cookie_str += '; Path=%s' % cookie['path']
        if cookie.get('domain', None):
            cookie_str += '; Domain=%s' % cookie['domain']

        return cookie_str

    def _get_request_cookies(self, jar, request):
        if isinstance(request.cookies, dict):
            cookie_list = [{'name': k, 'value': v} for k, v in \
                    request.cookies.iteritems()]
        else:
            cookie_list = request.cookies

        cookies = [self._format_cookie(x) for x in cookie_list]
        headers = {'Set-Cookie': cookies}
        response = Response(request.url, headers=headers)

        return jar.make_cookies(response, request)
