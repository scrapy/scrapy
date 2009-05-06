"""
Extensions for debugging Scrapy 

See documentation in docs/ref/extensions.rst
"""
import signal
import traceback

class StackTraceDump(object):
    def __init__(self):
        try:
            signal.signal(signal.SIGUSR1, self.dump_stacktrace)
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def dump_stacktrace(self, signum, frame):
        print "Got signal. Dumping stack trace..."
        traceback.print_stack(frame)
