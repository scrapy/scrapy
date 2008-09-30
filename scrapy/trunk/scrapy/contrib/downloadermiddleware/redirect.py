import re

from scrapy import log
from scrapy.http import Request, Response
from scrapy.core.exceptions import HttpException
from scrapy.utils.url import urljoin_rfc as urljoin

class RedirectLoop(Exception):
    pass

META_REFRESH_RE = re.compile(r'<meta[^>]*http-equiv[^>]*refresh[^>].*?(\d+);url=([^"\']+)', re.IGNORECASE)
# some sites use meta-refresh for redirecting to a session expired page, so we
# restrict automatic redirection to a maximum delay (in number of seconds)
META_REFRESH_MAXSEC = 100
MAX_REDIRECT_LOOP = 10

class RedirectMiddleware(object):
    def process_exception(self, request, exception, spider):
        if isinstance(exception, HttpException):
            status = exception.status
            response = exception.response
            
            if status in ['302', '303']:
                redirected_url = urljoin(request.url, response.headers['location'][0])
                if not getattr(spider, "no_redirect", False):
                    redirected = request.copy()
                    redirected.url = redirected_url
                    redirected.method = 'GET'
                    redirected.body = None
                    # This is needed to avoid redirection loops with requests that contain dont_filter = True
                    # Example (9 May 2008): http://www.55max.com/product/001_photography.asp?3233,0,0,0,Michael+Banks
                    if isinstance(redirected.dont_filter, int):
                        if not hasattr(redirected, "original_dont_filter"):
                            redirected.original_dont_filter = redirected.dont_filter
                        if redirected.dont_filter <= -MAX_REDIRECT_LOOP:
                            raise RedirectLoop("Exited redirect loop with %s consecutive visits to the same url." % (redirected.original_dont_filter + MAX_REDIRECT_LOOP) )
                        redirected.dont_filter -= 1
                    else:
                        redirected.dont_filter = False
                    log.msg("Redirecting (%s) to %s from %s" % (status, redirected, request), level=log.DEBUG, domain=spider.domain_name)
                    return redirected
                log.msg("Ignored redirecting (%s) to %s from %s (disabled by spider)" % (status, redirected_url, request), level=log.DEBUG, domain=spider.domain_name)
                return response

            if status in ['301', '307']:
                redirected_url = urljoin(request.url, response.headers['location'][0])
                if not getattr(spider, "no_redirect", False):
                    redirected = request.copy()
                    redirected.url = redirected_url
                    # This is needed to avoid redirection loops with requests that contain dont_filter = True
                    # Example (9 May 2008): http://www.55max.com/product/001_photography.asp?3233,0,0,0,Michael+Banks
                    redirected.dont_filter = False
                    log.msg("Redirecting (%s) to %s from %s" % (status, redirected, request), level=log.DEBUG, domain=spider.domain_name)
                    return redirected
                log.msg("Ignored redirecting (%s) to %s from %s (disabled by spider)" % (status, redirected_url, request), level=log.DEBUG, domain=spider.domain_name)
                return response

    def process_response(self, request, response, spider):
        if isinstance(response, Response):
            m = META_REFRESH_RE.search(response.body.to_string()[0:4096])
            if m and int(m.group(1)) < META_REFRESH_MAXSEC:
                redirected = request.copy()
                redirected.url = urljoin(request.url, m.group(2))
                log.msg("Redirecting (meta refresh) to %s from %s" % (redirected, request), level=log.DEBUG, domain=spider.domain_name)
                return redirected
        return response
