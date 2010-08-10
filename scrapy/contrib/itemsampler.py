"""
This module provides a mechanism for collecting one (or more) sample items per
spider.

The items are collected in a dict of guid->item and persisted by pickling that
dict into a file.

This can be useful for testing changes made to the framework or other common
code that affects several spiders.

It uses the scrapy stats service to keep track of which spiders are already
sampled.

Settings that affect this module:

ITEMSAMPLER_FILE
  file where to store the pickled dict of scraped items
ITEMSAMPLER_CLOSE_SPIDER
  wether to close the spider after enough products have been sampled
ITEMSAMPLER_MAX_RESPONSE_SIZE
  maximum response size to process
"""

from __future__ import with_statement

import cPickle as pickle

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core.manager import scrapymanager
from scrapy.exceptions import NotConfigured
from scrapy import signals
from scrapy.utils.response import response_httprepr
from scrapy.stats import stats
from scrapy.http import Request
from scrapy import log
from scrapy.conf import settings

items_per_spider = settings.getint('ITEMSAMPLER_COUNT', 1)
close_spider = settings.getbool('ITEMSAMPLER_CLOSE_SPIDER', False)
max_response_size = settings.getbool('ITEMSAMPLER_MAX_RESPONSE_SIZE', )

class ItemSamplerPipeline(object):

    def __init__(self):
        self.filename = settings['ITEMSAMPLER_FILE']
        if not self.filename:
            raise NotConfigured
        self.items = {}
        self.spiders_count = 0
        self.empty_spiders = set()
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)

    def process_item(self, spider, item):
        sampled = stats.get_value("items_sampled", 0, spider=spider)
        if sampled < items_per_spider:
            self.items[item.guid] = item
            sampled += 1
            stats.set_value("items_sampled", sampled, spider=spider)
            log.msg("Sampled %s" % item, spider=spider, level=log.INFO)
            if close_spider and sampled == items_per_spider:
                scrapymanager.engine.close_spider(spider)
        return item

    def engine_stopped(self):
        with open(self.filename, 'w') as f:
            pickle.dump(self.items, f)
        if self.empty_spiders:
            log.msg("No products sampled for: %s" % " ".join(self.empty_spiders), \
                level=log.WARNING)

    def spider_closed(self, spider, reason):
        if reason == 'finished' and not stats.get_value("items_sampled", spider=spider):
            self.empty_spiders.add(spider.name)
        self.spiders_count += 1
        log.msg("Sampled %d spiders so far (%d empty)" % (self.spiders_count, \
            len(self.empty_spiders)), level=log.INFO)


class ItemSamplerMiddleware(object):
    """This middleware drops items and requests (when spider sampling has been
    completed) to accelerate the processing of remaining spiders"""

    def __init__(self):
        if not settings['ITEMSAMPLER_FILE']:
            raise NotConfigured

    def process_spider_input(self, response, spider):
        if stats.get_value("items_sampled", spider=spider) >= items_per_spider:
            return []
        elif max_response_size and max_response_size > len(response_httprepr(response)):  
            return []

    def process_spider_output(self, response, result, spider):
        requests, items = [], []
        for r in result:
            if isinstance(r, Request):
                requests.append(r)
            else:
                items.append(r)

        if stats.get_value("items_sampled", spider=spider) >= items_per_spider:
            return []
        else:
            # TODO: this needs some revision, as keeping only the first item
            # may lead to differences when performing replays on sampled items
            return requests + items[0:]
