import re

from scrapy import log
from scrapy.http import Request, Response
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

        status = exception.status
        response = exception.response

        if status in set([302, 303]):
            redirected_url = urljoin(request.url, response.headers['location'][0])
            redirected = request.replace(url=redirected_url, method='GET', body=None)
            log.msg("Redirecting (%d) to %s from %s" % (status, redirected, request), level=log.DEBUG, domain=spider.domain_name)
            return redirected

        if status in [301, 307]:
            redirected_url = urljoin(request.url, response.headers['location'][0])
            redirected = request.replace(url=redirected_url)
            log.msg("Redirecting (%d) to %s from %s" % (status, redirected, request), level=log.DEBUG, domain=spider.domain_name)
            return redirected

    def process_response(self, request, response, spider):
        interval, url = get_meta_refresh(response)
        if url and int(interval) < META_REFRESH_MAXSEC:
            redirected = request.replace(url=urljoin(request.url, url))
            log.msg("Redirecting (meta refresh) to %s from %s" % (redirected, request), level=log.DEBUG, domain=spider.domain_name)
            return redirected

        return response
