import sys
import os
import time
import datetime

from twisted.internet import protocol, reactor
from twisted.spread import pb

from scrapy.core import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings
from scrapy.core.engine import scrapyengine

class ScrapyProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, procman, domain, logfile=None, spider_settings=None):
        self.procman = procman
        self.domain = domain
        self.logfile = logfile
        self.start_time = datetime.datetime.utcnow()
        self.status = "starting"
        self.pid = -1

        env = {'SCRAPY_LOGFILE': self.logfile, 'SCRAPY_CLUSTER_WORKER_ENABLED': '0', 'SCRAPY_WEBCONSOLE_ENABLED': '0'}
        #We conserve original setting format for info purposes (avoid lots of unnecesary "SCRAPY_")
        self.settings = spider_settings or {}
        for k in self.settings:
            env["SCRAPY_%s" % k] = self.settings[k]
        self.env = env

    def __str__(self):
        return "<ScrapyProcess domain=%s, pid=%s, status=%s>" % (self.domain, self.pid, self.status)

    def as_dict(self):
        return {"domain": self.domain, "pid": self.pid, "status": self.status, "settings": self.settings, "logfile": self.logfile, "starttime": self.start_time}

    def connectionMade(self):
        self.pid = self.transport.pid
        log.msg("ClusterWorker: started domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        self.transport.closeStdin()
        self.status = "running"

    def processEnded(self, status_object):
        log.msg("ClusterWorker: finished domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        del self.procman.running[self.domain]
        self.procman.next_pending()

class ClusterWorker(pb.Root):

    def __init__(self):
        if not settings.getbool('CLUSTER_WORKER_ENABLED'):
            raise NotConfigured

        self.maxproc = settings.getint('CLUSTER_WORKER_MAXPROC')
        self.logdir = settings['CLUSTER_WORKER_LOGDIR']
        self.running = {}
        self.pending = []
        self.starttime = time.time()
        port = settings.getint('CLUSTER_WORKER_PORT')
        scrapyengine.listenTCP(port, pb.PBServerFactory(self))

    def remote_schedule(self, domains, spider_settings=None, priority=20):
        """Schedule new domains to be crawled in a separate processes"""

        responses = []
        for domain in domains:
            if len(self.running) < self.maxproc and domain not in self.running:
                self._run(domain, spider_settings)
                responses.append("Started %s" % self.running[domain])
            else:
                i = 0
                for p in self.pending:
                    if p['priority'] <= priority:
                        i += 1
                    else:
                        break
                self.pending.insert(i, {'domain': domain, 'settings': spider_settings, 'priority': priority})
                responses.append("Scheduled domain %s at position %s in queue" % (domain, i))
        return self.status(responses)

    def remote_stop(self, domains):
        """Stop running domains. For removing pending (not yet started) domains
        use remove() instead"""

        responses = []
        for domain in domains:
            if domain in self.running:
                proc = self.running[domain]
                log.msg("ClusterWorker: Sending shutdown signal to domain=%s, pid=%d" % (domain, proc.pid))
                proc.transport.signalProcess('INT')
                proc.status = "closing"
                responses.append("Stopped process %s" % proc)
            else:
                responses.append("%s: domain not running." % domain)
        return self.status(responses)

    def remote_remove(self, domains):
        """Remove all scheduled instances of the given domains (if it hasn't
        started yet). Otherwise use stop()"""

        responses = []
        for domain in domains:
            to_remove = []
            for p in self.pending:
                if p['domain'] == domain:
                    to_remove.append(p)
    
            for p in to_remove:
                self.pending.remove(p)
            responses.append("Unscheduled domain %s" % domain)
        return self.status(responses)

    def remote_status(self):
        return self.status()
    
    def status(self, response="Status Response"):
        status = {}
        status["pending"] = self.pending
        status["running"] = [ self.running[k].as_dict() for k in self.running.keys() ]
        status["starttime"] = self.starttime
        status["timestamp"] = time.time()
        status["maxproc"] = self.maxproc
        status["loadavg"] = os.getloadavg()
        status["logdir"] = self.logdir
        status["callresponse"] = response
        return status
        
    def next_pending(self):
        """Run the next domain in the pending list, which is not already running"""

        if len(self.running) >= self.maxproc:
            return
        for p in self.pending:
            if p['domain'] not in self.running:
                self._run(p['domain'], p['settings'])
                self.pending.remove(p)
                return

    def _run(self, domain, spider_settings=None):
        """Spawn process to run the given domain. Don't call this method
        directly. Instead use schedule()."""

        logfile = os.path.join(self.logdir, domain, time.strftime("%FT%T.log"))
        if not os.path.exists(os.path.dirname(logfile)):
            os.makedirs(os.path.dirname(logfile))
        scrapy_proc = ScrapyProcessProtocol(self, domain, logfile, spider_settings)

        args = [sys.executable, sys.argv[0], 'crawl', domain]
        proc = reactor.spawnProcess(scrapy_proc, sys.executable, args=args, env=scrapy_proc.env)
        self.running[domain] = scrapy_proc


