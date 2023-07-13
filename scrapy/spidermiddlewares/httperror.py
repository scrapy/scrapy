import logging

from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from scrapy.spidermiddlewares.handler.basespidermiddleware import BaseSpiderMiddleware

logger = logging.getLogger(__name__)


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super().__init__(*args, **kwargs)


class HttpErrorMiddleware(BaseSpiderMiddleware):
    _sm_component_name = "HttpErrorMiddleware"

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(settings)

    def __init__(self, settings):
        self.handle_httpstatus_all = settings.getbool("HTTPERROR_ALLOW_ALL")
        self.handle_httpstatus_list = settings.getlist("HTTPERROR_ALLOWED_CODES")

    def handle(self, packet, spider, result):
        if isinstance(packet, Response):
            self.process_spider_input(packet, spider, result)

        if self._next_handler:
            return self._next_handler.handle(packet, spider, result)
        return

    def process_spider_input(self, response, spider, result):
        if 200 <= response.status < 300:  # common case
            return
        meta = response.meta
        if meta.get("handle_httpstatus_all", False):
            return
        if "handle_httpstatus_list" in meta:
            allowed_statuses = meta["handle_httpstatus_list"]
        elif self.handle_httpstatus_all:
            return
        else:
            allowed_statuses = getattr(
                spider, "handle_httpstatus_list", self.handle_httpstatus_list
            )
        if response.status in allowed_statuses:
            return
        raise HttpError(response, "Ignoring non-200 response")

    def process_spider_output(self, packet, spider, result):
        return result

    @staticmethod
    def process_spider_exception(response, exception, spider):
        if isinstance(exception, HttpError):
            spider.crawler.stats.inc_value("httperror/response_ignored_count")
            spider.crawler.stats.inc_value(
                f"httperror/response_ignored_status_count/{response.status}"
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {"response": response},
                extra={"spider": spider},
            )
            return []
