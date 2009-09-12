"""
This module provides a mechanism for collecting one (or more) sample items per
domain.

The items are collected in a dict of guid->item and persisted by pickling that
dict into a file.

This can be useful for testing changes made to the framework or other common
code that affects several spiders.

It uses the scrapy stats service to keep track of which domains are already
sampled.

Settings that affect this module:

ITEMSAMPLER_FILE
  file where to store the pickled dict of scraped items
ITEMSAMPLER_CLOSE_DOMAIN
  wether to close the domain after enough products have been sampled
ITEMSAMPLER_MAX_RESPONSE_SIZE
  maximum response size to process
"""

from __future__ import with_statement

import cPickle as pickle

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.core import signals
from scrapy.utils.response import response_httprepr
from scrapy.stats import stats
from scrapy.http import Request
from scrapy import log
from scrapy.conf import settings

items_per_domain = settings.getint('ITEMSAMPLER_COUNT', 1)
close_domain = settings.getbool('ITEMSAMPLER_CLOSE_DOMAIN', False)
max_response_size = settings.getbool('ITEMSAMPLER_MAX_RESPONSE_SIZE', )

class ItemSamplerPipeline(object):

    def __init__(self):
        self.filename = settings['ITEMSAMPLER_FILE']
        if not self.filename:
            raise NotConfigured
        self.items = {}
        self.domains_count = 0
        self.empty_domains = set()
        dispatcher.connect(self.domain_closed, signal=signals.domain_closed)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)

    def process_item(self, item, spider):
        domain = spider.domain_name
        sampled = stats.get_value("items_sampled", 0, domain=domain)
        if sampled < items_per_domain:
            self.items[item.guid] = item
            sampled += 1
            stats.set_value("items_sampled", sampled, domain=domain)
            log.msg("Sampled %s" % item, domain=domain, level=log.INFO)
            if close_domain and sampled == items_per_domain:
                scrapyengine.close_spider(spider)
        return item

    def engine_stopped(self):
        with open(self.filename, 'w') as f:
            pickle.dump(self.items, f)
        if self.empty_domains:
            log.msg("No products sampled for: %s" % " ".join(self.empty_domains), level=log.WARNING)

    def domain_closed(self, domain, spider, reason):
        if reason == 'finished' and not stats.get_value("items_sampled", domain=domain):
            self.empty_domains.add(domain)
        self.domains_count += 1
        log.msg("Sampled %d domains so far (%d empty)" % (self.domains_count, len(self.empty_domains)), level=log.INFO)


class ItemSamplerMiddleware(object):
    """This middleware drops items and requests (when domain sampling has been
    completed) to accelerate the processing of remaining domains"""

    def __init__(self):
        if not settings['ITEMSAMPLER_FILE']:
            raise NotConfigured

    def process_spider_input(self, response, spider):
        if stats.get_value("items_sampled", domain=spider.domain_name) >= items_per_domain:
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

        if stats.get_value("items_sampled", domain=spider.domain_name) >= items_per_domain:
            return []
        else:
            # TODO: this needs some revision, as keeping only the first item
            # may lead to differences when performing replays on sampled items
            return requests + items[0:]
