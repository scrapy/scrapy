import logging
import inspect
try:
    import asyncio
except ImportError:
    asyncio = None

import six
from twisted.internet.defer import Deferred

from scrapy.spiders import Spider
from scrapy.utils.misc import  arg_to_iter
try:
    from scrapy.utils.aio_py36 import collect_asyncgen
except SyntaxError:
    pass

logger = logging.getLogger(__name__)


def iterate_spider_output(result):
    # FIXME check if changes need to be made here or just when calling from  scrapy.core.scraper
    # TODO probably add other cases from ensure_future here
    # FIXME hmm which is the proper check for async def coroutines?
    if asyncio is not None and hasattr(result, '__await__') and asyncio.coroutines.iscoroutine(result):
        d = _aio_as_deferred(result)
        d.addCallback(iterate_spider_output)
        return d
    elif hasattr(inspect, 'isasyncgen') and inspect.isasyncgen(result):
        d = _aio_as_deferred(collect_asyncgen(result))
        d.addCallback(iterate_spider_output)
        return d
    else:
        return arg_to_iter(result)


def _aio_as_deferred(f):
    return Deferred.fromFuture(asyncio.ensure_future(f))


def iter_spider_classes(module):
    """Return an iterator over all spider classes defined in the given module
    that can be instantiated (ie. which have name)
    """
    # this needs to be imported here until get rid of the spider manager
    # singleton in scrapy.spider.spiders
    from scrapy.spiders import Spider

    for obj in six.itervalues(vars(module)):
        if inspect.isclass(obj) and \
           issubclass(obj, Spider) and \
           obj.__module__ == module.__name__ and \
           getattr(obj, 'name', None):
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
