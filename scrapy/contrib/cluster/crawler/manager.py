import os

from twisted.spread import pb
from twisted.internet import reactor

from scrapy.conf import settings
from scrapy import log
from scrapy.core.manager import scrapymanager
from scrapy.core.exceptions import NotConfigured

class ClusterCrawlerBroker(pb.Referenceable):
    """ClusterCrawlerBroker is the class that's used for communication between
    the cluster worker and the crawling proces"""

    def __init__(self, crawler, remote):
        self.__remote = remote
        self.__crawler = crawler
        deferred = self.__remote.callRemote("register_crawler", os.getpid(), self)
        deferred.addCallbacks(callback=lambda x: None, errback=lambda reason: log.msg(reason, log.ERROR))

    def remote_stop(self):
        scrapymanager.stop()
    
class ClusterCrawler(object):
    """ClusterCrawler is an extension that instances a ClusterCrawlerBroker
    which is used to control a crawling process from the cluster worker. It
    also registers that broker to the local cluster worker"""

    def __init__(self):
        if not settings.getbool('CLUSTER_CRAWLER_ENABLED'):
            raise NotConfigured

        self.worker = None

        factory = pb.PBClientFactory()
        reactor.connectTCP("localhost", settings.getint('CLUSTER_WORKER_PORT'), factory)
        d = factory.getRootObject()
        def _set_worker(obj):
            self.worker = ClusterCrawlerBroker(self, obj)
        d.addCallbacks(callback=_set_worker, errback=lambda reason: log.msg(reason, log.ERROR))
        
