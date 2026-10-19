from __future__ import annotations

import logging
import time
from abc import abstractmethod
from io import BytesIO
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    ClassVar,
    Generic,
    NoReturn,
    NotRequired,
    TypedDict,
    TypeVar,
)

from scrapy import Request, signals
from scrapy.exceptions import (
    DownloadCancelledError,
    NotConfigured,
    ResponseDataLossError,
)
from scrapy.utils._download_handlers import (
    check_stop_download,
    get_dataloss_msg,
    get_maxsize_msg,
    get_warnsize,
    get_warnsize_msg,
    make_response,
)
from scrapy.utils.asyncio import is_asyncio_available

from ._base_http import BaseHttpDownloadHandler

if TYPE_CHECKING:
    import os
    from collections.abc import AsyncIterable
    from contextlib import AbstractAsyncContextManager
    from ipaddress import IPv4Address, IPv6Address

    from _typeshed import SizedBuffer

    from scrapy.crawler import Crawler
    from scrapy.http import Headers, Response


logger = logging.getLogger(__name__)

_ResponseT = TypeVar("_ResponseT")


class _BaseResponseArgs(TypedDict):
    status: int
    url: str
    headers: Headers
    certificate: NotRequired[Any]
    ip_address: NotRequired[IPv4Address | IPv6Address | None]
    protocol: str | None
    body_file: NotRequired[str | os.PathLike[str] | None]


