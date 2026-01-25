"""Utils for built-in HTTP download handlers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from twisted.internet.defer import CancelledError
from twisted.internet.error import ConnectionRefusedError as TxConnectionRefusedError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.web.client import ResponseFailed
from twisted.web.error import SchemeNotSupported

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
