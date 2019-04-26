from __future__ import absolute_import
import sys
import os

from twisted.internet import reactor, defer, protocol


class ProcessTest(object):

    command = None
    prefix = [sys.executable, '-m', 'scrapy.cmdline']
    cwd = os.getcwd()  # trial chdirs to temp dir

    def execute(self, args, check_code=True, settings=None):
        env = os.environ.copy()
        if settings is not None:
            env['SCRAPY_SETTINGS_MODULE'] = settings
        cmd = self.prefix + [self.command] + list(args)
        pp = TestProcessProtocol()
        pp.deferred.addBoth(self._process_finished, cmd, check_code)
        reactor.spawnProcess(pp, cmd[0], cmd, env=env, path=self.cwd)
        return pp.deferred

    def _process_finished(self, pp, cmd, check_code):
        if pp.exitcode and check_code:
            msg = "process %s exit with code %d" % (cmd, pp.exitcode)
            msg += "\n>>> stdout <<<\n%s" % pp.out
            msg += "\n"
            msg += "\n>>> stderr <<<\n%s" % pp.err
            raise RuntimeError(msg)
        return pp.exitcode, pp.out, pp.err


class TestProcessProtocol(protocol.ProcessProtocol):

    def __init__(self):
        self.deferred = defer.Deferred()
        self.out = b''
        self.err = b''
        self.exitcode = None

    def outReceived(self, data):
        self.out += data

    def errReceived(self, data):
        self.err += data

    def processEnded(self, status):
        self.exitcode = status.value.exitCode
        self.deferred.callback(self)
