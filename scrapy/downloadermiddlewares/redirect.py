import logging
from six.moves.urllib.parse import urljoin

from w3lib.url import safe_url_string

from scrapy.http import HtmlResponse
from scrapy.utils.response import get_meta_refresh
from scrapy.exceptions import IgnoreRequest, NotConfigured

logger = logging.getLogger(__name__)


class BaseRedirectMiddleware(object):

    enabled_setting = 'REDIRECT_ENABLED'

    def __init__(self, settings):
        if not settings.getbool(self.enabled_setting):
            raise NotConfigured

        self.max_redirect_times = settings.getint('REDIRECT_MAX_TIMES')
        self.priority_adjust = settings.getint('REDIRECT_PRIORITY_ADJUST')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def _redirect(self, redirected, request, spider, reason):
        ttl = request.meta.setdefault('redirect_ttl', self.max_redirect_times)
        redirects = request.meta.get('redirect_times', 0) + 1

        if ttl and redirects <= self.max_redirect_times:
            redirected.meta['redirect_times'] = redirects
            redirected.meta['redirect_ttl'] = ttl - 1
            redirected.meta['redirect_urls'] = request.meta.get('redirect_urls', []) + \
                [request.url]
            redirected.meta['redirect_reasons'] = request.meta.get('redirect_reasons', []) + \
                [reason]
            redirected.dont_filter = request.dont_filter
            redirected.priority = request.priority + self.priority_adjust
            logger.debug("Redirecting (%(reason)s) to %(redirected)s from %(request)s",
                         {'reason': reason, 'redirected': redirected, 'request': request},
                         extra={'spider': spider})
            return redirected
        else:
            logger.debug("Discarding %(request)s: max redirections reached",
                         {'request': request}, extra={'spider': spider})
            raise IgnoreRequest("max redirections reached")

    def _redirect_request_using_get(self, request, redirect_url):
        redirected = request.replace(url=redirect_url, method='GET', body='')
        redirected.headers.pop('Content-Type', None)
        redirected.headers.pop('Content-Length', None)
        return redirected


class RedirectMiddleware(BaseRedirectMiddleware):
    """
    Handle redirection of requests based on response status
    and meta-refresh html tag.
    """
    def process_response(self, request, response, spider):
        if (request.meta.get('dont_redirect', False) or
                response.status in getattr(spider, 'handle_httpstatus_list', []) or
                response.status in request.meta.get('handle_httpstatus_list', []) or
                request.meta.get('handle_httpstatus_all', False)):
            return response

        allowed_status = (301, 302, 303, 307, 308)
        if 'Location' not in response.headers or response.status not in allowed_status:
            return response

        location = safe_url_string(response.headers['location'])

        redirected_url = urljoin(request.url, location)

        if response.status in (301, 307, 308) or request.method == 'HEAD':
            redirected = request.replace(url=redirected_url)
            return self._redirect(redirected, request, spider, response.status)

        redirected = self._redirect_request_using_get(request, redirected_url)
        return self._redirect(redirected, request, spider, response.status)


class MetaRefreshMiddleware(BaseRedirectMiddleware):

    enabled_setting = 'METAREFRESH_ENABLED'

    def __init__(self, settings):
        super(MetaRefreshMiddleware, self).__init__(settings)
        self._ignore_tags = settings.getlist('METAREFRESH_IGNORE_TAGS')
        self._maxdelay = settings.getint('REDIRECT_MAX_METAREFRESH_DELAY',
                                         settings.getint('METAREFRESH_MAXDELAY'))

    def process_response(self, request, response, spider):
        if request.meta.get('dont_redirect', False) or request.method == 'HEAD' or \
                not isinstance(response, HtmlResponse):
            return response

        interval, url = get_meta_refresh(response,
                                         ignore_tags=self._ignore_tags)
        if url and interval < self._maxdelay:
            redirected = self._redirect_request_using_get(request, url)
            return self._redirect(redirected, request, spider, 'meta refresh')

        return response
