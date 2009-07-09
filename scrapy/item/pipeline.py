from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.item import ScrapedItem
from scrapy.utils.misc import load_object
from scrapy.utils.defer import defer_succeed, mustbe_deferred
from scrapy.conf import settings

class ItemPipelineManager(object):

    def __init__(self):
        self.loaded = False
        self.pipeline = []
        self.load()

    def load(self):
        """
        Load pipelines stages defined in settings module
        """
        for stage in settings.getlist('ITEM_PIPELINES') or ():
            cls = load_object(stage)
            if cls:
                try:
                    stageinstance = cls()
                    self.pipeline.append(stageinstance)
                except NotConfigured:
                    pass
        log.msg("Enabled item pipelines: %s" % ", ".join([type(p).__name__ for p in self.pipeline]),
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
            assert isinstance(item, ScrapedItem), \
                'Item pipelines must return a ScrapedItem, got %s' % type(item).__name__
            if not stages_left:
                return item
            current_stage = stages_left.pop(0)
            d = mustbe_deferred(current_stage.process_item, spider.domain_name, item)
            d.addCallback(next_stage, stages_left)
            return d

        deferred = mustbe_deferred(next_stage, item, self.pipeline[:])
        return deferred
