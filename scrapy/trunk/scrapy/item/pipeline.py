from scrapy import log
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.item import ScrapedItem
from scrapy.utils.misc import load_class
from scrapy.utils.defer import defer_succeed, mustbe_deferred
from scrapy.conf import settings

class ItemPipelineManager(object):

    def __init__(self):
        self.loaded = False
        self.pipeline = []
        self.domaininfo = {}
        self.load()

    def load(self):
        """
        Load pipelines stages defined in settings module
        """
        for stage in settings.getlist('ITEM_PIPELINES') or ():
            cls = load_class(stage)
            if cls:
                try:
                    stageinstance = cls()
                    self.pipeline.append(stageinstance)
                except NotConfigured:
                    pass
        log.msg("Enabled item pipelines: %s" % ", ".join([type(p).__name__ for p in self.pipeline]))
        self.loaded = True

    def open_domain(self, domain):
        self.domaininfo[domain] = set()

    def close_domain(self, domain):
        del self.domaininfo[domain]

    def is_idle(self):
        return not self.domaininfo

    def domain_is_idle(self, domain):
        return not self.domaininfo.get(domain)

    def pipe(self, item, spider):
        """
        item pipelines are instanceable classes that defines a `pipeline` method
        that takes ScrapedItem as input and returns ScrapedItem.

        The output from one stage is the input of the next.

        Raising DropItem stops pipeline.

        This pipeline is configurable with the ITEM_PIPELINES setting
        """
        if not self.pipeline:
            return defer_succeed(item)

        domain = spider.domain_name
        pipeline = self.pipeline[:]
        current_stage = pipeline[0]
        info = self.domaininfo[domain]
        info.add(item)

        def _next_stage(item):
            assert isinstance(item, ScrapedItem), 'Pipeline stages must return a ScrapedItem or raise DropItem'
            if not pipeline:
                return item

            current_stage = pipeline.pop(0)
            log.msg("_%s_ Pipeline stage: %s" % (item, type(current_stage).__name__), log.TRACE, domain=domain)

            d = mustbe_deferred(current_stage.process_item, domain, item)
            d.addCallback(_next_stage)
            return d

        def _ondrop(_failure):
            ex = _failure.value
            if isinstance(ex, DropItem):
                # TODO: current_stage is not working, check why
                #log.msg("%s: Dropped %s - %s" % (type(current_stage).__name__, item, str(ex)), log.DEBUG, domain=domain)
                log.msg("Dropped %s - %s" % (item, str(ex)), log.DEBUG, domain=domain)
                return _failure
            else:
                # TODO: current_stage is not working, check why
                #log.msg('%s: Error processing %s - %s' % (type(current_stage).__name__, item, _failure), log.ERROR, domain=domain)
                log.msg('Error processing %s - %s' % (item, _failure), log.ERROR, domain=domain)

        def _pipeline_finished(_):
            log.msg("_%s_ Pipeline finished" % item, log.TRACE, domain=domain)
            info.remove(item)
            return _

        deferred = mustbe_deferred(_next_stage, item)
        deferred.addErrback(_ondrop)
        deferred.addBoth(_pipeline_finished)
        return deferred
