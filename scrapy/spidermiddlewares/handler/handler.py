from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class Handler(ABC):
    @abstractmethod
    def set_next(self, handler: Handler) -> Handler:
        pass

    @abstractmethod
    def handle(self, packet: Any, spider, result) -> Any:
        pass


class AbstractHandler(Handler):
    _next_handler: Optional[Handler] = None

    def set_next(self, handler: Handler) -> Any:
        self._next_handler = handler
        return self._next_handler

    def get_next(self) -> Optional[Handler]:
        return self._next_handler

    def handle(self, packet: Any, spider, result) -> Any:
        if self._next_handler:
            return self._next_handler.handle(packet, spider, result)

        return result
