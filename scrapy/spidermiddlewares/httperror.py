import logging
from typing import Any

from scrapy import Request
from scrapy.http import Response
from scrapy.spidermiddlewares.basespidermiddleware import BaseSpiderMiddleware

logger = logging.getLogger(__name__)


class HttpError(BaseSpiderMiddleware):
  """A non-200 response was filtered"""

  def __init__(self, response, *args, **kwargs):
    self.response = response
    super().__init__(*args, **kwargs)


class HttpErrorMiddleware(BaseSpiderMiddleware):
  _sm_component_name = "HttpErrorMiddleware"

  def handle(self, packet: Any, spider, result):
    if isinstance(packet, Request):
        self.process_spider_input(packet, spider)
    elif isinstance(packet, Response):
        result = self.process_spider_output(packet, result, spider)

    self.get_next().handle(packet, spider, result)

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

  def process_spider_exception(self, response, exception, spider):
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

  def process_spider_output(self, response, result, spider):
    return result
