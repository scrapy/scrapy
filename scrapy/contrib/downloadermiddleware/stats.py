from scrapy.core.exceptions import NotConfigured
from scrapy.stats import stats
from scrapy.conf import settings

class DownloaderStats(object):
    """DownloaderStats store stats of all requests, responses and
    exceptions that pass through it.

    They are stored in the following keys:

    SPIDER/downloader/request_method_count
    SPIDER/downloader/response_status_count
    SPIDER/downloader/exception_count

    To use this middleware you must enable the DOWNLOADER_STATS setting.
    """

    def __init__(self):
        if not settings.getbool('DOWNLOADER_STATS'):
            raise NotConfigured

    def process_request(self, request, spider):
        stats.incpath('_global/downloader/request_count')
        stats.incpath('%s/downloader/request_count' % spider.domain_name)
        stats.incpath('%s/downloader/request_method_count/%s' % (spider.domain_name, request.method))
        reqlen = len(request.httprepr())
        stats.incpath('%s/downloader/request_bytes' % spider.domain_name, reqlen)
        stats.incpath('_global/downloader/request_bytes', reqlen)

    def process_response(self, request, response, spider):
        self._inc_response_count(response, spider.domain_name)
        return response

    def process_exception(self, request, exception, spider):
        ex_class = "%s.%s" % (exception.__class__.__module__, exception.__class__.__name__)
        stats.incpath('_global/downloader/exception_count')
        stats.incpath('%s/downloader/exception_count' % spider.domain_name)
        stats.incpath('%s/downloader/exception_type_count/%s' % (spider.domain_name, ex_class))

    def _inc_response_count(self, response, domain):
        stats.incpath('_global/downloader/response_count')
        stats.incpath('%s/downloader/response_count' % domain)
        stats.incpath('%s/downloader/response_status_count/%s' % (domain, response.status))
        reslen = len(response.httprepr())
        stats.incpath('%s/downloader/response_bytes' % domain, reslen)
        stats.incpath('_global/downloader/response_bytes', reslen)
