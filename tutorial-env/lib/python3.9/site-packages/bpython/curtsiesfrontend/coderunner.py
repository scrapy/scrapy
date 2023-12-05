"""For running Python code that could interrupt itself at any time in order to,
for example, ask for a read on stdin, or a write on stdout

The CodeRunner spawns a greenlet to run code in, and that code can suspend its
own execution to ask the main greenlet to refresh the display or get
information.

Greenlets are basically threads that can explicitly switch control to each
other.  You can replace the word "greenlet" with "thread" in these docs if that
makes more sense to you.
"""

import code
import greenlet
import logging
import signal

from curtsies.input import is_main_thread

logger = logging.getLogger(__name__)


class SigintHappened:
    """If this class is returned, a SIGINT happened while the main greenlet"""


class SystemExitFromCodeRunner(SystemExit):
    """If this class is returned, a SystemExit happened while in the code
    greenlet"""


class RequestFromCodeRunner:
    """Message from the code runner"""


class Wait(RequestFromCodeRunner):
    """Running code would like the main loop to run for a bit"""


class Refresh(RequestFromCodeRunner):
    """Running code would like the main loop to refresh the display"""


class Done(RequestFromCodeRunner):
    """Running code is done running"""


class Unfinished(RequestFromCodeRunner):
    """Source code wasn't executed because it wasn't fully formed"""


class SystemExitRequest(RequestFromCodeRunner):
    """Running code raised a SystemExit"""

    def __init__(self, args):
        self.args = args


class CodeRunner:
    """Runs user code in an interpreter.

    Running code requests a refresh by calling
    request_from_main_context(force_refresh=True), which
    suspends execution of the code and switches back to the main greenlet

    After load_code() is called with the source code to be run,
    the run_code() method should be called to start running the code.
    The running code may request screen refreshes and user input
    by calling request_from_main_context.
    When this are called, the running source code cedes
    control, and the current run_code() method call returns.

    The return value of run_code() determines whether the method ought
    to be called again to complete execution of the source code.

    Once the screen refresh has occurred or the requested user input
    has been gathered, run_code() should be called again, passing in any
    requested user input. This continues until run_code returns Done.

    The code greenlet is responsible for telling the main greenlet
    what it wants returned in the next run_code call - CodeRunner
    just passes whatever is passed in to run_code(for_code) to the
    code greenlet
    """

    def __init__(self, interp=None, request_refresh=lambda: None):
        """
        interp is an interpreter object to use. By default a new one is
        created.

        request_refresh is a function that will be called each time the running
        code asks for a refresh - to, for example, update the screen.
        """
        self.interp = interp or code.InteractiveInterpreter()
        self.source = None
        self.main_context = greenlet.getcurrent()
        self.code_context = None
        self.request_refresh = request_refresh
        # waiting for response from main thread
        self.code_is_waiting = False
        # sigint happened while in main thread
        self.sigint_happened_in_main_context = False
        self.orig_sigint_handler = None

    @property
    def running(self):
        """Returns greenlet if code has been loaded greenlet has been
        started"""
        return self.source and self.code_context

    def load_code(self, source):
        """Prep code to be run"""
        assert self.source is None, (
            "you shouldn't load code when some is " "already running"
        )
        self.source = source
        self.code_context = None

    def _unload_code(self):
        """Called when done running code"""
        self.source = None
        self.code_context = None
        self.code_is_waiting = False

    def run_code(self, for_code=None):
        """Returns Truthy values if code finishes, False otherwise

        if for_code is provided, send that value to the code greenlet
        if source code is complete, returns "done"
        if source code is incomplete, returns "unfinished"
        """
        if self.code_context is None:
            assert self.source is not None
            self.code_context = greenlet.greenlet(self._blocking_run_code)
            if is_main_thread():
                self.orig_sigint_handler = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT, self.sigint_handler)
            request = self.code_context.switch()
        else:
            assert self.code_is_waiting
            self.code_is_waiting = False
            if is_main_thread():
                signal.signal(signal.SIGINT, self.sigint_handler)
            if self.sigint_happened_in_main_context:
                self.sigint_happened_in_main_context = False
                request = self.code_context.switch(SigintHappened)
            else:
                request = self.code_context.switch(for_code)

        logger.debug("request received from code was %r", request)
        if not isinstance(request, RequestFromCodeRunner):
            raise ValueError(
                "Not a valid value from code greenlet: %r" % request
            )
        if isinstance(request, (Wait, Refresh)):
            self.code_is_waiting = True
            if isinstance(request, Refresh):
                self.request_refresh()
            return False
        elif isinstance(request, (Done, Unfinished)):
            self._unload_code()
            if is_main_thread():
                signal.signal(signal.SIGINT, self.orig_sigint_handler)
            self.orig_sigint_handler = None
            return request
        elif isinstance(request, SystemExitRequest):
            self._unload_code()
            raise SystemExitFromCodeRunner(request.args)

    def sigint_handler(self, *args):
        """SIGINT handler to use while code is running or request being
        fulfilled"""
        if greenlet.getcurrent() is self.code_context:
            logger.debug("sigint while running user code!")
            raise KeyboardInterrupt()
        else:
            logger.debug(
                "sigint while fulfilling code request sigint handler "
                "running!"
            )
            self.sigint_happened_in_main_context = True

    def _blocking_run_code(self):
        try:
            unfinished = self.interp.runsource(self.source)
        except SystemExit as e:
            return SystemExitRequest(*e.args)
        return Unfinished() if unfinished else Done()

    def request_from_main_context(self, force_refresh=False):
        """Return the argument passed in to .run_code(for_code)

        Nothing means calls to run_code must be... ???
        """
        if force_refresh:
            value = self.main_context.switch(Refresh())
        else:
            value = self.main_context.switch(Wait())
        if value is SigintHappened:
            raise KeyboardInterrupt()
        return value


class FakeOutput:
    def __init__(self, coderunner, on_write, real_fileobj):
        """Fakes sys.stdout or sys.stderr

        on_write should always take unicode

        fileno should be the fileno that on_write will
                output to (e.g. 1 for standard output).
        """
        self.coderunner = coderunner
        self.on_write = on_write
        self._real_fileobj = real_fileobj

    def write(self, s, *args, **kwargs):
        self.on_write(s, *args, **kwargs)
        return self.coderunner.request_from_main_context(force_refresh=True)

    # Some applications which use curses require that sys.stdout
    # have a method called fileno. One example is pwntools. This
    # is not a widespread issue, but is annoying.
    def fileno(self):
        return self._real_fileobj.fileno()

    def writelines(self, l):
        for s in l:
            self.write(s)

    def flush(self):
        pass

    def isatty(self):
        return True

    @property
    def encoding(self):
        return self._real_fileobj.encoding
