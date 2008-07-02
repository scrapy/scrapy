import urlparse
import urllib
import bisect
import sys
import pickle, socket

from pydispatch import dispatcher

from twisted.spread import pb
from twisted.internet import reactor
from twisted.python import util

from scrapy.core import log, signals
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

priorities = { 20:'NORMAL',
               10:'QUICK',
                0:'NOW',
}

# Set priorities module attributes
for val, attr in priorities.items():
    setattr(sys.modules[__name__], "PRIORITY_%s" % attr, val )

def my_import(name):
    mod = __import__(name)
    components = name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod

class Node:
    def __init__(self, remote, status, name, master):
        self.__remote = remote
        self._set_status(status)
        self.name = name
        self.master = master

    def _set_status(self, status):
        self.status_as_dict = status
        if not status:
            self.available = False
        else:
            self.available = True
            self.running = status['running']
            self.maxproc = status['maxproc']
            self.starttime = status['starttime']
            self.timestamp = status['timestamp']
            self.loadavg = status['loadavg']
            self.logdir = status['logdir']
            free_slots = self.maxproc - len(self.running)
            while free_slots > 0 and self.master.pending:
                pending = self.master.pending.pop(0)
                self.run(pending)
                free_slots -= 1

    def get_status(self):
        try:
            deferred = self.__remote.callRemote("status")
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))

    def stop(self, domain):
        try:
            deferred = self.__remote.callRemote("stop", domain)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))

    def run(self, pending):

        def _run_callback(status):
            if status['callresponse'][0] == 1:
                #slots are complete. Reschedule in master. This is a security issue because could happen that the slots were completed since last status update by another cluster (thinking at future with full-distributed worker-master clusters)
                self.master.schedule(pending['domain'], pending['settings'], pending['priority'])
                log.msg("Domain %s rescheduled: no proc space in node." % pending['domain'], log.WARNING)
            self._set_status(status)

        try:
            deferred = self.__remote.callRemote("run", pending["domain"], pending["settings"])
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=_run_callback, errback=lambda reason:log.msg(reason, log.ERROR))

class ClusterMaster(object):

    def __init__(self):

        if not (settings.getbool('CLUSTER_MASTER_ENABLED')):
            raise NotConfigured

        #import groups settings
        if settings.getbool('GROUPSETTINGS_ENABLED'):
            self.get_spider_groupsettings = my_import(settings["GROUPSETTINGS_MODULE"]).get_spider_groupsettings
        else:
            self.get_spider_groupsettings = lambda x: {}

        #load pending domains
        try:
            self.pending = pickle.load( open("pending_cache_%s" % socket.gethostname(), "r") )
        except IOError:
            self.pending = []

        self.nodes = {}
        dispatcher.connect(self._engine_started, signal=signals.engine_started)
        dispatcher.connect(self._engine_stopped, signal=signals.engine_stopped)
        
    def load_nodes(self):

        def _make_callback(_factory, _name, _url):

            def _errback(_reason):
                log.msg("Could not get remote node %s in %s: %s." % (_name, _url, _reason), log.ERROR)

            d = _factory.getRootObject()
            d.addCallbacks(callback=lambda obj: self.add_node(obj, _name), errback=_errback)

        """Loads nodes from the CLUSTER_MASTER_NODES setting"""

        for name, url in settings.get('CLUSTER_MASTER_NODES', {}).iteritems():
            if name not in self.nodes:
                server, port = url.split(":")
                port = eval(port)
                log.msg("Connecting to cluster worker %s..." % name)
                log.msg("Server: %s, Port: %s" % (server, port))
                factory = pb.PBClientFactory()
                try:
                    reactor.connectTCP(server, port, factory)
                except Exception, err:
                    log.msg("Could not connect to node %s in %s: %s." % (name, url, reason), log.ERROR)
                else:
                    _make_callback(factory, name, url)

    def update_nodes(self):
        for node in self.nodes.itervalues():
            node.get_status()

    def add_node(self, cworker, name):
        """Add node given its node"""
        node = Node(cworker, None, name, self)
        node.get_status()
        self.nodes[name] = node
        log.msg("Added cluster worker %s" % name)

    def remove_node(self, nodename):
        raise NotImplemented

    def schedule(self, domains, spider_settings=None, priority=PRIORITY_NORMAL):
        i = 0
        for p in self.pending:
            if p['priority'] <= priority:
                i += 1
            else:
                break
        for domain in domains:
            final_spider_settings = self.get_spider_groupsettings(domain)
            final_spider_settings.update(spider_settings or {})
            self.pending.insert(i, {'domain': domain, 'settings': final_spider_settings, 'priority': priority})
        self.update_nodes()

    def stop(self, domains):
        to_stop = {}
        for domain in domains:
            node = self.running.get(domain, None)
            if node:
                if node.name not in to_stop:
                    to_stop[node.name] = []
                to_stop[node.name].append(domain)

        for nodename, domains in to_stop.iteritems():
            for domain in domains:
                self.nodes[nodename].stop(domain)

    def remove(self, domains):
        """Remove all scheduled instances of the given domains (if it hasn't
        started yet). Otherwise use stop()"""

        for domain in domains:
            to_remove = []
            for p in self.pending:
                if p['domain'] == domain:
                    to_remove.append(p)
    
            for p in to_remove:
                self.pending.remove(p)

    def discard(self, domains):
        """Stop and remove all running and pending instances of the given
        domains"""
        self.remove(domains)
        self.stop(domains)

    @property
    def running(self):
        """Return dict of running domains as domain -> node"""
        d = {}
        for node in self.nodes.itervalues():
            for proc in node.running:
                d[proc['domain']] = node
        return d

    @property
    def available_nodes(self):
        return (node for node in self.nodes.itervalues() if node.available)

    def _engine_started(self):
        self.load_nodes()
        scrapyengine.addtask(self.update_nodes, settings.getint('CLUSTER_MASTER_POLL_INTERVAL'))
    def _engine_stopped(self):
        pickle.dump( self.pending, open("pending_cache_%s" % socket.gethostname(), "w") )