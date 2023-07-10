import handler.handler
from handler.handler import AbstractHandler
from typing import Any


class BaseSpiderMiddleware(AbstractHandler):
  _sm_component_name: str = None

  def handle(self, packet: Any, spider, result):
    pass

    def process_spider_input():
      pass

    def process_spider_output():
      pass