class BaseStreamingDownloadHandler(BaseHttpDownloadHandler, Generic[_ResponseT]):
    """A base class for HTTP download handlers that follow the streaming logic flow."""

    _DEFAULT_CONNECT_TIMEOUT: ClassVar[float] = 10
    experimental: ClassVar[bool] = False
    requires_asyncio: ClassVar[bool] = True
    # require subclasses to disable proxies explicitly with an explanation
    supports_proxies: ClassVar[bool] = True
    supports_per_request_bindaddress: ClassVar[bool] = False

    def __init__(self, crawler: Crawler):
        if self.requires_asyncio and not is_asyncio_available():  # pragma: no cover
            raise NotConfigured(
                f"{type(self).__name__} requires the asyncio support. Make"
                f" sure that you have either enabled the asyncio Twisted"
                f" reactor in the TWISTED_REACTOR setting or disabled the"
                f" TWISTED_REACTOR_ENABLED setting. See the asyncio documentation"
                f" of Scrapy for more information."
            )
        self._check_deps_installed()
        super().__init__(crawler)
        if self.experimental:
            logger.warning(
                f"{type(self).__name__} is experimental and is not recommended for production use."
            )
        # these are useful for many handlers but used in different ways by them
        self._pool_size_total: int = crawler.settings.getint("CONCURRENT_REQUESTS")
        self._pool_size_per_host: int = crawler.settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )

    @abstractmethod
    def _make_request(
        self, request: Request, timeout: float
    ) -> AbstractAsyncContextManager[_ResponseT]:
        """Return an async context manager yielding the library-specific response.

        Exceptions raised by the library should be reraised as Scrapy-specific ones.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _extract_headers(response: _ResponseT) -> Headers:
        """Convert library-specific response headers to a
        :class:`~scrapy.http.headers.Headers` object."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _build_base_response_args(
        response: _ResponseT, request: Request, headers: Headers
    ) -> _BaseResponseArgs:
        """Build kwargs for :func:`scrapy.utils._download_handlers.make_response`."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _iter_body_chunks(response: _ResponseT) -> AsyncIterable[SizedBuffer]:
        """Return an async iterable yielding body chunks from the response."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        """Return True if ``exc`` represents dataloss."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _is_timeout_exception(exc: Exception) -> bool:
        """Return True if ``exc`` represents the download timeout being hit
        while reading the response body."""
        raise NotImplementedError

    @staticmethod
    def _check_deps_installed() -> None:
        """Raise NotConfigured if the required deps are not installed."""

    def _log_tls_info(self, response: _ResponseT, request: Request) -> None:
        """Log TLS connection details, if possible."""

    def _open_body_buffer(self, response: _ResponseT, request: Request) -> BinaryIO:
        """Return a file object to write the response body into."""
        if body_file := request.meta.get("body_file"):
            return Path(body_file).open("wb")
        return BytesIO()

    def _get_body(
        self, buffer: BinaryIO, response: _ResponseT, request: Request
    ) -> bytes:
        """Return the response body given the *buffer* it was written into."""
        if request.meta.get("body_file"):
            return b""
        assert isinstance(buffer, BytesIO)
        return buffer.getvalue()

    async def download_request(self, request: Request) -> Response:
        if not self.supports_proxies and request.meta.get("proxy"):
            raise NotImplementedError(f"{type(self).__name__} doesn't support proxies.")
        if not self.supports_per_request_bindaddress and request.meta.get(
            "bindaddress"
        ):
            logger.error(
                f"The 'bindaddress' request meta key is not supported by"
                f" {type(self).__name__} and will be ignored."
            )
        timeout: float = request.meta.get(
            "download_timeout", self._DEFAULT_CONNECT_TIMEOUT
        )
        start_time = time.monotonic()
        async with self._make_request(request, timeout) as response:
            request.meta["download_latency"] = time.monotonic() - start_time
            return await self._read_response(response, request)

    async def _read_response(self, response: _ResponseT, request: Request) -> Response:
        maxsize: int = request.meta.get("download_maxsize", self._default_maxsize)
        warnsize = get_warnsize(request.meta, self._default_warnsize)

        headers = self._extract_headers(response)
        content_length = headers.get("Content-Length")
        expected_size = int(content_length) if content_length is not None else None
        if maxsize and expected_size and expected_size > maxsize:
            self._cancel_maxsize(expected_size, maxsize, request, expected=True)

        reached_warnsize = False
        if warnsize and expected_size and expected_size > warnsize:
            reached_warnsize = True
            logger.warning(
                get_warnsize_msg(expected_size, warnsize, request, expected=True)
            )

        make_response_base_args = self._build_base_response_args(
            response, request, headers
        )
        make_response_base_args["body_file"] = request.meta.get("body_file")

        if self._tls_verbose_logging:
            self._log_tls_info(response, request)

        with self._open_body_buffer(response, request) as response_body:
            if stop_download := check_stop_download(
                signals.headers_received,
                self.crawler,
                request,
                headers=headers,
                body_length=expected_size,
            ):
                return make_response(
                    **make_response_base_args,
                    stop_download=stop_download,
                )

            bytes_received = 0
            try:
                async for chunk in self._iter_body_chunks(response):
                    response_body.write(chunk)
                    bytes_received += len(chunk)

                    if stop_download := check_stop_download(
                        signals.bytes_received, self.crawler, request, data=chunk
                    ):
                        return make_response(
                            **make_response_base_args,
                            body=self._get_body(response_body, response, request),
                            stop_download=stop_download,
                        )

                    if maxsize and bytes_received > maxsize:
                        response_body.truncate(0)
                        self._cancel_maxsize(
                            bytes_received, maxsize, request, expected=False
                        )

                    if warnsize and bytes_received > warnsize and not reached_warnsize:
                        reached_warnsize = True
                        logger.warning(
                            get_warnsize_msg(
                                bytes_received, warnsize, request, expected=False
                            )
                        )
            except Exception as e:
                return self._handle_body_exception(
                    e,
                    request,
                    make_response_base_args,
                    self._get_body(response_body, response, request),
                )

            return make_response(
                **make_response_base_args,
                body=self._get_body(response_body, response, request),
            )

    def _handle_body_exception(
        self,
        exc: Exception,
        request: Request,
        make_response_base_args: _BaseResponseArgs,
        body: bytes,
    ) -> Response:
        """Turn an exception raised while reading the response body into a
        partial response, if the request allows for it, or reraise it."""
        is_dataloss = self._is_dataloss_exception(exc)
        if not is_dataloss and not self._is_timeout_exception(exc):
            raise exc
        fail_on_dataloss: bool = request.meta.get(
            "download_fail_on_dataloss", self._fail_on_dataloss
        )
        if not fail_on_dataloss:
            return make_response(
                **make_response_base_args, body=body, flags=["dataloss"]
            )
        if not is_dataloss:
            # let the timeout be reported as usual
            raise exc
        if not self._fail_on_dataloss_warned:
            logger.warning(get_dataloss_msg(request.url))
            self._fail_on_dataloss_warned = True
        raise ResponseDataLossError(str(exc)) from exc

    @staticmethod
    def _cancel_maxsize(
        size: int, limit: int, request: Request, *, expected: bool
    ) -> NoReturn:
        warning_msg = get_maxsize_msg(size, limit, request, expected=expected)
        logger.warning(warning_msg)
        raise DownloadCancelledError(warning_msg)
