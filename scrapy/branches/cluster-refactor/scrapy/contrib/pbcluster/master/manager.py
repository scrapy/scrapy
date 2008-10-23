from __future__ import with_statement

import datetime
import cPickle as pickle

from pydispatch import dispatcher
from twisted.spread import pb
from twisted.internet import reactor

from scrapy.core import signals
from scrapy import log
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.contrib.pbcluster.worker.manager import ResponseCode
from scrapy.conf import settings

def my_import(name):
    mod = __import__(name)
    components = name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod

class ClusterNodeBroker(pb.Referenceable):

    def __init__(self, worker, name, master):
        self.unsafeTracebacks = True
        self._worker = worker
        self.alive = False
        self.name = name
        self.master = master
        self.available = True
        try:
            deferred = self._worker.callRemote("set_master", self)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("ClusterMaster: Lost connection to node %s." % self.name, log.ERROR)
        else:
            def _eb(failure):
                self._logfailure("Error while setting master to worker node", failure)
            deferred.addCallbacks(callback=self._set_status, errback=_eb)
            
    def status_as_dict(self, verbosity=1):
        if verbosity == 0:
            return
        status = {"alive": self.alive}
        if self.alive:
            if verbosity == 1:
                # dont show spider settings
                status["running"] = []
                for proc in self.running:
                    proccopy = proc.copy()
                    del proccopy["settings"]
                    status["running"].append(proccopy)
            elif verbosity == 2:
                status["running"] = self.running
            status["maxproc"] = self.maxproc
            status["freeslots"] = self.maxproc - len(self.running)
            status["available"] = self.available
            status["starttime"] = self.starttime
            status["timestamp"] = self.timestamp
            status["loadavg"] = self.loadavg
        return status
        
    def update_status(self):
        """Update status from this worker. This is called periodically."""
        try:
            deferred = self._worker.callRemote("status")
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("ClusterMaster: Lost connection to worker=%s." % self.name, log.ERROR)
        else:
            def _eb(failure):
                self._logfailure("Error while updating status", failure)
            deferred.addCallbacks(callback=self._set_status, errback=_eb)

    def stop(self, domain):
        try:
            deferred = self._worker.callRemote("stop", domain)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("ClusterMaster: Lost connection to worker=%s." % self.name, log.ERROR)
        else:
            def _eb(failure):
                self._logfailure("Error while stopping domain=%s" % domain, failure)
            deferred.addCallbacks(callback=self._set_status, errback=_eb)

    def run(self, domain_info):
        """Run the given domain. 
        
        domain_info is a dict of keys:
        domain - the domain to run
        settings - the settings to use
        priority - the priority to use
        """

        domain = domain_info['domain']
        dsettings  = domain_info['settings']
        priority = domain_info['priority']

        def _run_errback(failure):
            self._logfailure("Error while running domain=%s" % domain, failure)
            self.master.loading.remove(domain)
            newprio = priority - 1 # increase priority for reschedule
            self.master.reschedule([domain], dsettings, newprio, reason="error while try to run it")
            
        def _run_callback(status):
            if status['callresponse'][0] == ResponseCode.NO_FREE_SLOT:
                log.msg("ClusterMaster: No available slots at worker=%s when trying to run domain=%s" % (self.name, domain), log.WARNING)
                self.master.loading.remove(domain)
                newprio = priority - 1 # increase priority for rerunning asap
                self.master.reschedule([domain], dsettings, newprio, reason="no available slots at worker=%s" % self.name)
            elif status['callresponse'][0] == ResponseCode.DOMAIN_ALREADY_RUNNING:
                log.msg("ClusterMaster: Already running domain=%s at worker=%s" % (domain, self.name), log.WARNING)
                self.master.loading.remove(domain)
                self.master.reschedule([domain], dsettings, priority, reason="domain already running at worker=%s" % self.name)

        try:
            log.msg("ClusterMaster: Running domain=%s at worker=%s" % (domain, self.name), log.DEBUG)
            deferred = self._worker.callRemote("run", domain, dsettings)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("ClusterMaster: Lost connection to worker=%s." % self.name, log.ERROR)
        else:
            deferred.addCallbacks(callback=_run_callback, errback=_run_errback)
        
    def remote_update(self, worker_status, domain, domain_status):
        """Called remotely form worker when domains finish to update status"""
        self._set_status(worker_status)
        if domain in self.master.loading and domain_status == "running":
            self.master.loading.remove(domain)
            self.master.statistics["domains"]["running"].add(domain)
        elif domain_status in ("done", "terminated"):
            self.master.statistics["domains"]["running"].remove(domain)
            self.master.statistics["domains"]["scraped"][domain] = self.master.statistics["domains"]["scraped"].get(domain, 0) + 1
            self.master.statistics["scraped_count"] = self.master.statistics.get("scraped_count", 0) + 1
            if domain in self.master.statistics["domains"]["lost"]:
                self.master.statistics["domains"]["lost"].remove(domain)
        log.msg("ClusterMaster: Changed status to <%s> for domain=%s at worker=%s" % (domain_status, domain, self.name))

    def _logfailure(self, msg, failure):
        log.msg("ClusterMaster: %s (worker=%s)\n%s" % (msg, self.name, failure), log.ERROR)

    def _set_status(self, status):
        if not status:
            self.alive = False
        else:
            self.alive = True
            self.running = status['running']
            self.maxproc = status['maxproc']
            self.starttime = status['starttime']
            self.timestamp = status['timestamp']
            self.loadavg = status['loadavg']
            self.logdir = status['logdir']
            free_slots = self.maxproc - len(self.running)

            # load domains by one, so to mix up better the domain loading between nodes. The next one in the same node will be loaded
            # when there is no loading domain or in the next status update. This way also we load the nodes softly
            if self.available and free_slots > 0 and self.master.pending:
                pending = self.master.pending.pop(0)
                # if domain already running in some node, reschedule with same priority (so it will be run later)
                if pending['domain'] in self.master.running or pending['domain'] in self.master.loading:
                    self.master.reschedule([pending['domain']], pending['settings'], pending['priority'], reason="domain already running in other worker")
                else:
                    self.run(pending)
                    self.master.loading.append(pending['domain'])


