from twisted.spread import pb
from twisted.internet import reactor

from scrapy.conf import settings
from scrapy.core import log
from scrapy.core.manager import scrapymanager

class Broker(pb.Referenceable):
    def __init__(self, crawler, remote):
        self.__remote = remote
        self.__crawler = crawler
        try:
            deferred = self.__remote.callRemote("register_crawler", domain, self)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))
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
        d.addCallbacks(callback=lambda obj: self.worker=Node(self, obj), errback=lambda reason: log.msg(reason, log.ERROR))
        