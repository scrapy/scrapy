"""Utilities related to asyncio and its support in Scrapy."""

from scrapy.utils.reactor import is_asyncio_reactor_installed, is_reactor_installed


def is_asyncio_available() -> bool:
    """Check if it's possible to call asyncio code that relies on the asyncio event loop.

    .. versionadded:: VERSION

    Currently this function is identical to
    :func:`scrapy.utils.reactor.is_asyncio_reactor_installed`: it returns
    ``True`` if the Twisted reactor that is installed is
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor`, returns
    ``False`` if a different reactor is installed, and raises a
    :exc:`RuntimeError` if no reactor is installed. In a future Scrapy version,
    when Scrapy supports running without a Twisted reactor, this function will
    also return ``True`` when running in that mode, so code that doesn't
    directly require a Twisted reactor should use this function instead of
    :func:`~scrapy.utils.reactor.is_asyncio_reactor_installed`.

    When this returns ``True``, an asyncio loop is installed and used by
    Scrapy. It's possible to call functions that require it, such as
    :func:`asyncio.sleep`, and await on :class:`asyncio.Future` objects in
    Scrapy-related code.

    When this returns ``False``, a non-asyncio Twisted reactor is installed.
    It's not possible to use asyncio features that require an asyncio event
    loop or await on :class:`asyncio.Future` objects in Scrapy-related code,
    but it's possible to await on :class:`~twisted.internet.defer.Deferred`
    objects.
    """
    if not is_reactor_installed():
        raise RuntimeError(
            "is_asyncio_available() called without an installed reactor."
        )

    return is_asyncio_reactor_installed()
