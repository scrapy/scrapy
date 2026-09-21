from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple, cast

from scrapy.core.downloader import Downloader
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from scrapy.http import Request


class MockSlot(NamedTuple):
    active: list[Any]


class MockDownloader:
    def __init__(self) -> None:
        self.slots: dict[str, MockSlot] = {}

    def get_slot_key(self, request: Request) -> str:
        if Downloader.DOWNLOAD_SLOT in request.meta:
            return cast("str", request.meta[Downloader.DOWNLOAD_SLOT])

        return urlparse_cached(request).hostname or ""

    def increment(self, slot_key: str) -> None:
        slot = self.slots.setdefault(slot_key, MockSlot(active=[]))
        slot.active.append(1)

    def decrement(self, slot_key: str) -> None:
        slot = self.slots[slot_key]
        slot.active.pop()

    def close(self) -> None:
        pass
