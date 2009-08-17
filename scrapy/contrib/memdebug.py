"""
MemoryDebugger extension

See documentation in docs/ref/extensions.rst
"""

import gc
import socket

import libxml2
from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.stats import stats
from scrapy.conf import settings
from scrapy.utils.memory import get_vmvalue_from_procfs
from scrapy import log

class MemoryDebugger(object):

    def __init__(self):
        if not settings.getbool('MEMDEBUG_ENABLED'):
            raise NotConfigured

        self.mail = MailSender()
        self.rcpts = settings.getlist('MEMDEBUG_NOTIFY')

        dispatcher.connect(self.engine_started, signals.engine_started)
        dispatcher.connect(self.engine_stopped, signals.engine_stopped)

    def engine_started(self):
        libxml2.debugMemory(1)

    def engine_stopped(self):
        figures = self.collect_figures()
        report = self.create_report(figures)
        self.log_or_send_report(report)

    def collect_figures(self):
        libxml2.cleanupParser()
        gc.collect()

        figures = []
        if stats.get_value('memusage/startup'):
            figures.append(("Memory usage at startup", \
                stats.get_value('memusage/startup')/1024/1024, "Mb"))
            figures.append(("Maximum memory usage", \
                stats.get_value('memusage/max')/1024/1024, "Mb"))
            figures.append(("Memory usage at shutdown", \
                get_vmvalue_from_procfs()/1024/1024, "Mb"))
        figures.append(("Objects in gc.garbage", len(gc.garbage), ""))
        figures.append(("libxml2 memory leak", libxml2.debugMemory(1), "bytes"))
        return figures

    def create_report(self, figures):
        s = ""
        s += "SCRAPY MEMORY DEBUGGER RESULTS\n\n"
        for f in figures:
            s += "%-30s : %d %s\n" % f
        return s

    def log_or_send_report(self, report):
        if self.rcpts:
            self.mail.send(self.rcpts, "Scrapy Memory Debugger results at %s" % \
                socket.gethostname(), report)
        log.msg(report)
