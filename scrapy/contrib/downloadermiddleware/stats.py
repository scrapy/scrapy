from scrapy.core.exceptions import NotConfigured
from scrapy.utils.request import request_httprepr
from scrapy.utils.response import response_httprepr
from scrapy.stats import stats
from scrapy.conf import settings

class DownloaderStats(object):
    """DownloaderStats store stats of all requests, responses and
    exceptions that pass through it.

    To use this middleware you must enable the DOWNLOADER_STATS setting.
    """

    def __init__(self):
        if not settings.getbool('DOWNLOADER_STATS'):
            raise NotConfigured

    def process_request(self, request, spider):
        domain = spider.domain_name
        stats.inc_value('downloader/request_count')
        stats.inc_value('downloader/request_count', domain=domain)
        stats.inc_value('downloader/request_method_count/%s' % request.method, domain=domain)
        reqlen = len(request_httprepr(request))
        stats.inc_value('downloader/request_bytes', reqlen, domain=domain)
        stats.inc_value('downloader/request_bytes', reqlen)

    def process_response(self, request, response, spider):
        domain = spider.domain_name
        stats.inc_value('downloader/response_count')
        stats.inc_value('downloader/response_count', domain=domain)
        stats.inc_value('downloader/response_status_count/%s' % response.status, domain=domain)
        reslen = len(response_httprepr(response))
        stats.inc_value('downloader/response_bytes', reslen, domain=domain)
        stats.inc_value('downloader/response_bytes', reslen)
        return response

    def process_exception(self, request, exception, spider):
        ex_class = "%s.%s" % (exception.__class__.__module__, exception.__class__.__name__)
        stats.inc_value('downloader/exception_count')
        stats.inc_value('downloader/exception_count', domain=spider.domain_name)
        stats.inc_value('downloader/exception_type_count/%s' % ex_class, domain=spider.domain_name)
