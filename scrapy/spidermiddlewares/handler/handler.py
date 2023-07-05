from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Handler(ABC):
  @abstractmethod
  def set_next(self, handler: Handler) -> Handler:
    pass

  @abstractmethod
  def handle(self, request: Any) -> any:
    pass


class AbstractHandler(Handler):
  _next_handler: Handler = None

  @abstractmethod
  def set_next(self, handler: Handler) -> Handler:
    self._next_handler = handler
    return handler

  @abstractmethod
  def handle(self, request: Any) -> str:
    if self._next_handler:
      return self._next_handler.handle(request)

    return None
