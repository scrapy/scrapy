import os

from twisted.spread import pb
from twisted.internet import reactor

from scrapy.conf import settings
from scrapy import log
from scrapy.core.manager import scrapymanager
from scrapy.core.exceptions import NotConfigured

class Broker(pb.Referenceable):
    def __init__(self, crawler, remote):
        self.__remote = remote
        self.__crawler = crawler
        try:
            deferred = self.__remote.callRemote("register_crawler", os.getpid(), self)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=lambda x: None, errback=lambda reason: log.msg(reason, log.ERROR))
    def remote_stop(self):
        scrapymanager.stop()
    
class ClusterCrawler:
    def __init__(self):
        if not settings.getbool('CLUSTER_CRAWLER_ENABLED'):
            raise NotConfigured

        self.worker = None

        factory = pb.PBClientFactory()
        reactor.connectTCP("localhost", settings.getint('CLUSTER_WORKER_PORT'), factory)
        d = factory.getRootObject()
        def _set_worker(obj):
            self.worker = Broker(self, obj)
        d.addCallbacks(callback=_set_worker, errback=lambda reason: log.msg(reason, log.ERROR))
        
