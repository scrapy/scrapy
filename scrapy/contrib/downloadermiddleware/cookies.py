from collections import defaultdict
from scrapy.xlib.pydispatch import dispatcher

from scrapy import signals
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.conf import settings
from scrapy import log


class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""
    debug = settings.getbool('COOKIES_DEBUG')

    def __init__(self):
        self.jars = defaultdict(CookieJar)
        dispatcher.connect(self.spider_closed, signals.spider_closed)

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        jar = self.jars[spider]
        cookies = self._get_request_cookies(jar, request)
        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        # set Cookie header
        request.headers.pop('Cookie', None)
        jar.add_cookie_header(request)
        self._debug_cookie(request)

    def process_response(self, request, response, spider):
        if request.meta.get('dont_merge_cookies', False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        jar = self.jars[spider]
        jar.extract_cookies(response, request)
        self._debug_set_cookie(response)

        return response

    def spider_closed(self, spider):
        self.jars.pop(spider, None)

    def _debug_cookie(self, request):
        """log Cookie header for request"""
        if self.debug:
            c = request.headers.get('Cookie')
            c = c and [p.split('=')[0] for p in c.split(';')]
            log.msg('Cookie: %s for %s' % (c, request.url), level=log.DEBUG)

    def _debug_set_cookie(self, response):
        """log Set-Cookies headers but exclude cookie values"""
        if self.debug:
            cl = response.headers.getlist('Set-Cookie')
            res = []
            for c in cl:
                kv, tail = c.split(';', 1)
                k = kv.split('=', 1)[0]
                res.append('%s %s' % (k, tail))
            log.msg('Set-Cookie: %s from %s' % (res, response.url))


    def _get_request_cookies(self, jar, request):
        headers = {'Set-Cookie': ['%s=%s;' % (k, v) for k, v in request.cookies.iteritems()]}
        response = Response(request.url, headers=headers)
        cookies = jar.make_cookies(response, request)
        return cookies


