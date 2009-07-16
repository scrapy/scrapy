"""
MemoryDebugger extension

See documentation in docs/ref/extensions.rst
"""

import pprint
import gc
import socket

import libxml2
from scrapy.xlib.pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.exceptions import NotConfigured
from scrapy.mail import MailSender
from scrapy.extension import extensions
from scrapy.conf import settings

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
        self.print_or_send_report(report)

    def collect_figures(self):
        libxml2.cleanupParser()
        gc.collect()

        figures = []
        if 'MemoryUsage' in extensions.enabled:
            memusage = extensions.enabled['MemoryUsage']
            memusage.update()
            figures.append(("Memory usage at startup", int(memusage.data['startup']/1024/1024), "Mb"))
            figures.append(("Maximum memory usage", int(memusage.data['max']/1024/1024), "Mb"))
            figures.append(("Memory usage at shutdown", int(memusage.virtual/1024/1024), "Mb"))
        figures.append(("Objects in gc.garbage", len(gc.garbage), ""))
        figures.append(("libxml2 memory leak", libxml2.debugMemory(1), "bytes"))
        return figures

    def create_report(self, figures):
        s = ""
        s += "SCRAPY MEMORY DEBUGGER RESULTS\n\n"
        for f in figures:
            s += "%-30s : %s %s\n" % f
        return s

    def print_or_send_report(self, report):
        if self.rcpts:
            self.mail.send(self.rcpts, "Scrapy Memory Debugger results at %s" % socket.gethostname(), report)
        print report
