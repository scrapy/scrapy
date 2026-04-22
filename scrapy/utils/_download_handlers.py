"""Utils for built-in HTTP download handlers."""

from __future__ import annotations

from abc import ABC
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from twisted.internet.defer import CancelledError
from twisted.internet.error import ConnectBindError as TxConnectBindError
from twisted.internet.error import ConnectError as TxConnectError
from twisted.internet.error import ConnectionRefusedError as TxConnectionRefusedError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import NoRouteError as TxNoRouteError
from twisted.internet.error import TCPTimedOutError as TxTCPTimedOutError
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.internet.error import UnknownHostError as TxUnknownHostError
from twisted.python.failure import Failure
from twisted.web.client import ResponseFailed
from twisted.web.error import SchemeNotSupported

from scrapy import responsetypes
from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectBindError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadNoRouteError,
    DownloadTCPTimedOutError,
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
        self._tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        self._fail_on_dataloss_warned: bool = False


_TWISTED_CONNECT_ERROR_MAP: tuple[
    tuple[type[TxConnectError], type[Exception]],
    ...,
] = (
    (TxConnectionRefusedError, DownloadConnectionRefusedError),
    (TxConnectBindError, DownloadConnectBindError),
    (TxUnknownHostError, CannotResolveHostError),
    (TxNoRouteError, DownloadNoRouteError),
    (TxTCPTimedOutError, DownloadTCPTimedOutError),
    (TxTimeoutError, DownloadTimeoutError),
)


def _map_twisted_connect_exception(exc: TxConnectError) -> Exception:
    message = str(exc)
    for twisted_exc_cls, scrapy_exc_cls in _TWISTED_CONNECT_ERROR_MAP:
        if isinstance(exc, twisted_exc_cls):
            return scrapy_exc_cls(message)
    return DownloadFailedError(message)


def _map_response_failed_exception(exc: ResponseFailed) -> Exception | None:
    mapped_exception: Exception | None = None
    for reason in exc.reasons:
        if isinstance(reason.value, TxConnectError):
            current_exception: Exception = _map_twisted_connect_exception(reason.value)
        elif isinstance(reason.value, DNSLookupError):
            current_exception = CannotResolveHostError(str(reason.value))
        else:
            return None
        if mapped_exception is None:
            mapped_exception = current_exception
            continue
        if type(mapped_exception) is not type(current_exception):
            return None
    return mapped_exception


@contextmanager
def wrap_twisted_exceptions() -> Iterator[None]:
    """Context manager that wraps Twisted exceptions into Scrapy exceptions."""
    try:
        yield
    except SchemeNotSupported as e:
        raise UnsupportedURLSchemeError(str(e)) from e
    except CancelledError as e:
        raise DownloadCancelledError(str(e)) from e
    except DNSLookupError as e:
        raise CannotResolveHostError(str(e)) from e
    except TxConnectError as e:
        raise _map_twisted_connect_exception(e) from e
    except ResponseFailed as e:
        if mapped_exception := _map_response_failed_exception(e):
            raise mapped_exception from e
        raise DownloadFailedError(str(e)) from e


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


def normalize_bind_address(
    value: str | tuple[str, int] | None,
) -> tuple[str, int] | None:
    if isinstance(value, str):
        return (value, 0)
    return value
