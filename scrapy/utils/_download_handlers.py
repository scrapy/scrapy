"""Utils for built-in HTTP download handlers."""

from __future__ import annotations

from abc import ABC
from contextlib import contextmanager
from typing import TYPE_CHECKING

from twisted.internet.defer import CancelledError
from twisted.internet.error import ConnectionRefusedError as TxConnectionRefusedError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.web.client import ResponseFailed
from twisted.web.error import SchemeNotSupported

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    UnsupportedURLSchemeError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from scrapy import Request
    from scrapy.crawler import Crawler


class BaseHttpDownloadHandler(BaseDownloadHandler, ABC):
    """Base class for built-in HTTP download handlers."""

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self._default_maxsize: int = crawler.settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize: int = crawler.settings.getint("DOWNLOAD_WARNSIZE")
        self._fail_on_dataloss: bool = crawler.settings.getbool(
            "DOWNLOAD_FAIL_ON_DATALOSS"
        )
        self._fail_on_dataloss_warned: bool = False


@contextmanager
def wrap_twisted_exceptions() -> Iterator[None]:
    """Context manager that wraps Twisted exceptions into Scrapy exceptions."""
    try:
        yield
    except SchemeNotSupported as e:
        raise UnsupportedURLSchemeError(str(e)) from e
    except CancelledError as e:
        raise DownloadCancelledError(str(e)) from e
    except TxConnectionRefusedError as e:
        raise DownloadConnectionRefusedError(str(e)) from e
    except DNSLookupError as e:
        raise CannotResolveHostError(str(e)) from e
    except ResponseFailed as e:
        raise DownloadFailedError(str(e)) from e
    except TxTimeoutError as e:
        raise DownloadTimeoutError(str(e)) from e


def get_maxsize_msg(size: int, limit: int, request: Request) -> str:
    return (
        f"Received ({size}) bytes larger than download "
        f"max size ({limit}) in request {request}."
    )


def get_warnsize_msg(size: int, limit: int, request: Request) -> str:
    return (
        f"Expected response size ({size}) larger than download "
        f"warn size ({limit}) in request {request}."
    )


def get_dataloss_msg(url: str) -> str:
    return (
        f"Got data loss in {url}. If you want to process broken "
        f"responses set the setting DOWNLOAD_FAIL_ON_DATALOSS = False"
        f" -- This message won't be shown in further requests"
    )
