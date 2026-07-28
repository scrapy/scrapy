"""Boto/botocore helpers"""

from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.settings import BaseSettings


def is_botocore_available() -> bool:
    return find_spec("botocore") is not None


def _get_max_pool_connections(settings: BaseSettings) -> int:
    """Return the maximum number of connections that AWS clients may keep in
    their connection pool.

    AWS clients are used from the reactor thread pool, so its size is a sensible
    default for the size of their connection pool.
    """
    return settings.getint("AWS_MAX_POOL_CONNECTIONS") or settings.getint(
        "REACTOR_THREADPOOL_MAXSIZE"
    )
