import urlparse
import urllib
import bisect

from pydispatch import dispatcher
from twisted.web.client import getPage

from scrapy.core import log, signals
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.serialization import unserialize
from scrapy.conf import settings

class ClusterNode(object):
    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.maxproc = 0
        self.running = {}
        self.pending = []
        self.loadavg = (0.0, 0.0, 0.0)
        self.status = "down"  # down/crawling/idle/error
        self.available = False

        self.wsurl = urlparse.urljoin(self.url, "cluster_worker/ws/?format=json")

    def update(self):
        d = getPage(self.wsurl)
        d.addCallbacks(self._cbUpdate, self._ebUpdate)

    def schedule(self, domains):
        args = [("schedule", domain) for domain in domains]
        self._wsRequest(args)

    def stop(self, domains):
        args = [("stop", domain) for domain in domains]
        self._wsRequest(args)

    def remove(self, domains):
        args = [("remove", domain) for domain in domains]
        self._wsRequest(args)

    def _wsRequest(self, args):
        d = getPage("%s?%s" % (self.wsurl, urllib.urlencode(args)))
        d.addCallbacks(self._cbUpdate, self._ebUpdate)
        
    def _cbUpdate(self, jsonstatus):
        try:
            pmstatus = unserialize(jsonstatus, 'json')
            self.maxproc = int(pmstatus.get('maxproc', None))
            self.running = pmstatus.get('running') or {}
            self.pending = pmstatus.get('pending') or []
            self.loadavg = tuple(pmstatus.get('loadavg', (0.0, 0.0, 0.0)))
            self.status = "crawling" if self.running else "idle"
            self.available = True
        except ValueError:
            self.status = "error"
            self.available = False

    def _ebUpdate(self, err):
        self.status = "down"
        self.available = False


class ClusterMaster(object):

    def __init__(self):
        if not settings.getbool('CLUSTER_MASTER_ENABLED'):
            raise NotConfigured
        self.nodes = {}

        dispatcher.connect(self._engine_started, signal=signals.engine_started)

    def load_nodes(self):
        """Loads nodes from the CLUSTER_MASTER_NODES setting"""
        for name, url in settings.get('CLUSTER_MASTER_NODES', {}).iteritems():
            self.add_node(name, url)

    def update_nodes(self):
        for node in self.nodes.itervalues():
            node.update()

    def add_node(self, name, url):
        """Add node given its node"""
        if name not in self.nodes:
            node = ClusterNode(name, url)
            self.nodes[name] = node
            node.update()

    def remove_node(self, nodename):
        raise NotImplemented

    def schedule(self, domains, nodename=None):
        if nodename:
            node = self.nodes[nodename]
            node.schedule(domains)
        else:
            self._dispatch_domains(domains)

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
            for domain in node.running.iterkeys():
                d[domain] = node
        return d

    @property
    def pending(self):
        """Return dict of pending domains as domain -> node"""
        d = {}
        for node in self.nodes.itervalues():
            for domain in node.pending:
                d[domain] = node
        return d

    @property
    def available_nodes(self):
        return (node for node in self.nodes.itervalues() if node.available)

    def _dispatch_domains(self, domains):
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
            bisect.insort(pending_node, (len(node.pending), node))

            to_schedule[node.name] = []
            while domains and capacity > 0:
                to_schedule[node.name].append(domains.pop(0))
                capacity -= 1
            if not domains:
                break

        for domain in domains:
            pending, node = pending_node.pop(0)
            to_schedule[node.name].append(domain)
            bisect.insort(pending_node, (pending+1, node))
            
        for nodename, domains in to_schedule.iteritems():
            if domains:
                self.nodes[nodename].schedule(domains)

    def _engine_started(self):
        self.load_nodes()
        scrapyengine.addtask(self.update_nodes, settings.getint('CLUSTER_MASTER_POLL_INTERVAL'))

