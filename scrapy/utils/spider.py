from __future__ import annotations

import inspect
import logging
import warnings
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.spiders import Spider
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.defer import _is_awaitable, deferred_from_coro
from scrapy.utils.misc import arg_to_iter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Iterable
    from types import ModuleType

    from twisted.internet.defer import Deferred

    from scrapy import Request
    from scrapy.spiderloader import SpiderLoaderProtocol


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# https://stackoverflow.com/questions/60222982
@overload
def iterate_spider_output(result: AsyncGenerator[_T]) -> AsyncGenerator[_T]: ...  # type: ignore[overload-overlap]


@overload
def iterate_spider_output(
    result: Coroutine[Any, Any, Any],
) -> Deferred[Iterable[Any]]: ...


@overload
def iterate_spider_output(result: _T) -> Iterable[Any]: ...


def iterate_spider_output(
    result: Any,
) -> Iterable[Any] | AsyncGenerator[_T] | Deferred[Iterable[Any]]:
    if inspect.isasyncgen(result):
        return cast("AsyncGenerator[_T]", result)
    d: Deferred[_T] = deferred_from_coro(result)
    if inspect.iscoroutine(result):
        warnings.warn(
            "Passing a coroutine to iterate_spider_output() is deprecated."
            " For a coroutine it returns a Deferred instead of an iterable, so"
            " iterating over the result does not work. Await the coroutine and"
            " pass its result instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return d.addCallback(iterate_spider_output)
    return arg_to_iter(d)


async def _await_spider_output(result: Any) -> Any:
    """Return *result*, the output of a spider callback, awaiting it first if
    it is awaitable, or collecting it into a list if it is an asynchronous
    iterator."""
    if isinstance(result, AsyncIterator):
        return await collect_asyncgen(result)
    if _is_awaitable(result):
        return await result
    return result


def iter_spider_classes(module: ModuleType) -> Iterable[type[Spider]]:
    """Return an iterator over all spider classes defined in the given module
    that can be instantiated (i.e. which have name)
    """
    for obj in vars(module).values():
        if (
            inspect.isclass(obj)
            and issubclass(obj, Spider)
            and obj.__module__ == module.__name__
            and getattr(obj, "name", None)
        ):
            yield obj


@overload
def spidercls_for_request(
    spider_loader: SpiderLoaderProtocol,
    request: Request,
    default_spidercls: type[Spider],
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> type[Spider]: ...


@overload
def spidercls_for_request(
    spider_loader: SpiderLoaderProtocol,
    request: Request,
    default_spidercls: None,
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> type[Spider] | None: ...


@overload
def spidercls_for_request(
    spider_loader: SpiderLoaderProtocol,
    request: Request,
    *,
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> type[Spider] | None: ...


def spidercls_for_request(
    spider_loader: SpiderLoaderProtocol,
    request: Request,
    default_spidercls: type[Spider] | None = None,
    log_none: bool = False,
    log_multiple: bool = False,
) -> type[Spider] | None:
    """Return a spider class that handles the given Request.

    This will look for the spiders that can handle the given request (using
    the spider loader) and return a Spider class if (and only if) there is
    only one Spider able to handle the Request.

    If multiple spiders (or no spider) are found, it will return the
    default_spidercls passed. It can optionally log if multiple or no spiders
    are found.
    """
    snames = spider_loader.find_by_request(request)
    if len(snames) == 1:
        return spider_loader.load(snames[0])

    if len(snames) > 1 and log_multiple:
        logger.error(
            "More than one spider can handle: %(request)s - %(snames)s",
            {"request": request, "snames": ", ".join(snames)},
        )

    if len(snames) == 0 and log_none:
        logger.error(
            "Unable to find spider that handles: %(request)s", {"request": request}
        )

    return default_spidercls


class DefaultSpider(Spider):
    name = "default"
