"""
MemoryUsage extension

See documentation in docs/topics/extensions.rst
"""

import os
import socket

from twisted.internet import task

from scrapy.xlib.pydispatch import dispatcher
from scrapy.core import signals
from scrapy import log
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.conf import settings
from scrapy.stats import stats
from scrapy.utils.memory import get_vmvalue_from_procfs

class MemoryUsage(object):
    
    def __init__(self):
        if not settings.getbool('MEMUSAGE_ENABLED'):
            raise NotConfigured
        if not os.path.exists('/proc'):
            raise NotConfigured
        self.warned = False

        self.notify_mails = settings.getlist('MEMUSAGE_NOTIFY')
        self.limit = settings.getint('MEMUSAGE_LIMIT_MB')*1024*1024
        self.warning = settings.getint('MEMUSAGE_WARNING_MB')*1024*1024
        self.report = settings.getbool('MEMUSAGE_REPORT')
        self.mail = MailSender()
        dispatcher.connect(self.engine_started, signal=signals.engine_started)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)


    @property
    def virtual(self):
        return get_vmvalue_from_procfs('VmSize')

    def engine_started(self):
        stats.set_value('memusage/startup', self.virtual)
        self.tasks = []
        tsk = task.LoopingCall(self.update)
        self.tasks.append(tsk)
        tsk.start(60.0, now=True)
        if self.limit:
            tsk = task.LoopingCall(self._check_limit)
            self.tasks.append(tsk)
            tsk.start(60.0, now=True)
        if self.warning:
            tsk = task.LoopingCall(self._check_warning)
            self.tasks.append(tsk)
            tsk.start(60.0, now=True)

    def engine_stopped(self):
        for tsk in self.tasks:
            if tsk.running:
                tsk.stop()

    def update(self):
        stats.max_value('memusage/max', self.virtual)

    def _check_limit(self):
        if self.virtual > self.limit:
            stats.set_value('memusage/limit_reached', 1)
            mem = self.limit/1024/1024
            log.msg("Memory usage exceeded %dM. Shutting down Scrapy..." % mem, level=log.ERROR)
            if self.notify_mails:
                subj = "%s terminated: memory usage exceeded %dM at %s" % \
                        (settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
                stats.set_value('memusage/limit_notified', 1)
            scrapymanager.stop()

    def _check_warning(self):
        if self.warned: # warn only once
            return
        if self.virtual > self.warning:
            stats.set_value('memusage/warning_reached', 1)
            mem = self.warning/1024/1024
            log.msg("Memory usage reached %dM" % mem, level=log.WARNING)
            if self.notify_mails:
                subj = "%s warning: memory usage reached %dM at %s" % \
                        (settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
                stats.set_value('memusage/warning_notified', 1)
            self.warned = True

    def _send_report(self, rcpts, subject):
        """send notification mail with some additional useful info"""
        s = "Memory usage at engine startup : %dM\r\n" % (stats.get_value('memusage/startup')/1024/1024)
        s += "Maximum memory usage           : %dM\r\n" % (stats.get_value('memusage/max')/1024/1024)
        s += "Current memory usage           : %dM\r\n" % (self.virtual/1024/1024)

        s += "ENGINE STATUS ------------------------------------------------------- \r\n"
        s += "\r\n"
        s += scrapyengine.getstatus()
        s += "\r\n"
        self.mail.send(rcpts, subject, s)
