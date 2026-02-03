"""Utils for built-in HTTP download handlers."""

from __future__ import annotations

from abc import ABC
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import CancelledError
from twisted.internet.error import ConnectionRefusedError as TxConnectionRefusedError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.python.failure import Failure
from twisted.web.client import ResponseFailed
from twisted.web.error import SchemeNotSupported

from scrapy import responsetypes
from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    StopDownload,
    UnsupportedURLSchemeError,
)
from scrapy.utils.log import logger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from ipaddress import IPv4Address, IPv6Address

    from twisted.internet.ssl import Certificate

    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Headers, Response


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


def check_stop_download(
    signal: object, crawler: Crawler, request: Request, **kwargs: Any
) -> StopDownload | None:
    """Send the given signal and check if any of its handlers raised
    :exc:`~scrapy.exceptions.StopDownload`.

    Return the raised exception or ``None``.
    """
    signal_result = crawler.signals.send_catch_log(
        signal=signal,
        request=request,
        spider=crawler.spider,
        **kwargs,
    )
    for handler, result in signal_result:
        if isinstance(result, Failure) and isinstance(result.value, StopDownload):
            logger.debug(
                f"Download stopped for {request} from signal handler {handler.__qualname__}"
            )
            return result.value

    return None


def make_response(
    url: str,
    status: int,
    headers: Headers,
    body: bytes = b"",
    flags: list[str] | None = None,
    certificate: Certificate | None = None,
    ip_address: IPv4Address | IPv6Address | None = None,
    protocol: str | None = None,
    stop_download: StopDownload | None = None,
) -> Response:
    respcls = responsetypes.responsetypes.from_args(headers=headers, url=url, body=body)
    response = respcls(
        url=url,
        status=status,
        headers=headers,
        body=body,
        flags=flags,
        certificate=certificate,
        ip_address=ip_address,
        protocol=protocol,
    )
    if stop_download:
        response.flags.append("download_stopped")
        if stop_download.fail:
            stop_download.response = response
            raise stop_download
    return response


def get_maxsize_msg(size: int, limit: int, request: Request, *, expected: bool) -> str:
    prefix = "Expected to receive" if expected else "Received"
    return (
        f"{prefix} {size} bytes which is larger than download "
        f"max size ({limit}) in request {request}."
    )


def get_warnsize_msg(size: int, limit: int, request: Request, *, expected: bool) -> str:
    prefix = "Expected to receive" if expected else "Received"
    return (
        f"{prefix} {size} bytes which is larger than download "
        f"warn size ({limit}) in request {request}."
    )


def get_dataloss_msg(url: str) -> str:
    return (
        f"Got data loss in {url}. If you want to process broken "
        f"responses set the setting DOWNLOAD_FAIL_ON_DATALOSS = False"
        f" -- This message won't be shown in further requests"
    )
