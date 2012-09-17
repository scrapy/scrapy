"""
Extensions for debugging Scrapy

See documentation in docs/topics/extensions.rst
"""

import sys
import signal
import traceback
import threading
from pdb import Pdb

from scrapy.utils.engine import format_engine_status
from scrapy.utils.trackref import format_live_refs
from scrapy import log


class StackTraceDump(object):

    def __init__(self, crawler=None):
        self.crawler = crawler
        try:
            signal.signal(signal.SIGUSR2, self.dump_stacktrace)
            signal.signal(signal.SIGQUIT, self.dump_stacktrace)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def dump_stacktrace(self, signum, frame):
        stackdumps = self._thread_stacks()
        enginestatus = format_engine_status(self.crawler.engine)
        liverefs = format_live_refs()
        msg = "Dumping stack trace and engine status" \
            "\n{0}\n{1}\n{2}".format(enginestatus, liverefs, stackdumps)
        log.msg(msg)

    def _thread_stacks(self):
        id2name = dict((th.ident, th.name) for th in threading.enumerate())
        dumps = ''
        for id_, frame in sys._current_frames().items():
            name = id2name.get(id_, '')
            dump = ''.join(traceback.format_stack(frame))
            dumps += "# Thread: {0}({1})\n{2}\n".format(name, id_, dump)
        return dumps


class Debugger(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self._enter_debugger)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def _enter_debugger(self, signum, frame):
        Pdb().set_trace(frame.f_back)
