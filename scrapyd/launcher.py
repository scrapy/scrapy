import sys, os
from shutil import copyfileobj
from tempfile import mkstemp
from datetime import datetime

from twisted.internet import reactor, defer, protocol, error
from twisted.application.service import Service
from twisted.python import log

from scrapy.utils.py26 import cpu_count
from scrapy.utils.python import stringify_dict
from scrapyd.utils import get_crawl_args
from .interfaces import IPoller, IEggStorage, IEnvironment

class Launcher(Service):

    name = 'launcher'

    def __init__(self, config, app):
        self.processes = {}
        self.max_proc = config.getint('max_proc', 0)
        if not self.max_proc:
            self.max_proc = cpu_count() * config.getint('max_proc_per_cpu', 4)
        self.egg_runner = config.get('egg_runner', 'scrapyd.eggrunner')
        self.app = app

    def startService(self):
        for slot in range(self.max_proc):
            self._wait_for_project(slot)
        log.msg("%s started: max_proc=%r, egg_runner=%r" % (self.parent.name, \
            self.max_proc, self.egg_runner), system="Launcher")

    def _wait_for_project(self, slot):
        poller = self.app.getComponent(IPoller)
        poller.next().addCallback(self._spawn_process, slot)

    def _get_eggpath(self, project):
        eggstorage = self.app.getComponent(IEggStorage)
        version, eggf = eggstorage.get(project)
        if eggf is None:
            return
        prefix = '%s-%s-' % (project, version)
        fd, eggpath = mkstemp(prefix=prefix, suffix='.egg')
        lf = os.fdopen(fd, 'wb')
        copyfileobj(eggf, lf)
        lf.close()
        return eggpath

    def _spawn_process(self, message, slot):
        msg = stringify_dict(message, keys_only=False)
        project = msg['_project']
        eggpath = self._get_eggpath(project)
        args = [sys.executable, '-m', self.egg_runner, 'crawl']
        args += get_crawl_args(msg)
        e = self.app.getComponent(IEnvironment)
        env = e.get_environment(msg, slot, eggpath)
        env = stringify_dict(env, keys_only=False)
        pp = ScrapyProcessProtocol(eggpath, slot, project, msg['_spider'], \
            msg['_job'], env)
        pp.deferred.addBoth(self._process_finished, eggpath, slot)
        reactor.spawnProcess(pp, sys.executable, args=args, env=env)
        self.processes[slot] = pp

    def _process_finished(self, _, eggpath, slot):
        if eggpath:
            os.remove(eggpath)
        self.processes.pop(slot)
        self._wait_for_project(slot)


class ScrapyProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, eggfile, slot, project, spider, job, env):
        self.eggfile = eggfile
        self.slot = slot
        self.pid = None
        self.project = project
        self.spider = spider
        self.job = job
        self.start_time = datetime.now()
        self.env = env
        self.logfile = env['SCRAPY_LOG_FILE']
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
        msg += "project=%r spider=%r job=%r pid=%r egg=%r log=%r" % (self.project, \
            self.spider, self.job, self.pid, self.eggfile, self.logfile)
        log.msg(msg, system="Launcher")
