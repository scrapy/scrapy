import sys, os, time, datetime, pickle

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
        self.env = {}
        #We conserve original setting format for info purposes (avoid lots of unnecesary "SCRAPY_")
        self.scrapy_settings = spider_settings or {}
        self.scrapy_settings.update({'LOGFILE': self.logfile, 'CLUSTER_WORKER_ENABLED': '0', 'WEBCONSOLE_ENABLED': '0'})
        pickled_settings = pickle.dumps(self.scrapy_settings)
        self.env["SCRAPY_PICKLED_SETTINGS"] = pickled_settings
        self.env["PYTHONPATH"] = ":".join(sys.path)#this is need so this crawl process knows where to locate local_scrapy_settings.

    def __str__(self):
        return "<ScrapyProcess domain=%s, pid=%s, status=%s>" % (self.domain, self.pid, self.status)

    def as_dict(self):
        return {"domain": self.domain, "pid": self.pid, "status": self.status, "settings": self.scrapy_settings, "logfile": self.logfile, "starttime": self.start_time}

    def connectionMade(self):
        self.pid = self.transport.pid
        log.msg("ClusterWorker: started domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        self.transport.closeStdin()
        self.status = "running"

    def processEnded(self, status_object):
        log.msg("ClusterWorker: finished domain=%s, pid=%d, log=%s" % (self.domain, self.pid, self.logfile))
        del self.procman.running[self.domain]

class ClusterWorker(pb.Root):

    def __init__(self):
        if not settings.getbool('CLUSTER_WORKER_ENABLED'):
            raise NotConfigured

        self.maxproc = settings.getint('CLUSTER_WORKER_MAXPROC')
        self.logdir = settings['CLUSTER_LOGDIR']
        self.running = {}
        self.starttime = time.time()
        port = settings.getint('CLUSTER_WORKER_PORT')
        scrapyengine.listenTCP(port, pb.PBServerFactory(self))

    def remote_stop(self, domain):
        """Stop running domain."""
        if domain in self.running:
            proc = self.running[domain]
            log.msg("ClusterWorker: Sending shutdown signal to domain=%s, pid=%d" % (domain, proc.pid))
            proc.transport.signalProcess('INT')
            proc.status = "closing"
            return self.status(0, "Stopped process %s" % proc)
        else:
            return self.status(1, "%s: domain not running." % domain)

    def remote_status(self):
        return self.status()
    
    def status(self, rcode=0, rstring=None):
        status = {}
        status["running"] = [ self.running[k].as_dict() for k in self.running.keys() ]
        status["starttime"] = self.starttime
        status["timestamp"] = time.time()
        status["maxproc"] = self.maxproc
        status["loadavg"] = os.getloadavg()
        status["logdir"] = self.logdir
        status["callresponse"] = (rcode, rstring) if rstring else (0, "Status Response.")
        return status

    def remote_run(self, domain, spider_settings=None):
        """Spawn process to run the given domain."""
        if len(self.running) < self.maxproc:
            logfile = os.path.join(self.logdir, domain, time.strftime("%FT%T.log"))
            if not os.path.exists(os.path.dirname(logfile)):
                os.makedirs(os.path.dirname(logfile))
            scrapy_proc = ScrapyProcessProtocol(self, domain, logfile, spider_settings)
            args = [sys.executable, sys.argv[0], 'crawl', domain]
            self.running[domain] = scrapy_proc
            try:
                import pysvn
                c=pysvn.Client()
                r = c.update(settings["CLUSTER_WORKER_SVNWORKDIR"] or ".")
                log.msg("Updated to revision %s." %r[0].number )
            except:
                pass
            proc = reactor.spawnProcess(scrapy_proc, sys.executable, args=args, env=scrapy_proc.env)
            return self.status(0, "Started process %s." % scrapy_proc)
        return self.status(1, "No free slot to run another process.")
