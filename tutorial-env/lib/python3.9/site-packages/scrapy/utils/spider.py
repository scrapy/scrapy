from __future__ import annotations

import inspect
import logging
from types import CoroutineType, ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Generator,
    Iterable,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from twisted.internet.defer import Deferred

from scrapy import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import arg_to_iter

if TYPE_CHECKING:
    from scrapy.spiderloader import SpiderLoader

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# https://stackoverflow.com/questions/60222982
@overload
def iterate_spider_output(result: AsyncGenerator) -> AsyncGenerator:  # type: ignore[misc]
    ...


@overload
def iterate_spider_output(result: CoroutineType) -> Deferred:
    ...


@overload
def iterate_spider_output(result: _T) -> Iterable:
    ...


def iterate_spider_output(result: Any) -> Union[Iterable, AsyncGenerator, Deferred]:
    if inspect.isasyncgen(result):
        return result
    if inspect.iscoroutine(result):
        d = deferred_from_coro(result)
        d.addCallback(iterate_spider_output)
        return d
    return arg_to_iter(deferred_from_coro(result))


def iter_spider_classes(module: ModuleType) -> Generator[Type[Spider], Any, None]:
    """Return an iterator over all spider classes defined in the given module
    that can be instantiated (i.e. which have name)
    """
    # this needs to be imported here until get rid of the spider manager
    # singleton in scrapy.spider.spiders
    from scrapy.spiders import Spider

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
    spider_loader: SpiderLoader,
    request: Request,
    default_spidercls: Type[Spider],
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> Type[Spider]:
    ...


@overload
def spidercls_for_request(
    spider_loader: SpiderLoader,
    request: Request,
    default_spidercls: Literal[None],
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> Optional[Type[Spider]]:
    ...


@overload
def spidercls_for_request(
    spider_loader: SpiderLoader,
    request: Request,
    *,
    log_none: bool = ...,
    log_multiple: bool = ...,
) -> Optional[Type[Spider]]:
    ...


def spidercls_for_request(
    spider_loader: SpiderLoader,
    request: Request,
    default_spidercls: Optional[Type[Spider]] = None,
    log_none: bool = False,
    log_multiple: bool = False,
) -> Optional[Type[Spider]]:
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
