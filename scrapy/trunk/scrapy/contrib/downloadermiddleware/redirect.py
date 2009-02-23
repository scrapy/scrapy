from scrapy import log
from scrapy.core.exceptions import HttpException
from scrapy.utils.url import urljoin_rfc as urljoin
from scrapy.utils.response import get_meta_refresh

class RedirectLoop(Exception):
    pass

# some sites use meta-refresh for redirecting to a session expired page, so we
# restrict automatic redirection to a maximum delay (in number of seconds)
META_REFRESH_MAXSEC = 100
MAX_REDIRECT_LOOP = 10

class RedirectMiddleware(object):
    def process_exception(self, request, exception, spider):
        if not isinstance(exception, HttpException):
            return

        domain = spider.domain_name
        status = exception.status
        response = exception.response

        if status in [302, 303]:
            redirected_url = urljoin(request.url, response.headers['location'][0])
            redirected = request.replace(url=redirected_url, method='GET', body=None)
            return self._redirect(redirected, request, spider, status)

        if status in [301, 307]:
            redirected_url = urljoin(request.url, response.headers['location'][0])
            redirected = request.replace(url=redirected_url)
            return self._redirect(redirected, request, spider, status)

    def process_response(self, request, response, spider):
        interval, url = get_meta_refresh(response)
        if url and int(interval) < META_REFRESH_MAXSEC:
            redirected = request.replace(url=urljoin(request.url, url))
            return self._redirect(redirected, request, spider, 'meta refresh')

        return response

    def _redirect(self, redirected, request, spider, reason):
        domain = spider.domain_name
        log.msg("Redirecting (%s) to %s from %s" % (reason, redirected, request), level=log.DEBUG, domain=domain)
        return redirected

