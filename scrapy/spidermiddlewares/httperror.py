"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
import logging
from typing import Union

from scrapy.exceptions import IgnoreRequest
from scrapy.http.response import Response, ResponseList
from scrapy.spiders import Spider


logger = logging.getLogger(__name__)


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response: Union[Response, ResponseList], *args) -> None:
        self.response: Union[Response, ResponseList] = response
        super().__init__(*args)


class HttpErrorMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.handle_httpstatus_all = settings.getbool('HTTPERROR_ALLOW_ALL')
        self.handle_httpstatus_list = settings.getlist('HTTPERROR_ALLOWED_CODES')

    def process_spider_input(self, response: Union[Response, ResponseList], spider: Spider) -> None:
        def process_response(response: Response) -> None:
            if 200 <= response.status < 300:
                return None
            meta = response.meta
            if meta.get('handle_httpstatus_all', False):
                return None
            if 'handle_httpstatus_list' in meta:
                allowed_statuses = meta['handle_httpstatus_list']
            elif self.handle_httpstatus_all:
                return None
            else:
                allowed_statuses = getattr(spider, 'handle_httpstatus_list', self.handle_httpstatus_list)
            if response.status in allowed_statuses:
                return None
            raise HttpError(response, 'Ignoring non-200 response')

        if isinstance(response, Response):
            return process_response(response)
        elif isinstance(response, ResponseList):
            error = False
            responses = []
            for resp in response.responses:
                if isinstance(resp, Response):
                    try:
                        if process_response(resp) is None:
                            responses.append(resp)
                    except HttpError as ex:
                        error = True
                        responses.append(ex)
                else:
                    responses.append(resp)
            response.responses = responses
            if error:
                raise HttpError(response)
            return None

    def process_spider_exception(self, response, exception, spider):
        if isinstance(exception, HttpError):
            spider.crawler.stats.inc_value('httperror/response_ignored_count')
            spider.crawler.stats.inc_value(
                f'httperror/response_ignored_status_count/{response.status}'
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {'response': response}, extra={'spider': spider},
            )
            return []
