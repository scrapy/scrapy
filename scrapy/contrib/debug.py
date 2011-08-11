"""
Extensions for debugging Scrapy 

See documentation in docs/topics/extensions.rst
"""

import os
import signal
import traceback
from pdb import Pdb

from scrapy.utils.engine import format_engine_status
from scrapy import log


class StackTraceDump(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self.dump_stacktrace)
            signal.signal(signal.SIGQUIT, self.dump_stacktrace)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def dump_stacktrace(self, signum, frame):
        msg = "Dumping stack trace and engine status" + os.linesep
        msg += "".join(traceback.format_stack(frame))
        msg += os.linesep
        msg += format_engine_status()
        log.msg(msg)


class Debugger(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self._enter_debugger)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def _enter_debugger(self, signum, frame):
        Pdb().set_trace(frame.f_back)
