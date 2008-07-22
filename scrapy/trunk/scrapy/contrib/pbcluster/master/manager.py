import sys, datetime
import pickle

from pydispatch import dispatcher

from twisted.spread import pb
from twisted.internet import reactor

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
        self.available = True
        self.statistics = {"domains": {}, "scraped_total": 0 }

    def status_as_dict(self, verbosity=0):
        status = {"alive": self.alive}
        if self.alive:
            if verbosity == 0:
                #dont show spider settings
                status["running"] = []
                for proc in self.running:
                    proccopy = proc.copy()
                    del proccopy["settings"]
                    status["running"].append(proccopy)
            else:
                status["running"] = self.running
            status["maxproc"] = self.maxproc
            status["freeslots"] = self.maxproc - len(self.running)
            status["available"] = self.available
            status["starttime"] = self.starttime
            status["timestamp"] = self.timestamp
            status["loadavg"] = self.loadavg
        return status
        
    def _set_status(self, status):
        if not status:
            self.alive = False
        else:
            self.alive = True
            self.running = status['running']
            for proc in self.running:
                if proc["domain"] in self.master.loading:
                    self.master.loading.remove(proc["domain"])
            self.maxproc = status['maxproc']
            self.starttime = status['starttime']
            self.timestamp = status['timestamp']
            self.loadavg = status['loadavg']
            self.logdir = status['logdir']
            free_slots = self.maxproc - len(self.running)

            #load domains by one, so to mix up better the domain loading between nodes. The next one in the same node will be loaded
            #when there is no loading domain or in the next status update. This way also we load the nodes softly
            if self.available and free_slots > 0 and self.master.pending:
                pending = self.master.pending.pop(0)
                #if domain already running in some node, reschedule with same priority (so will be moved to run later)
                if pending['domain'] in self.master.running or pending['domain'] in self.master.loading:
                    self.master.schedule([pending['domain']], pending['settings'], pending['priority'])
                else:
                    self.run(pending)
                    self.master.loading.append(pending['domain'])

    def update_status(self):
        try:
            deferred = self.__remote.callRemote("status")
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))

    def update_statistics(self):
        
        def _set_statistics(statistics):
            self.statistics = statistics

        try:
            deferred = self.__remote.callRemote("statistics")
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=_set_statistics, errback=lambda reason: log.msg(reason, log.ERROR))
        
    def stop(self, domain):
        try:
            deferred = self.__remote.callRemote("stop", domain)
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=self._set_status, errback=lambda reason: log.msg(reason, log.ERROR))

    def run(self, pending):

        def _run_errback(reason):
            log.msg(reason, log.ERROR)
            self.master.loading.remove(pending['domain'])
            self.master.schedule([pending['domain']], pending['settings'], pending['priority'] - 1)
            log.msg("Domain %s rescheduled: lost connection to node." % pending['domain'], log.WARNING)
            
        def _run_callback(status):
            if status['callresponse'][0] == 1:
                #slots are complete. Reschedule in master with priority reduced by one.
                #self.master.loading check should avoid this to happen
                self.master.schedule([pending['domain']], pending['settings'], pending['priority'] - 1)
                log.msg("Domain %s rescheduled: no proc space in node." % pending['domain'], log.WARNING)
            elif status['callresponse'][0] == 2:
                #domain already running in node. Reschedule with same priority.
                #self.master.loading check should avoid this to happen
                self.master.schedule([pending['domain']], pending['settings'], pending['priority'])
                log.msg("Domain %s rescheduled: already running in node." % pending['domain'], log.WARNING)

        try:
            deferred = self.__remote.callRemote("run", pending["domain"], pending["settings"])
        except pb.DeadReferenceError:
            self._set_status(None)
            log.msg("Lost connection to node %s." % (self.name), log.ERROR)
        else:
            deferred.addCallbacks(callback=_run_callback, errback=_run_errback)
        

class ClusterMaster(pb.Root):

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
            self.pending = pickle.load( open(settings["CLUSTER_MASTER_CACHEFILE"], "r") )
        except IOError:
            self.pending = []
        self.loading = []
        self.nodes = {}
        self.statistics = {"domains": {}, "scraped_total": 0, "start_time": datetime.datetime.utcnow()}
        self.global_settings = {}
        #load cluster global settings
        for sname in settings.getlist('GLOBAL_CLUSTER_SETTINGS'):
            self.global_settings[sname] = settings[sname]
        
        dispatcher.connect(self._engine_started, signal=signals.engine_started)
        dispatcher.connect(self._engine_stopped, signal=signals.engine_stopped)
        port = settings.getint('CLUSTER_MASTER_PORT')
        scrapyengine.listenTCP(port, pb.PBServerFactory(self))
        
    def load_nodes(self):

        """Loads nodes from the CLUSTER_MASTER_NODES setting"""

        for name, url in settings.get('CLUSTER_MASTER_NODES', {}).iteritems():
            self.load_node(name, url)
            
    def load_node(self, name, url):

        def _make_callback(_factory, _name, _url):

            def _errback(_reason):
                log.msg("Could not get remote node %s in %s: %s." % (_name, _url, _reason), log.ERROR)

            d = _factory.getRootObject()
            d.addCallbacks(callback=lambda obj: self.add_node(obj, _name), errback=_errback)

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
        self.statistics["scraped_total"] = 0
        for name, url in settings.get('CLUSTER_MASTER_NODES', {}).iteritems():
            if name in self.nodes and self.nodes[name].alive:
                log.msg("Updating node. name: %s, url: %s" % (name, url) )
                self.nodes[name].update_status()
                self.nodes[name].update_statistics()
                self.statistics["scraped_total"] += self.nodes[name].statistics["scraped_total"]
                self.statistics["timestamp"] = datetime.datetime.utcnow()
                for domain in self.nodes[name].statistics["domains"]:
                    if not domain in self.statistics["domains"] or self.nodes[name].statistics["domains"][domain]["last_start_time"] >= self.statistics["domains"][domain]["last_start_time"]:
                        self.statistics["domains"][domain] = self.nodes[name].statistics["domains"][domain]
            else:
                log.msg("Reloading node. name: %s, url: %s" % (name, url) )
                self.load_node(name, url)

    def add_node(self, cworker, name):
        """Add node given its node"""
        node = Node(cworker, None, name, self)
        node.update_status()
        self.nodes[name] = node
        log.msg("Added cluster worker %s" % name)

    def disable_node(self, name):
        self.nodes[name].available = False
        
    def enable_node(self, name):
        self.nodes[name].available = True

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
            pd = self.find_ifpending(domain)
            if pd: #domain already pending, so just change priority if new is higher
                if priority < pd['priority']:
                    self.pending.remove(pd)
                    pd['priority'] = priority
                    self.pending.insert(i, pd)
            else:
                final_spider_settings = self.get_spider_groupsettings(domain)
                final_spider_settings.update(self.global_settings)
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

    def find_ifpending(self, domain):
        for p in self.pending:
            if domain == p['domain']:
                return p

    def print_pending(self, verbosity=0):
        if verbosity == 0:
            pending = []
            for p in self.pending:
                pp = p.copy()
                del pp["settings"]
                pending.append(pp)
            return pending
        else:
            return self.pending
        
    def _engine_started(self):
        self.load_nodes()
        scrapyengine.addtask(self.update_nodes, settings.getint('CLUSTER_MASTER_POLL_INTERVAL'))
    def _engine_stopped(self):
        pickle.dump( self.pending, open(settings["CLUSTER_MASTER_CACHEFILE"], "w") )
        log.msg("Pending saved in %s" % settings["CLUSTER_MASTER_CACHEFILE"])
