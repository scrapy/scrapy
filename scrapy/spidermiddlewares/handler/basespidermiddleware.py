from abc import abstractmethod
from typing import Any

from scrapy.spidermiddlewares.handler.handler import AbstractHandler


class BaseSpiderMiddleware(AbstractHandler):
    _sm_component_name: str = "BaseSpiderMiddleWare"

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
