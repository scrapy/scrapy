import sys
import os
import time
import datetime

from twisted.internet import protocol, reactor

from scrapy.core import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class ScrapyProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, procman, domain, logfile=None):
        self.procman = procman
        self.domain = domain
        self.logfile = logfile
        self.start_time = datetime.datetime.utcnow()
        self.status = "starting"
        self.pid = -1

    def __str__(self):
        return "<ScrapyProcess domain=%s, pid=%s, status=%s>" % (self.domain, self.pid, self.status)

    def connectionMade(self):
        self.pid = self.transport.pid
        log.msg("ClusterWorker: started domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        self.transport.closeStdin()
        self.status = "running"

    def processEnded(self, status_object):
        log.msg("ClusterWorker: finished domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        del self.procman.running[self.domain]
        self.procman.next_pending()
    

class ClusterWorker(object):

    def __init__(self):
        if not settings.getbool('CLUSTER_WORKER_ENABLED'):
            raise NotConfigured

        self.maxproc = settings.getint('CLUSTER_WORKER_MAXPROC')
        self.logdir = settings['CLUSTER_WORKER_LOGDIR']
        self.running = {}
        self.pending = []

    def schedule(self, domain):
        """Schedule new domain to be crawled in a separate processes"""

        if len(self.running) < self.maxproc and domain not in self.running:
            self._run(domain)
        else:
            self.pending.append(domain)

    def stop(self, domain):
        """Stop running domain. For removing pending (not yet started) domains
        use remove() instead"""

        if domain in self.running:
            proc = self.running[domain]
            log.msg("ClusterWorker: Sending shutdown signal to domain=%s, pid=%d" % (domain, proc.pid))
            proc.transport.signalProcess('INT')
            proc.status = "closing"

    def remove(self, domain):
        """Remove all scheduled instances of the given domain (if it hasn't
        started yet). Otherwise use stop()"""

        while domain in self.pending:
            self.pending.remove(domain)

    def next_pending(self):
        """Run the next domain in the pending list, which is not already running"""

        if len(self.running) >= self.maxproc:
            return
        for domain in self.pending:
            if domain not in self.running:
                self._run(domain)
                self.pending.remove(domain)
                return

    def _run(self, domain):
        """Spawn process to run the given domain. Don't call this method
        directly. Instead use schedule()."""

        logfile = os.path.join(self.logdir, domain, time.strftime("%FT%T.log"))
        if not os.path.exists(os.path.dirname(logfile)):
            os.makedirs(os.path.dirname(logfile))
        scrapy_proc = ScrapyProcessProtocol(self, domain, logfile)
        env = {'SCRAPY_LOGFILE': logfile}
        args = [sys.executable, sys.argv[0], 'crawl', domain]
        proc = reactor.spawnProcess(scrapy_proc, sys.executable, args=args, env=env)
        self.running[domain] = scrapy_proc


