import os
import six
import logging
from collections import defaultdict

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.python import to_native_str

logger = logging.getLogger(__name__)


class CookiesMiddleware(object):
    """This middleware enables working with sites that require cookies, such as
    those that use sessions. It keeps track of cookies sent by web servers, and
    send them back on subsequent requests (from that spider), just like web
    browsers do.

    The following settings can be used to configure the cookie middleware:

    * :setting:`COOKIES_ENABLED`
    * :setting:`COOKIES_DEBUG`

    .. reqmeta:: cookiejar

    .. rubric:: Multiple cookie sessions per spider

    .. versionadded:: 0.15

    There is support for keeping multiple cookie sessions per spider by using the
    :reqmeta:`cookiejar` Request meta key. By default it uses a single cookie jar
    (session), but you can pass an identifier to use different ones.

    For example::

        for i, url in enumerate(urls):
            yield scrapy.Request(url, meta={'cookiejar': i},
                callback=self.parse_page)

    Keep in mind that the :reqmeta:`cookiejar` meta key is not "sticky". You need to keep
    passing it along on subsequent requests. For example::

        def parse_page(self, response):
            # do some processing
            return scrapy.Request("http://www.example.com/otherpage",
                meta={'cookiejar': response.meta['cookiejar']},
                callback=self.parse_other_page)

    .. setting:: COOKIES_ENABLED

    .. rubric:: COOKIES_ENABLED

    Default: ``True``

    Whether to enable the cookies middleware. If disabled, no cookies will be sent
    to web servers.

    Notice that despite the value of :setting:`COOKIES_ENABLED` setting if
    ``Request.``:reqmeta:`meta['dont_merge_cookies'] <dont_merge_cookies>`
    evaluates to ``True`` the request cookies will **not** be sent to the
    web server and received cookies in :class:`Response <scrapy.Response>` will
    **not** be merged with the existing cookies.

    For more detailed information see the ``cookies`` parameter in
    :class:`Request <scrapy.Request>`.

    .. setting:: COOKIES_DEBUG

    .. rubric:: COOKIES_DEBUG

    Default: ``False``

    If enabled, Scrapy will log all cookies sent in requests (ie. ``Cookie``
    header) and all cookies received in responses (ie. ``Set-Cookie`` header).

    Here's an example of a log with :setting:`COOKIES_DEBUG` enabled::

        2011-04-06 14:35:10-0300 [scrapy.core.engine] INFO: Spider opened
        2011-04-06 14:35:10-0300 [scrapy.downloadermiddlewares.cookies] DEBUG: Sending cookies to: <GET http://www.diningcity.com/netherlands/index.html>
                Cookie: clientlanguage_nl=en_EN
        2011-04-06 14:35:14-0300 [scrapy.downloadermiddlewares.cookies] DEBUG: Received cookies from: <200 http://www.diningcity.com/netherlands/index.html>
                Set-Cookie: JSESSIONID=B~FA4DC0C496C8762AE4F1A620EAB34F38; Path=/
                Set-Cookie: ip_isocode=US
                Set-Cookie: clientlanguage_nl=en_EN; Expires=Thu, 07-Apr-2011 21:21:34 GMT; Path=/
        2011-04-06 14:49:50-0300 [scrapy.core.engine] DEBUG: Crawled (200) <GET http://www.diningcity.com/netherlands/index.html> (referer: None)
        [...]
    """

    def __init__(self, debug=False):
        self.jars = defaultdict(CookieJar)
        self.debug = debug

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings.getbool('COOKIES_DEBUG'))

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
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
        if request.meta.get('dont_merge_cookies', False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        jar.extract_cookies(response, request)
        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in request.headers.getlist('Cookie')]
            if cl:
                cookies = "\n".join("Cookie: {}\n".format(c) for c in cl)
                msg = "Sending cookies to: {}\n{}".format(request, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in response.headers.getlist('Set-Cookie')]
            if cl:
                cookies = "\n".join("Set-Cookie: {}\n".format(c) for c in cl)
                msg = "Received cookies from: {}\n{}".format(response, cookies)
                logger.debug(msg, extra={'spider': spider})

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
                    six.iteritems(request.cookies)]
        else:
            cookie_list = request.cookies

        cookies = [self._format_cookie(x) for x in cookie_list]
        headers = {'Set-Cookie': cookies}
        response = Response(request.url, headers=headers)

        return jar.make_cookies(response, request)
