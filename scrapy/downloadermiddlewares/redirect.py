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
    """This middleware handles redirection of requests based on response status.

    .. reqmeta:: redirect_urls

    The urls which the request goes through (while being redirected) can be found
    in the ``redirect_urls`` :attr:`Request.meta <scrapy.http.Request.meta>` key.

    The :class:`RedirectMiddleware` can be configured through the following
    settings (see the settings documentation for more info):

    * :setting:`REDIRECT_ENABLED`
    * :setting:`REDIRECT_MAX_TIMES`

    .. reqmeta:: dont_redirect

    If :attr:`Request.meta <scrapy.http.Request.meta>` has ``dont_redirect``
    key set to True, the request will be ignored by this middleware.

    If you want to handle some redirect status codes in your spider, you can
    specify these in the ``handle_httpstatus_list`` spider attribute.

    For example, if you want the redirect middleware to ignore 301 and 302
    responses (and pass them through to your spider) you can do this::

        class MySpider(CrawlSpider):
            handle_httpstatus_list = [301, 302]

    The ``handle_httpstatus_list`` key of :attr:`Request.meta
    <scrapy.http.Request.meta>` can also be used to specify which response codes to
    allow on a per-request basis. You can also set the meta key
    ``handle_httpstatus_all`` to ``True`` if you want to allow any response code
    for a request.


    .. rubric:: RedirectMiddleware settings

    .. setting:: REDIRECT_ENABLED

    .. rubric:: REDIRECT_ENABLED

    .. versionadded:: 0.13

    Default: ``True``

    Whether the Redirect middleware will be enabled.

    .. setting:: REDIRECT_MAX_TIMES

    .. rubric:: REDIRECT_MAX_TIMES

    Default: ``20``

    The maximum number of redirections that will be followed for a single request.
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
    """This middleware handles redirection of requests based on meta-refresh html tag.

    The :class:`MetaRefreshMiddleware` can be configured through the following
    settings (see the settings documentation for more info):

    * :setting:`METAREFRESH_ENABLED`
    * :setting:`METAREFRESH_MAXDELAY`

    This middleware obey :setting:`REDIRECT_MAX_TIMES` setting, :reqmeta:`dont_redirect`
    and :reqmeta:`redirect_urls` request meta keys as described for :class:`RedirectMiddleware`


    .. rubric:: MetaRefreshMiddleware settings

    .. setting:: METAREFRESH_ENABLED

    .. rubric::METAREFRESH_ENABLED

    .. versionadded:: 0.17

    Default: ``True``

    Whether the Meta Refresh middleware will be enabled.

    .. setting:: METAREFRESH_MAXDELAY

    .. rubric::METAREFRESH_MAXDELAY

    Default: ``100``

    The maximum meta-refresh delay (in seconds) to follow the redirection.
    Some sites use meta-refresh for redirecting to a session expired page, so we
    restrict automatic redirection to the maximum delay.
    """

    enabled_setting = 'METAREFRESH_ENABLED'

    def __init__(self, settings):
        super(MetaRefreshMiddleware, self).__init__(settings)
        self._maxdelay = settings.getint('REDIRECT_MAX_METAREFRESH_DELAY',
                                         settings.getint('METAREFRESH_MAXDELAY'))

    def process_response(self, request, response, spider):
        if request.meta.get('dont_redirect', False) or request.method == 'HEAD' or \
                not isinstance(response, HtmlResponse):
            return response

        interval, url = get_meta_refresh(response)
        if url and interval < self._maxdelay:
            redirected = self._redirect_request_using_get(request, url)
            return self._redirect(redirected, request, spider, 'meta refresh')

        return response
