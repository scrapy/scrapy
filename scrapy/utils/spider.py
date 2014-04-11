from scrapy import log
from scrapy.item import BaseItem
from scrapy.utils.misc import  arg_to_iter


def iterate_spider_output(result):
    return [result] if isinstance(result, BaseItem) else arg_to_iter(result)

def create_spider_for_request(spidermanager, request, default_spider=None, \
        log_none=False, log_multiple=False, **spider_kwargs):
    """Create a spider to handle the given Request.

    This will look for the spiders that can handle the given request (using
    the spider manager) and return a (new) Spider if (and only if) there is
    only one Spider able to handle the Request.

    If multiple spiders (or no spider) are found, it will return the
    default_spider passed. It can optionally log if multiple or no spiders
    are found.
    """
    snames = spidermanager.find_by_request(request)
    if len(snames) == 1:
        return spidermanager.create(snames[0], **spider_kwargs)

    if len(snames) > 1 and log_multiple:
        log.msg(format='More than one spider can handle: %(request)s - %(snames)s',
                level=log.ERROR, request=request, snames=', '.join(snames))

    if len(snames) == 0 and log_none:
        log.msg(format='Unable to find spider that handles: %(request)s',
                level=log.ERROR, request=request)

    return default_spider

