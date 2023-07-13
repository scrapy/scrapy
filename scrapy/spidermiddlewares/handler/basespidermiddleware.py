from abc import abstractmethod
from typing import Any, Callable

from twisted.python.failure import Failure

from scrapy import Request, Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Response
from scrapy.spidermiddlewares.handler.handler import AbstractHandler

from typing import (
    Any,
    Callable,
    Union,
)
ScrapeFunc = Callable[[Union[Response, Failure], Request, Spider], Any]


class BaseSpiderMiddleware(AbstractHandler):
    _sm_component_name: str = "BaseSpiderMiddleWare"
    scrape_func: ScrapeFunc

    def handle(self, packet: Any, spider, result):
        if self._next_handler:
            return self._next_handler.handle(packet, spider, result)
        return

    @abstractmethod
    def process_spider_input(self, packet, spider, result):
        pass

    @abstractmethod
    def process_spider_output(self, packet, spider, result):
        pass

    def check_integrity(self, result):
        try:
            if result is not None:
                msg = (
                    f"{self._sm_component_name.__qualname__} must return None "
                    f"or raise an exception, got {type(result)}"
                )
                raise _InvalidOutput(msg)
        except _InvalidOutput:
            raise
