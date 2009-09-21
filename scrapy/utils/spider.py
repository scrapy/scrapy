from scrapy.item import BaseItem
from scrapy.utils.misc import  arg_to_iter


def iterate_spider_output(result):
    return [result] if isinstance(result, BaseItem) else arg_to_iter(result)

