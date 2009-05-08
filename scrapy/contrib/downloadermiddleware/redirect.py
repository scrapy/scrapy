from scrapy import log
from scrapy.core.exceptions import HttpException
from scrapy.utils.url import urljoin_rfc as urljoin
from scrapy.utils.response import get_meta_refresh
from scrapy.conf import settings

# some sites use meta-refresh for redirecting to a session expired page, so we
# restrict automatic redirection to a maximum delay (in number of seconds)
META_REFRESH_MAXSEC = 100
MAX_REDIRECT_LOOP = 10

class RedirectMiddleware(object):
    def __init__(self):
        self.max_redirect_times = settings.getint('REDIRECTMIDDLEWARE_MAX_TIMES')

    def process_exception(self, request, exception, spider):
        if not isinstance(exception, HttpException):
            return

        domain = spider.domain_name
        status = exception.status
        response = exception.response

        if status in [302, 303] and 'Location' in response.headers:
            redirected_url = urljoin(request.url, response.headers['location'])
            redirected = request.replace(url=redirected_url, method='GET', body='')
            redirected.headers.pop('Content-Type', None)
            redirected.headers.pop('Content-Length', None)
            return self._redirect(redirected, request, spider, status)

        if status in [301, 307] and 'Location' in response.headers:
            redirected_url = urljoin(request.url, response.headers['location'])
            redirected = request.replace(url=redirected_url)
            return self._redirect(redirected, request, spider, status)

    def process_response(self, request, response, spider):
        interval, url = get_meta_refresh(response)
        if url and int(interval) < META_REFRESH_MAXSEC:
            redirected = request.replace(url=urljoin(request.url, url))
            return self._redirect(redirected, request, spider, 'meta refresh')

        return response

    def _redirect(self, redirected, request, spider, reason):
        ttl = request.meta.setdefault('redirect_ttl', self.max_redirect_times)
        redirects = request.meta.get('redirect_times', 0) + 1

        if ttl and redirects <= self.max_redirect_times:
            redirected.meta['redirect_times'] = redirects
            redirected.meta['redirect_ttl'] = ttl - 1
            redirected.dont_filter = request.dont_filter
            log.msg("Redirecting (%s) to %s from %s" % (reason, redirected, request),
                    domain=spider.domain_name, level=log.DEBUG)
            return redirected
        else:
            log.msg("Discarding %s: max redirections reached" % request,
                    domain=spider.domain_name, level=log.DEBUG)


