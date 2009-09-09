"""
Extensions for debugging Scrapy 

See documentation in docs/topics/extensions.rst
"""

import signal
import traceback
from pdb import Pdb


class StackTraceDump(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self.dump_stacktrace)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def dump_stacktrace(self, signum, frame):
        print "Got signal. Dumping stack trace..."
        traceback.print_stack(frame)


class Debugger(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self._enter_debugger)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def _enter_debugger(self, signum, frame):
        Pdb().set_trace(frame.f_back)
