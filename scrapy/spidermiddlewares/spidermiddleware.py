import handler.handler
from typing import Any

class SpiderMiddleware(handler.AbstractHandler):
  def handle(self, request: Any) -> str:
    if request == "Banana":
      """Do things"""
    else:
      return super().handle(request)