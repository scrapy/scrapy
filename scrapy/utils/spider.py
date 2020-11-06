import inspect
import logging

from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import arg_to_iter
try:
    from scrapy.utils.py36 import collect_asyncgen
except SyntaxError:
    collect_asyncgen = None


logger = logging.getLogger(__name__)


def iterate_spider_output(result):
    if collect_asyncgen and hasattr(inspect, 'isasyncgen') and inspect.isasyncgen(result):
        d = deferred_from_coro(collect_asyncgen(result))
        d.addCallback(iterate_spider_output)
        return d
    elif inspect.iscoroutine(result):
        d = deferred_from_coro(result)
        d.addCallback(iterate_spider_output)
        return d
    return arg_to_iter(result)


def _is_ignored(spider_class, *, require_name):
    return (
        not inspect.isclass(spider_class)
        or not issubclass(spider_class, Spider)
        or spider_class._is_ignored()
        or require_name and not getattr(spider_class, 'name', None)
    )


def iter_spider_classes(module, *, require_name=True):
    """Return an iterator over all :class:`~scrapy.spiders.Spider` subclasses
    defined in the given module, excluding those marked with
    :func:`scrapy.spiders.ignore_spider`.

    If `require_name` is ``True`` (default), any
    :class:`~scrapy.spiders.Spider` subclass without a non-empty
    :class:`~scrapy.spiders.Spider.name` is also excluded.
    """
    for obj in vars(module).values():
        if (
            not _is_ignored(obj, require_name=require_name)
            and obj.__module__ == module.__name__
        ):
            yield obj


def spidercls_for_request(spider_loader, request, default_spidercls=None,
                          log_none=False, log_multiple=False):
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
        logger.error('More than one spider can handle: %(request)s - %(snames)s',
                     {'request': request, 'snames': ', '.join(snames)})

    if len(snames) == 0 and log_none:
        logger.error('Unable to find spider that handles: %(request)s',
                     {'request': request})

    return default_spidercls


class DefaultSpider(Spider):
    name = 'default'
