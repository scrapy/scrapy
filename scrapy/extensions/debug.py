"""
Extensions for debugging Scrapy

See documentation in docs/topics/extensions.rst
"""

import sys
import signal
import logging
import traceback
import threading
from pdb import Pdb

from scrapy.utils.engine import format_engine_status
from scrapy.utils.trackref import format_live_refs

logger = logging.getLogger(__name__)


class StackTraceDump(object):
    """Dumps information about the running process when a `SIGQUIT`_ or `SIGUSR2`_
    signal is received. The information dumped is the following:

    1. engine status (using ``scrapy.utils.engine.get_engine_status()``)
    2. live references (see :ref:`topics-leaks-trackrefs`)
    3. stack trace of all threads

    After the stack trace and engine status is dumped, the Scrapy process continues
    running normally.

    This extension only works on POSIX-compliant platforms (ie. not Windows),
    because the `SIGQUIT`_ and `SIGUSR2`_ signals are not available on Windows.

    There are at least two ways to send Scrapy the `SIGQUIT`_ signal:

    1. By pressing Ctrl-\ while a Scrapy process is running (Linux only?)
    2. By running this command (assuming ``<pid>`` is the process id of the Scrapy
       process)::

        kill -QUIT <pid>

    .. _SIGUSR2: https://en.wikipedia.org/wiki/SIGUSR1_and_SIGUSR2
    .. _SIGQUIT: https://en.wikipedia.org/wiki/SIGQUIT
    """

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
        log_args = {
            'stackdumps': self._thread_stacks(),
            'enginestatus': format_engine_status(self.crawler.engine),
            'liverefs': format_live_refs(),
        }
        logger.info("Dumping stack trace and engine status\n"
                    "%(enginestatus)s\n%(liverefs)s\n%(stackdumps)s",
                    log_args, extra={'crawler': self.crawler})

    def _thread_stacks(self):
        id2name = dict((th.ident, th.name) for th in threading.enumerate())
        dumps = ''
        for id_, frame in sys._current_frames().items():
            name = id2name.get(id_, '')
            dump = ''.join(traceback.format_stack(frame))
            dumps += "# Thread: {0}({1})\n{2}\n".format(name, id_, dump)
        return dumps


class Debugger(object):
    """Invokes a :ref:`Python debugger <debugger>` inside a running Scrapy
    process when a `SIGUSR2`_ signal is received. After the debugger is exited,
    the Scrapy process continues running normally.

    For more info see `Debugging in Python`.

    This extension only works on POSIX-compliant platforms (ie. not Windows).

    .. _Debugging in Python: https://pythonconquerstheuniverse.wordpress.com/2009/09/10/debugging-in-python/
    """

    def __init__(self):
        try:
            signal.signal(signal.SIGUSR2, self._enter_debugger)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def _enter_debugger(self, signum, frame):
        Pdb().set_trace(frame.f_back)
