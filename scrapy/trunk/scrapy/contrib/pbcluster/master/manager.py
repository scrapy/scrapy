import urlparse
import urllib
import bisect
import sys

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

class Node:
    def __init__(self, remote, status, name):
        self.__remote = remote
        self._set_status(status)
        self.name = name

    def _set_status(self, status):
        if not status:
            self.available = False
        else:
            self.available = True
            self.running = status['running']
            self.pending = status['pending']
            self.maxproc = status['maxproc']
            self.starttime = status['starttime']
            self.timestamp = status['timestamp']
            self.loadavg = status['loadavg']
            self.logdir = status['logdir']
            self.lastcallresponse = status['callresponse']

    def _remote_call(self, function, *args):
        try:
            deferred = self.__remote.callRemote(function, *args)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))

    def get_status(self):
        self._remote_call("status")

    def schedule(self, domains, spider_settings=None, priority=PRIORITY_NORMAL):
        self._remote_call("schedule", domains, spider_settings, priority)

    def stop(self, domains):
        self._remote_call("stop", domains)

    def remove(self, domains):
        self._remote_call("remove", domains)

class ClusterMaster(object):

    def __init__(self):
        if not settings.getbool('CLUSTER_MASTER_ENABLED'):
            raise NotConfigured
        self.nodes = {}
        self.queue = []
        dispatcher.connect(self._engine_started, signal=signals.engine_started)

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
        node = Node(cworker, None, name)
        node.get_status()
        self.nodes[name] = node
        log.msg("Added cluster worker %s" % name)

    def remove_node(self, nodename):
        raise NotImplemented

    def schedule(self, domains, spider_settings=None, nodename=None, priority=PRIORITY_NORMAL):
        if nodename:
            self.nodes[nodename].schedule(domains, spider_settings, priority)
        else:
            self._dispatch_domains(domains, spider_settings, priority)

    def stop(self, domains):
        to_stop = {}
        for domain in domains:
            node = self.running.get(domain, None)
            if node:
                if node.name not in to_stop:
                    to_stop[node.name] = []
                to_stop[node.name].append(domain)

        for nodename, domains in to_stop.iteritems():
            self.nodes[nodename].stop(domains)

    def remove(self, domains):
        to_remove = {}
        for domain in domains:
            node = self.pending.get(domain, None)
            if node:
                if node.name not in to_remove:
                    to_remove[node.name] = []
                to_remove[node.name].append(domain)

        for nodename, domains in to_remove.iteritems():
            self.nodes[nodename].remove(domains)

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
    def pending(self):
        """Return dict of pending domains as domain -> node"""
        d = {}
        for node in self.nodes.itervalues():
            for p in node.pending:
                d[p['domain']] = node
        return d

    @property
    def available_nodes(self):
        return (node for node in self.nodes.itervalues() if node.available)

    def _dispatch_domains(self, domains, spider_settings, priority):
        """Schedule the given domains in the availables nodes as good as
        possible. The algorithm follows the next rules (in order):
        
        1. search for nodes with available capacity(running < maxproc) and (if
        any) schedules the domains there

        2. if there isn't any node with available capacity it schedules the
        domain in the node with the smallest number of pending spiders
        """

        to_schedule = {}  # domains to schedule per node
        pending_node = [] # list of #pending, node

        for node in self.available_nodes:
            capacity = node.maxproc - len(node.running)
            #order nodes in pending_node according to insertion position, calculated from priority comparison, for stage 2.
            i = 0
            for p in node.pending:
                if p['priority'] <= priority:
                    i += 1
                else:
                    break
            bisect.insort(pending_node, (i, node))

            #stage 1: use available capacity
            to_schedule[node.name] = []
            while domains and capacity > 0:
                to_schedule[node.name].append(domains.pop(0))
                capacity -= 1
            if not domains:
                break

        #stage 2: queue in pendings the remaining domains.
        # a) pops out minor insertion-point node b) schedules the domain c) reinserts the node in list with insertion-point incremented by one.
        for domain in domains:
            insert_point, node = pending_node.pop(0)
            to_schedule[node.name].append(domain)
            bisect.insort(pending_node, (insert_point+1, node))
            
        for nodename, domains in to_schedule.iteritems():
            if domains:
                self.nodes[nodename].schedule(domains, spider_settings, priority)

    def _engine_started(self):
        self.load_nodes()
        scrapyengine.addtask(self.update_nodes, settings.getint('CLUSTER_MASTER_POLL_INTERVAL'))
