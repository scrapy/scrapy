"""
MemoryDebugger extension

See documentation in docs/topics/extensions.rst
"""

import os
import gc
import socket

from scrapy.xlib.pydispatch import dispatcher

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.utils.trackref import format_live_refs
from scrapy.conf import settings
from scrapy import log

class MemoryDebugger(object):

    def __init__(self):
        try:
            import libxml2
            self.libxml2 = libxml2
        except ImportError:
            self.libxml2 = None
        if not settings.getbool('MEMDEBUG_ENABLED'):
            raise NotConfigured

        self.mail = MailSender()
        self.rcpts = settings.getlist('MEMDEBUG_NOTIFY')

        dispatcher.connect(self.engine_started, signals.engine_started)
        dispatcher.connect(self.engine_stopped, signals.engine_stopped)

    def engine_started(self):
        if self.libxml2:
            self.libxml2.debugMemory(1)

    def engine_stopped(self):
        figures = self.collect_figures()
        report = self.create_report(figures)
        self.log_or_send_report(report)

    def collect_figures(self):
        gc.collect()

        figures = []
        figures.append(("Objects in gc.garbage", len(gc.garbage), ""))
        if self.libxml2:
            self.libxml2.cleanupParser()
            figures.append(("libxml2 memory leak", self.libxml2.debugMemory(1), "bytes"))
        return figures

    def create_report(self, figures):
        s = ""
        s += "SCRAPY MEMORY DEBUGGER RESULTS\n\n"
        for f in figures:
            s += "%-30s : %d %s\n" % f
        if settings.getbool('TRACK_REFS'):
            s += os.linesep
            s += format_live_refs()
        return s

    def log_or_send_report(self, report):
        if self.rcpts:
            self.mail.send(self.rcpts, "Scrapy Memory Debugger results at %s" % \
                socket.gethostname(), report)
        log.msg(report)