class ScrapyPBClientFactory(pb.PBClientFactory):

    noisy = False

    def __init__(self, master, nodename):
        pb.PBClientFactory.__init__(self)
        self.unsafeTracebacks = True
        self.master = master
        self.nodename = nodename
        
    def clientConnectionLost(self, *args, **kargs):
        pb.PBClientFactory.clientConnectionLost(self, *args, **kargs)
        self.master.remove_node(self.nodename)
        log.msg("ClusterMaster: Lost connection to worker=%s. Node removed" % self.nodename)


class ClusterMaster(object):

    def __init__(self):

        if not settings.getbool('CLUSTER_MASTER_ENABLED'):
            raise NotConfigured

        self.statefile = settings['CLUSTER_MASTER_STATEFILE']
        if not self.statefile:
            raise NotConfigured("ClusterMaster: Missing CLUSTER_MASTER_STATEFILE setting")

        # import groups settings
        if settings.getbool('GROUPSETTINGS_ENABLED'):
            self.get_spider_groupsettings = my_import(settings["GROUPSETTINGS_MODULE"]).get_spider_groupsettings
        else:
            self.get_spider_groupsettings = lambda x: {}
        # load pending domains
        try:
            statefile = open(self.statefile, "r")
            self.pending = pickle.load(statefile)
            log.msg("ClusterMaster: Loaded state from %s" % self.statefile)
        except IOError:
            self.pending = []
        self.loading = []
        self.nodes = {}
        self.nodesconf = settings.get('CLUSTER_MASTER_NODES', {})
        self.start_time = datetime.datetime.utcnow()
        # for more info about statistics see self.update_nodes() and ClusterNodeBroker.remote_update()
        self.statistics = {"domains": {"running": set(), "scraped": {}, "lost_count": {}, "lost": set()}, "scraped_count": 0 }
        self.global_settings = {}
        # load cluster global settings
        for sname in settings.getlist('GLOBAL_CLUSTER_SETTINGS'):
            self.global_settings[sname] = settings[sname]
        
        dispatcher.connect(self._engine_started, signal=signals.engine_started)
        dispatcher.connect(self._engine_stopped, signal=signals.engine_stopped)
        
    def load_nodes(self):
        """Loads nodes listed in CLUSTER_MASTER_NODES setting"""
        for name, hostport in self.nodesconf.iteritems():
            self.load_node(name, hostport)
            
    def load_node(self, name, hostport):
        """Creates the remote reference for a worker node"""
        server, port = hostport.split(":")
        port = int(port)
        log.msg("ClusterMaster: Connecting to worker=%s (%s)..." % (name, hostport))
        factory = ScrapyPBClientFactory(self, name)
        try:
            reactor.connectTCP(server, port, factory)
        except Exception, err:
            log.msg("ClusterMaster: Could not connect to worker=%s (%s): %s" % (name, hostport, err), log.ERROR)
        else:
            def _eb(failure):
                log.msg("ClusterMaster: Could not connect to worker=%s (%s): %s" % (name, hostport, failure.value), log.ERROR)

            d = factory.getRootObject()
            d.addCallbacks(callback=lambda obj: self.add_node(obj, name), errback=_eb)

    def update_nodes(self):
        """Update worker nodes statistics"""
        for name, hostport in self.nodesconf.iteritems():
            if name in self.nodes and self.nodes[name].alive:
                self.nodes[name].update_status()
            else:
                self.load_node(name, hostport)
        
        real_running = set(self.running.keys())
        lost = self.statistics["domains"]["running"].difference(real_running)
        for domain in lost:
            self.statistics["domains"]["lost_count"][domain] = self.statistics["domains"]["lost_count"].get(domain, 0) + 1
        self.statistics["domains"]["lost"] = self.statistics["domains"]["lost"].union(lost)
            
    def add_node(self, cworker, name):
        """Add node given its node"""
        node = ClusterNodeBroker(cworker, name, self)
        self.nodes[name] = node
        log.msg("ClusterMaster: Added worker=%s" % name)

    def remove_node(self, nodename):
        del self.nodes[nodename]

    def disable_node(self, name):
        self.nodes[name].available = False
        
    def enable_node(self, name):
        self.nodes[name].available = True

    def _schedule(self, domains, spider_settings=None, priority=20):
        """Private method which performs the schedule of the given domains,
        with the given priority. Used for both scheduling and rescheduling."""
        insert_pos = len([p for p in self.pending if ['priority'] <= priority])
        for domain in domains:
            pd = self.get_first_pending(domain)
            if pd: # domain already pending, so just change priority if new is higher
                if priority < pd['priority']:
                    self.pending.remove(pd)
                    pd['priority'] = priority
                    self.pending.insert(insert_pos, pd)
            else:
                final_spider_settings = self.get_spider_groupsettings(domain)
                final_spider_settings.update(self.global_settings)
                final_spider_settings.update(spider_settings or {})
                self.pending.insert(insert_pos, {'domain': domain, 'settings': final_spider_settings, 'priority': priority})

    def schedule(self, domains, spider_settings=None, priority=20):
        """Schedule the given domains, with the given priority"""
        self._schedule(domains, spider_settings, priority)
        log.msg("clustermaster: Scheduled domains=%s with priority=%s" % (','.join(domains), priority), log.DEBUG)

    def reschedule(self, domains, spider_settings=None, priority=20, reason=None):
        """Reschedule the given domains, with the given priority"""
        self._schedule(domains, spider_settings, priority)
        log.msg("clustermaster: Rescheduled domains=%s with priority=%s reason='%s'" % (','.join(domains), priority, reason), log.DEBUG)


    def stop(self, domains):
        """Stop the given domains"""
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
        """Remove all scheduled instances of the given domains (if they haven't
        started yet). Otherwise use stop() to stop running domains"""

        self.pending = [p for p in self.pending if ['domain'] not in domains]

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

    def get_first_pending(self, domain):
        """Return first pending instance of a given domain"""
        for p in self.pending:
            if domain == p['domain']:
                return p

    def get_pending(self, verbosity=1):
        if verbosity == 1:
            pending = []
            for p in self.pending:
                pp = p.copy()
                del pp["settings"]
                pending.append(pp)
            return pending
        elif verbosity == 2:
            return self.pending
        return

    def _engine_started(self):
        self.load_nodes()
        scrapyengine.addtask(self.update_nodes, settings.getint('CLUSTER_MASTER_POLL_INTERVAL', 60))

    def _engine_stopped(self):
        with open(self.statefile, "w") as f:
            pickle.dump(self.pending, f)
            log.msg("ClusterMaster: Saved state in %s" % self.statefile)
