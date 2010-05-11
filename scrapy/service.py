import sys, os

from twisted.python import log
from twisted.internet import reactor, protocol, error
from twisted.application.service import Service

from scrapy.utils.py26 import cpu_count
from scrapy.conf import settings


class ScrapyService(Service):

    def startService(self):
        reactor.callWhenRunning(self.start_processes)

    def start_processes(self):
        for i in range(cpu_count()):
            self.start_process(i+1)

    def start_process(self, id):
        args = [sys.executable, '-m', 'scrapy.service']
        env = os.environ.copy()
        self.set_log_file(env, id)
        pp = ScrapyProcessProtocol(self, id, env.get('SCRAPY_LOG_FILE'))
        reactor.spawnProcess(pp, sys.executable, args=args, env=env)

    def set_log_file(self, env, suffix):
        logfile = settings['LOG_FILE']
        if logfile:
            file, ext = os.path.splitext(logfile)
            env['SCRAPY_LOG_FILE'] = "%s-%s%s" % (file, suffix, ext)


class ScrapyProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, service, id, logfile):
        self.service = service
        self.id = id
        self.logfile = logfile
        self.pid = None

    def connectionMade(self):
        self.pid = self.transport.pid
        log.msg("Process %r started: pid=%r logfile=%r" % (self.id, self.pid, \
            self.logfile))

    def processEnded(self, status):
        if isinstance(status.value, error.ProcessDone):
            log.msg("Process %r finished: pid=%r logfile=%r" % (self.id, \
                self.pid, self.logfile))
        else:
            log.msg("Process %r died: exitstatus=%r pid=%r logfile=%r" % \
                (self.id, status.value.exitCode, self.pid, self.logfile))
        reactor.callLater(5, self.service.start_process, self.id)


if __name__ == '__main__':
    from scrapy.core.manager import scrapymanager
    scrapymanager.configure()
    scrapymanager.start(keep_alive=True)
