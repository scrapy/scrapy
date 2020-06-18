import logging
from collections import defaultdict

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.python import to_unicode


logger = logging.getLogger(__name__)


class CookiesMiddleware:
    """This middleware enables working with sites that need cookies"""

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
        for cookie in self._get_request_cookies(jar, request):
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
            cl = [to_unicode(c, errors='replace')
                  for c in request.headers.getlist('Cookie')]
            if cl:
                cookies = "\n".join("Cookie: {}\n".format(c) for c in cl)
                msg = "Sending cookies to: {}\n{}".format(request, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = [to_unicode(c, errors='replace')
                  for c in response.headers.getlist('Set-Cookie')]
            if cl:
                cookies = "\n".join("Set-Cookie: {}\n".format(c) for c in cl)
                msg = "Received cookies from: {}\n{}".format(response, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _format_cookie(self, cookie, request):
        """
        Given a dict consisting of cookie components, return its string representation.
        Decode from bytes if necessary.
        """
        decoded = {}
        for key in ("name", "value", "path", "domain"):
            if not cookie.get(key):
                if key in ("name", "value"):
                    msg = "Invalid cookie found in request {}: {} ('{}' is missing)"
                    logger.warning(msg.format(request, cookie, key))
                    return
                continue
            if isinstance(cookie[key], str):
                decoded[key] = cookie[key]
            else:
                try:
                    decoded[key] = cookie[key].decode("utf8")
                except UnicodeDecodeError:
                    logger.warning("Non UTF-8 encoded cookie found in request %s: %s",
                                   request, cookie)
                    decoded[key] = cookie[key].decode("latin1", errors="replace")

        cookie_str = "{}={}".format(decoded.pop("name"), decoded.pop("value"))
        for key, value in decoded.items():  # path, domain
            cookie_str += "; {}={}".format(key.capitalize(), value)
        return cookie_str

    def _get_request_cookies(self, jar, request):
        """
        Extract cookies from a Request. Values from the `Request.cookies` attribute
        take precedence over values from the `Cookie` request header.
        """
        def get_cookies_from_header(jar, request):
            cookie_header = request.headers.get("Cookie")
            if not cookie_header:
                return []
            cookie_gen_bytes = (s.strip() for s in cookie_header.split(b";"))
            cookie_list_unicode = []
            for cookie_bytes in cookie_gen_bytes:
                try:
                    cookie_unicode = cookie_bytes.decode("utf8")
                except UnicodeDecodeError:
                    logger.warning("Non UTF-8 encoded cookie found in request %s: %s",
                                   request, cookie_bytes)
                    cookie_unicode = cookie_bytes.decode("latin1", errors="replace")
                cookie_list_unicode.append(cookie_unicode)
            response = Response(request.url, headers={"Set-Cookie": cookie_list_unicode})
            return jar.make_cookies(response, request)

        def get_cookies_from_attribute(jar, request):
            if not request.cookies:
                return []
            elif isinstance(request.cookies, dict):
                cookies = ({"name": k, "value": v} for k, v in request.cookies.items())
            else:
                cookies = request.cookies
            formatted = filter(None, (self._format_cookie(c, request) for c in cookies))
            response = Response(request.url, headers={"Set-Cookie": formatted})
            return jar.make_cookies(response, request)

        return get_cookies_from_header(jar, request) + get_cookies_from_attribute(jar, request)
