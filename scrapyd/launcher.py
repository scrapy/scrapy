import sys, os
from shutil import copyfileobj
from tempfile import mkstemp

from twisted.internet import reactor, defer, protocol, error
from twisted.application.service import Service
from twisted.python import log

from scrapy.utils.py26 import cpu_count
from .interfaces import IPoller, IEggStorage, IEnvironment

class Launcher(Service):

    def __init__(self, config, app):
        self.max_proc = config.getint('max_proc', 0) or cpu_count()
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
        prefix = '%s-%s-' % (project, version)
        fd, eggpath = mkstemp(prefix=prefix, suffix='.egg')
        lf = os.fdopen(fd, 'wb')
        copyfileobj(eggf, lf)
        lf.close()
        return eggpath

    def _spawn_process(self, message, slot):
        project = message['project']
        eggpath = self._get_eggpath(project)
        args = [sys.executable, '-m', self.egg_runner, eggpath, 'crawl']
        e = self.app.getComponent(IEnvironment)
        env = e.get_environment(message, slot)
        pp = ScrapyProcessProtocol(eggpath, slot)
        pp.deferred.addBoth(self._process_finished, eggpath, slot)
        reactor.spawnProcess(pp, sys.executable, args=args, env=env)

    def _process_finished(self, _, eggpath, slot):
        os.remove(eggpath)
        self._wait_for_project(slot)


class ScrapyProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, eggfile, slot):
        self.eggfile = eggfile
        self.slot = slot
        self.pid = None
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
        msg += "slot=%r pid=%r egg=%r" % (self.slot, self.pid, self.eggfile)
        log.msg(msg, system="Launcher")
