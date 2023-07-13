from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any  # , Optional


class Handler(ABC):
    @abstractmethod
    def set_next(self, handler: Handler) -> Handler:
        pass

    @abstractmethod
    def handle(self, packet: Any, spider, result) -> Any:
        pass


class AbstractHandler(Handler):
    _next_handler: None

    def set_next(self, handler: Handler):
        self._next_handler = handler

    def get_next(self) -> Any:
        if self._next_handler:
            return Handler
        return None

    def handle(self, packet: Any, spider, result) -> Any:
        if self._next_handler:
            return self._next_handler.handle(packet, spider, result)

        return result
