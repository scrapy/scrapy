import logging
from collections import defaultdict

from tldextract import TLDExtract

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_unicode


logger = logging.getLogger(__name__)


def _cookie_to_set_cookie_value(cookie, *, errback=None):
    """Given a cookie defined as a dictionary with name and value keys, and
    optional path and domain keys, return the equivalent string that can be
    associated to a ``Set-Cookie`` header."""
    decoded = {}
    for key in ("name", "value", "path", "domain"):
        if cookie.get(key) is None:
            if key in ("name", "value"):
                if errback:
                    errback(f'Key {key!r} missing in cookie {cookie!r}')
                return
            continue
        if isinstance(cookie[key], (bool, float, int, str)):
            decoded[key] = str(cookie[key])
        else:
            try:
                decoded[key] = cookie[key].decode("utf8")
            except UnicodeDecodeError:
                if errback:
                    errback(
                        f'Non-UTF-8 value found in key {key!r} of cookie '
                        f'{cookie!r}'
                    )
                decoded[key] = cookie[key].decode("latin1", errors="replace")

    cookie_str = f"{decoded.pop('name')}={decoded.pop('value')}"
    for key, value in decoded.items():  # path, domain
        cookie_str += f"; {key.capitalize()}={value}"
    return cookie_str


def cookies_to_set_cookie_list(cookies, *, errback=None):
    """Given a group of cookie defined either as a dictionary or as a list of
    dictionaries (i.e. in a format supported by the cookies parameter of
    Request), return the equivalen list of strings that can be associated to a
    ``Set-Cookie`` header."""
    if not cookies:
        return []
    if isinstance(cookies, dict):
        cookies = ({"name": k, "value": v} for k, v in cookies.items())
    return filter(
        None,
        (
            _cookie_to_set_cookie_value(cookie, errback=errback)
            for cookie in cookies
        )
    )


_split_domain = TLDExtract(include_psl_private_domains=True)


def _is_public_domain(domain):
    parts = _split_domain(domain)
    return not parts.domain


class CookiesMiddleware:
    """This middleware enables working with sites that need cookies"""

    def __init__(self, debug=False):
        self.jars = defaultdict(CookieJar)
        self.debug = debug

        # Set on the class to speed up tests, which create instances multiple
        # times.
        if not hasattr(CookiesMiddleware, "public_suffix_list"):
            CookiesMiddleware.public_suffix_list = PublicSuffixList()

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings.getbool('COOKIES_DEBUG'))

    def _process_cookies(self, cookies, *, jar, request):
        for cookie in cookies:
            cookie_domain = cookie.domain
            if cookie_domain.startswith('.'):
                cookie_domain = cookie_domain[1:]

            request_domain = urlparse_cached(request).hostname.lower()

            def update_cookie_domain(*, prefix=''):
                # https://bugs.python.org/issue46075
                # Workaround from https://github.com/psf/requests/issues/5388
                cookie.domain = (
                    f'{prefix}{request_domain}.local'
                    if '.' not in request_domain
                    else request_domain
                )

            if not cookie_domain:  # https://bugs.python.org/issue33017
                update_cookie_domain()
            elif not self.public_suffix_list.is_private(cookie_domain):
                if cookie_domain != request_domain:
                    continue
                update_cookie_domain(prefix='.')

            jar.set_cookie_if_ok(cookie, request)

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = self._get_request_cookies(jar, request)
        self._process_cookies(cookies, jar=jar, request=request)

        # set Cookie header
        request.headers.pop('Cookie', None)
        jar.add_cookie_header(request)
        self._debug_cookie(request, spider)

    def process_response(self, request, response, spider):
        if request.meta.get('dont_merge_cookies', False):
            return response

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = jar.make_cookies(response, request)
        self._process_cookies(cookies, jar=jar, request=request)

        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request, spider):
        if self.debug:
            cl = [to_unicode(c, errors='replace')
                  for c in request.headers.getlist('Cookie')]
            if cl:
                cookies = "\n".join(f"Cookie: {c}\n" for c in cl)
                msg = f"Sending cookies to: {request}\n{cookies}"
                logger.debug(msg, extra={'spider': spider})

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = [to_unicode(c, errors='replace')
                  for c in response.headers.getlist('Set-Cookie')]
            if cl:
                cookies = "\n".join(f"Set-Cookie: {c}\n" for c in cl)
                msg = f"Received cookies from: {response}\n{cookies}"
                logger.debug(msg, extra={'spider': spider})

    def _get_request_cookies(self, jar, request):
        """
        Extract cookies from the Request.cookies attribute
        """
        def errback(message):
            logger.warning(f'In request {request}: {message}')

        set_cookie_list = cookies_to_set_cookie_list(
            request.cookies,
            errback=errback,
        )
        if not set_cookie_list:
            return []
        headers = {"Set-Cookie": set_cookie_list}
        response = Response(request.url, headers=headers)
        return jar.make_cookies(response, request)
