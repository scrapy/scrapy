import sys
from datetime import datetime

from twisted.internet import reactor, defer, protocol, error
from twisted.application.service import Service
from twisted.python import log

from scrapy.utils.py26 import cpu_count
from scrapy.utils.python import stringify_dict
from scrapyd.utils import get_crawl_args
from .interfaces import IPoller, IEnvironment

class Launcher(Service):

    name = 'launcher'

    def __init__(self, config, app):
        self.processes = {}
        self.finished = []
        self.finished_to_keep = config.getint('finished_to_keep', 100)
        self.max_proc = config.getint('max_proc', 0)
        if not self.max_proc:
            self.max_proc = cpu_count() * config.getint('max_proc_per_cpu', 4)
        self.runner = config.get('runner', 'scrapyd.runner')
        self.app = app

    def startService(self):
        for slot in range(self.max_proc):
            self._wait_for_project(slot)
        log.msg("%s started: max_proc=%r, runner=%r" % (self.parent.name, \
            self.max_proc, self.runner), system="Launcher")

    def _wait_for_project(self, slot):
        poller = self.app.getComponent(IPoller)
        poller.next().addCallback(self._spawn_process, slot)

    def _spawn_process(self, message, slot):
        msg = stringify_dict(message, keys_only=False)
        project = msg['_project']
        args = [sys.executable, '-m', self.runner, 'crawl']
        args += get_crawl_args(msg)
        e = self.app.getComponent(IEnvironment)
        env = e.get_environment(msg, slot)
        env = stringify_dict(env, keys_only=False)
        pp = ScrapyProcessProtocol(slot, project, msg['_spider'], \
            msg['_job'], env)
        pp.deferred.addBoth(self._process_finished, slot)
        reactor.spawnProcess(pp, sys.executable, args=args, env=env)
        self.processes[slot] = pp

    def _process_finished(self, _, slot):
        process = self.processes.pop(slot)
        process.end_time = datetime.now()
        self.finished.append(process)
        del self.finished[:-self.finished_to_keep] # keep last 100 finished jobs
        self._wait_for_project(slot)


class ScrapyProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, slot, project, spider, job, env):
        self.slot = slot
        self.pid = None
        self.project = project
        self.spider = spider
        self.job = job
        self.start_time = datetime.now()
        self.end_time = None
        self.env = env
        self.logfile = env['SCRAPY_LOG_FILE']
        self.itemsfile = env['SCRAPY_FEED_URI']
        self.deferred = defer.Deferred()

    def outReceived(self, data):
        log.msg(data.rstrip(), system="Launcher,%d/stdout" % self.pid)

    def errReceived(self, data):
        log.msg(data.rstrip(), system="Launcher,%d/stderr" % self.pid)

    def connectionMade(self):
        self.pid = self.transport.pid
        self.log("Process started: ")

    def processEnded(self, status):
        if isinstance(status.value, error.ProcessDone):
            self.log("Process finished: ")
        else:
            self.log("Process died: exitstatus=%r " % status.value.exitCode)
        self.deferred.callback(self)

    def log(self, msg):
        msg += "project=%r spider=%r job=%r pid=%r log=%r items=%r" % (self.project, \
            self.spider, self.job, self.pid, self.logfile, self.itemsfile)
        log.msg(msg, system="Launcher")
