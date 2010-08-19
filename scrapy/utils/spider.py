import inspect

from scrapy.item import BaseItem
from scrapy.utils.misc import  arg_to_iter


def iterate_spider_output(result):
    return [result] if isinstance(result, BaseItem) else arg_to_iter(result)

def iter_spider_classes(module):
    """Return an iterator over all spider classes defined in the given module
    that can be instantiated (ie. which have name)
    """
    # this needs to be imported here until get rid of the spider manager
    # singleton in scrapy.spider.spiders
    from scrapy.spider import BaseSpider

    for obj in vars(module).itervalues():
        if inspect.isclass(obj) and \
           issubclass(obj, BaseSpider) and \
           obj.__module__ == module.__name__ and \
           getattr(obj, 'name', None):
            yield obj
