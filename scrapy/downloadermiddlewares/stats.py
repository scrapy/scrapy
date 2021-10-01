from scrapy.exceptions import NotConfigured
from scrapy.utils.python import global_object_name, to_bytes
from scrapy.utils.request import request_httprepr

from twisted.web import http


def get_header_size(headers):
    size = 0
    for key, value in headers.items():
        if isinstance(value, (list, tuple)):
            for v in value:
                size += len(b": ") + len(key) + len(v)
    return size + len(b'\r\n') * (len(headers.keys()) - 1)


def get_status_size(response_status):
    return len(to_bytes(http.RESPONSES.get(response_status, b''))) + 15
    # resp.status + b"\r\n" + b"HTTP/1.1 <100-599> "


class DownloaderStats:

    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('DOWNLOADER_STATS'):
            raise NotConfigured
        return cls(crawler.stats)

    def process_request(self, request, spider):
        self.stats.inc_value('downloader/request_count', spider=spider)
        self.stats.inc_value(f'downloader/request_method_count/{request.method}', spider=spider)
        reqlen = len(request_httprepr(request))
        self.stats.inc_value('downloader/request_bytes', reqlen, spider=spider)

    def process_response(self, request, response, spider):
        self.stats.inc_value('downloader/response_count', spider=spider)
        self.stats.inc_value(f'downloader/response_status_count/{response.status}', spider=spider)
        reslen = len(response.body) + get_header_size(response.headers) + get_status_size(response.status) + 4
        # response.body + b"\r\n"+ response.header + b"\r\n" + response.status
        self.stats.inc_value('downloader/response_bytes', reslen, spider=spider)
        return response

    def process_exception(self, request, exception, spider):
        ex_class = global_object_name(exception.__class__)
        self.stats.inc_value('downloader/exception_count', spider=spider)
        self.stats.inc_value(f'downloader/exception_type_count/{ex_class}', spider=spider)
