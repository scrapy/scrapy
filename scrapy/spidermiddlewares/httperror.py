import logging
from typing import Any, Callable, Union

from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest, _InvalidOutput
from scrapy.http import Response
from scrapy.spidermiddlewares.handler.basespidermiddleware import BaseSpiderMiddleware

logger = logging.getLogger(__name__)
ScrapeFunc = Callable[[Union[Response, Failure], Request, Spider], Any]


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super().__init__(*args, **kwargs)


class HttpErrorMiddleware(BaseSpiderMiddleware):
    _sm_component_name = "HttpErrorMiddleware"
    scrape_function: ScrapeFunc

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        middleware = cls(settings)
        middleware.scrape_function = ScrapeFunc  # Asigna la función predeterminada
        return middleware

    def __init__(self, settings):
        self.handle_httpstatus_all = settings.getbool("HTTPERROR_ALLOW_ALL")
        self.handle_httpstatus_list = settings.getlist("HTTPERROR_ALLOWED_CODES")

    def handle(self, packet, spider, result):
        try:
            if isinstance(packet, Response):
                self.process_spider_input(packet, spider)
                self.check_integrity(result)
        except _InvalidOutput:
            raise
        except Exception:
            return self.scrape_func(Failure(), packet, spider)

        if self._next_handler:
            return self._next_handler.handle(packet, spider, result)
        return

    def process_spider_input(self, response, spider):
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

    def process_spider_output(self, response, result, spider):
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
