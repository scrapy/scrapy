"""
Scrapy core exceptions

These exceptions are documented in docs/topics/exceptions.rst. Please don't add
new exceptions here without documenting them there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scrapy.http import Response

# Internal


class NotConfigured(Exception):
    """Raised by a :ref:`component <topics-components>` from its ``__init__()``
    or :meth:`from_crawler` method to indicate that it will remain disabled.

    Only the following components can be disabled this way:

    -   :ref:`Downloader middlewares <topics-downloader-middleware>`
    -   :ref:`Extensions <topics-extensions>`
    -   :ref:`Item pipelines <topics-item-pipeline>`
    -   :ref:`Spider middlewares <topics-spider-middleware>`"""


class _InvalidOutput(TypeError):
    """
    Indicates an invalid value has been returned by a middleware's processing method.
    Internal and undocumented, it should not be raised or caught by user code.
    """


# HTTP and crawling


class IgnoreRequest(Exception):
    """Raised to indicate that a request should be ignored.

    A :ref:`downloader middleware <topics-downloader-middleware>` can raise it
    from its
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_request`
    or
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response`
    method to drop a request, and a :signal:`request_scheduled` signal handler
    can raise it to drop a request before it reaches the
    :ref:`scheduler <topics-scheduler>`."""


class DontCloseSpider(Exception):
    """Raised in a :signal:`spider_idle` signal handler to prevent the spider
    from being closed."""


class CloseSpider(Exception):
    """Raised from a :ref:`spider callback <topics-spiders>` to request the
    spider to be closed/stopped.

    *reason* is a string with the reason for closing.

    For example:

    .. code-block:: python

        def parse_page(self, response):
            if "Bandwidth exceeded" in response.text:
                raise CloseSpider("bandwidth_exceeded")
    """

    def __init__(self, reason: str = "cancelled"):
        super().__init__()
        self.reason = reason


class StopDownload(Exception):
    """Raised from a :class:`~scrapy.signals.bytes_received` or
    :class:`~scrapy.signals.headers_received` signal handler to :ref:`stop the
    download <topics-stop-response-download>` of the response body.

    The ``fail`` boolean parameter controls which method will handle the
    resulting response:

    * If ``fail=True`` (default), the request errback is called. The response
      object is available as the ``response`` attribute of the ``StopDownload``
      exception, which is in turn stored as the ``value`` attribute of the
      received :class:`~twisted.python.failure.Failure` object. This means that
      in an errback defined as ``def errback(self, failure)``, the response can
      be accessed though ``failure.value.response``.

    * If ``fail=False``, the request callback is called instead.

    In both cases, the response could have its body truncated: the body contains
    all bytes received up until the exception is raised, including the bytes
    received in the signal handler that raises the exception. Also, the response
    object is marked with ``"download_stopped"`` in its
    :attr:`~scrapy.http.Response.flags` attribute.
    """

    response: Response | None

    def __init__(self, *, fail: bool = True):
        super().__init__()
        self.fail = fail


class DownloadConnectionRefusedError(Exception):
    """Indicates that a connection was refused by the server."""


class CannotResolveHostError(Exception):
    """Indicates that the provided hostname cannot be resolved."""


class DownloadTimeoutError(Exception):
    """Indicates that a request download has timed out."""


class DownloadCancelledError(Exception):
    """Indicates that a request download was cancelled."""


class DownloadFailedError(Exception):
    """Indicates that a request download has failed."""


class ResponseDataLossError(Exception):
    """Indicates that Scrapy couldn't get a complete response."""


class UnsupportedURLSchemeError(Exception):
    """Indicates that the URL scheme is not supported."""


# Items


class DropItem(Exception):
    """Raised from the :meth:`process_item` method of an :ref:`item pipeline
    <topics-item-pipeline>` to stop the processing of an item."""

    def __init__(self, message: str, log_level: str | None = None):
        super().__init__(message)
        self.log_level = log_level


class NotSupported(Exception):
    """Raised to indicate that a requested feature is not supported.

    For example, Scrapy raises it when text-parsing shortcuts such as
    :meth:`response.css() <scrapy.http.TextResponse.css>` or
    :meth:`response.xpath() <scrapy.http.TextResponse.xpath>` are used on a
    :class:`~scrapy.http.Response` whose content is not text, or when sending a
    request whose URL scheme has no matching :ref:`download handler
    <topics-download-handlers>`."""


# Commands


class UsageError(Exception):
    """To indicate a command-line usage error"""

    def __init__(self, *a: Any, **kw: Any):
        self.print_help = kw.pop("print_help", True)
        super().__init__(*a, **kw)


class ScrapyDeprecationWarning(Warning):
    """Warning category for deprecated features, since the default
    :exc:`DeprecationWarning` is silenced.
    """


class ContractFail(AssertionError):
    """Error raised in case of a failing contract"""
