"""
MemoryUsage extension

See documentation in docs/ref/extensions.rst
"""

import sys
import os
import pprint
import socket

from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy import log
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.stats import stats
from scrapy.conf import settings

class MemoryUsage(object):
    
    _proc_status = '/proc/%d/status' % os.getpid()
    _scale = {'kB': 1024.0, 'mB': 1024.0*1024.0,
              'KB': 1024.0, 'MB': 1024.0*1024.0}

    def __init__(self):
        if not settings.getbool('MEMUSAGE_ENABLED'):
            raise NotConfigured
        if sys.platform != 'linux2':
            raise NotConfigured("MemoryUsage extension is only available on Linux")

        self.warned = False

        self.data = {}
        self.data['startup'] = 0
        self.data['max'] = 0

        scrapyengine.addtask(self.update, 60.0, now=True)

        self.notify_mails = settings.getlist('MEMUSAGE_NOTIFY')
        self.limit = settings.getint('MEMUSAGE_LIMIT_MB')*1024*1024
        self.warning = settings.getint('MEMUSAGE_WARNING_MB')*1024*1024
        self.report = settings.getbool('MEMUSAGE_REPORT')

        if self.limit:
            scrapyengine.addtask(self._check_limit, 60.0, now=True)
        if self.warning:
            scrapyengine.addtask(self._check_warning, 60.0, now=True)

        self.mail = MailSender()

        dispatcher.connect(self.engine_started, signal=signals.engine_started)


    @property
    def virtual(self):
        return self._vmvalue('VmSize:')

    @property
    def resident(self):
        return self._vmvalue('VmRSS:')
        
    @property
    def stacksize(self):
        return self._vmvalue('VmStk:')

    def engine_started(self):
        self.data['startup'] = self.virtual

    def update(self):
        if self.virtual > self.data['max']:
            self.data['max'] = self.virtual

    def _vmvalue(self, VmKey):
        # get pseudo file  /proc/<pid>/status
        try:
            t = open(self._proc_status)
            v = t.read()
            t.close()
        except:
            return 0.0  # non-Linux?
        # get VmKey line e.g. 'VmRSS:  9999  kB\n ...'
        i = v.index(VmKey)
        v = v[i:].split(None, 3)  # whitespace
        if len(v) < 3:
            return 0.0  # invalid format?
        # convert Vm value to bytes
        return float(v[1]) * self._scale[v[2]]

    def _check_limit(self):
        if self.virtual > self.limit:
            mem = self.limit/1024/1024
            log.msg("Memory usage exceeded %dM. Shutting down Scrapy..." % mem, level=log.ERROR)
            if self.notify_mails:
                subj = "%s terminated: memory usage exceeded %dM at %s" % (settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
            scrapymanager.stop()

    def _check_warning(self):
        if self.warned: # warn only once
            return
        if self.virtual > self.warning:
            mem = self.warning/1024/1024
            log.msg("Memory usage reached %dM" % mem, level=log.WARNING)
            if self.notify_mails:
                subj = "%s warning: memory usage reached %dM at %s" % (settings['BOT_NAME'], mem, socket.gethostname())
                self._send_report(self.notify_mails, subj)
            self.warned = True

    def _send_report(self, rcpts, subject):
        """send notification mail with some additional useful info"""
        s = "Memory usage at engine startup : %dM\r\n" % (self.data['startup']/1024/1024)
        s += "Maximum memory usage           : %dM\r\n" % (self.data['max']/1024/1024)
        s += "Current memory usage           : %dM\r\n" % (self.virtual/1024/1024)

        s += "ENGINE STATUS ------------------------------------------------------- \r\n"
        s += "\r\n"
        s += scrapyengine.getstatus()
        s += "\r\n"

        if stats:
            s += "SCRAPING STATS ------------------------------------------------------ \r\n"
            s += "\r\n"
            s += pprint.pformat(stats)
        self.mail.send(rcpts, subject, s)
