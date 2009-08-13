"""
Item pipeline

See documentation in docs/item-pipeline.rst
"""

from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.item import BaseItem
from scrapy.utils.misc import load_object
from scrapy.utils.defer import defer_succeed, mustbe_deferred
from scrapy.conf import settings

class ItemPipelineManager(object):

    def __init__(self):
        self.loaded = False
        self.enabled = {}
        self.disabled = {}
        self.pipeline = []
        self.load()

    def load(self):
        """
        Load pipelines stages defined in settings module
        """
        self.enabled.clear()
        self.disabled.clear()
        for pipepath in settings.getlist('ITEM_PIPELINES'):
            cls = load_object(pipepath)
            if cls:
                try:
                    pipe = cls()
                    self.pipeline.append(pipe)
                    self.enabled[cls.__name__] = pipe
                except NotConfigured, e:
                    self.disabled[cls.__name__] = pipepath
                    if e.args:
                        log.msg(e)
        log.msg("Enabled item pipelines: %s" % ", ".join(self.enabled.keys()),
            level=log.DEBUG)
        self.loaded = True

    def open_domain(self, domain):
        pass

    def close_domain(self, domain):
        pass

    def process_item(self, item, spider):
        if not self.pipeline:
            return defer_succeed(item)

        def next_stage(item, stages_left):
            assert isinstance(item, BaseItem), \
                'Item pipelines must return a BaseItem, got %s' % type(item).__name__
            if not stages_left:
                return item
            current_stage = stages_left.pop(0)
            d = mustbe_deferred(current_stage.process_item, spider.domain_name, item)
            d.addCallback(next_stage, stages_left)
            return d

        deferred = mustbe_deferred(next_stage, item, self.pipeline[:])
        return deferred
