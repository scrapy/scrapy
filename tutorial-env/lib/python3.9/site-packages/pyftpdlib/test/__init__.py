# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

from __future__ import print_function

import atexit
import contextlib
import functools
import logging
import multiprocessing
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import warnings

import psutil

from pyftpdlib._compat import PY3
from pyftpdlib._compat import FileNotFoundError
from pyftpdlib._compat import getcwdu
from pyftpdlib._compat import super
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.handlers import _import_sendfile
from pyftpdlib.ioloop import IOLoop
from pyftpdlib.servers import FTPServer


try:
    from unittest import mock  # py3
except ImportError:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import mock  # NOQA - requires "pip install mock"


sendfile = _import_sendfile()


# --- platforms

HERE = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
ROOT_DIR = os.path.realpath(os.path.join(HERE, '..', '..'))
PYPY = '__pypy__' in sys.builtin_module_names
# whether we're running this test suite on a Continuous Integration service
APPVEYOR = 'APPVEYOR' in os.environ
GITHUB_ACTIONS = 'GITHUB_ACTIONS' in os.environ or 'CIBUILDWHEEL' in os.environ
CI_TESTING = APPVEYOR or GITHUB_ACTIONS
COVERAGE = 'COVERAGE_RUN' in os.environ
# are we a 64 bit process?
IS_64BIT = sys.maxsize > 2 ** 32
OSX = sys.platform.startswith("darwin")
POSIX = os.name == 'posix'
WINDOWS = os.name == 'nt'
LOG_FMT = "[%(levelname)1.1s t: %(threadName)-15s p: %(processName)-25s "
LOG_FMT += "@%(module)-12s: %(lineno)-4s] %(message)s"


# Attempt to use IP rather than hostname (test suite will run a lot faster)
try:
    HOST = socket.gethostbyname('localhost')
except socket.error:
    HOST = 'localhost'

USER = 'user'
PASSWD = '12345'
HOME = getcwdu()
# Use PID to disambiguate file name for parallel testing.
TESTFN_PREFIX = 'pyftpd-tmp-%s-' % os.getpid()
GLOBAL_TIMEOUT = 2
BUFSIZE = 1024
INTERRUPTED_TRANSF_SIZE = 32768
NO_RETRIES = 5
VERBOSITY = 1 if os.getenv('SILENT') else 2

if CI_TESTING:
    GLOBAL_TIMEOUT *= 3
    NO_RETRIES *= 3


class PyftpdlibTestCase(unittest.TestCase):
    """All test classes inherit from this one."""

    def setUp(self):
        self._test_ctx = {}
        self._test_ctx["threads"] = set(threading.enumerate())

    def tearDown(self):
        if not hasattr(self, "_test_ctx"):
            raise AssertionError("super().setUp() was not called for this "
                                 "test class")
        threads = set(threading.enumerate())
        if len(threads) > len(self._test_ctx["threads"]):
            extra = threads - self._test_ctx["threads"]
            raise AssertionError("%s orphaned thread(s) were left "
                                 "behind: %r" % (len(extra), extra))

    def __str__(self):
        # Print a full path representation of the single unit tests
        # being run.
        fqmod = self.__class__.__module__
        if not fqmod.startswith('pyftpdlib.'):
            fqmod = 'pyftpdlib.test.' + fqmod
        return "%s.%s.%s" % (
            fqmod, self.__class__.__name__, self._testMethodName)

    # assertRaisesRegexp renamed to assertRaisesRegex in 3.3;
    # add support for the new name.
    if not hasattr(unittest.TestCase, 'assertRaisesRegex'):
        assertRaisesRegex = unittest.TestCase.assertRaisesRegexp  # noqa

    def get_testfn(self, suffix="", dir=None):
        fname = get_testfn(suffix=suffix, dir=dir)
        self.addCleanup(safe_rmpath, fname)
        return fname


def close_client(session):
    """Closes a ftplib.FTP client session."""
    try:
        if session.sock is not None:
            try:
                resp = session.quit()
            except Exception:  # noqa
                pass
            else:
                # ...just to make sure the server isn't replying to some
                # pending command.
                assert resp.startswith('221'), resp
    finally:
        session.close()


def try_address(host, port=0, family=socket.AF_INET):
    """Try to bind a socket on the given host:port and return True
    if that has been possible."""
    try:
        with contextlib.closing(socket.socket(family)) as sock:
            sock.bind((host, port))
    except (socket.error, socket.gaierror):
        return False
    else:
        return True


SUPPORTS_IPV4 = try_address('127.0.0.1')
SUPPORTS_IPV6 = socket.has_ipv6 and try_address('::1', family=socket.AF_INET6)
SUPPORTS_SENDFILE = hasattr(os, 'sendfile') or sendfile is not None


def get_testfn(suffix="", dir=None):
    """Return an absolute pathname of a file or dir that did not
    exist at the time this call is made. Also schedule it for safe
    deletion at interpreter exit. It's technically racy but probably
    not really due to the time variant.
    """
    if dir is None:
        dir = os.getcwd()
    while True:
        name = tempfile.mktemp(prefix=TESTFN_PREFIX, suffix=suffix, dir=dir)
        if not os.path.exists(name):  # also include dirs
            return os.path.basename(name)


def safe_rmpath(path):
    """Convenience function for removing temporary test files or dirs."""
    def retry_fun(fun):
        # On Windows it could happen that the file or directory has
        # open handles or references preventing the delete operation
        # to succeed immediately, so we retry for a while. See:
        # https://bugs.python.org/issue33240
        stop_at = time.time() + GLOBAL_TIMEOUT
        while time.time() < stop_at:
            try:
                return fun()
            except FileNotFoundError:
                pass
            except WindowsError as _:
                err = _
                warnings.warn("ignoring %s" % str(err), UserWarning,
                              stacklevel=2)
            time.sleep(0.01)
        raise err

    try:
        st = os.stat(path)
        if stat.S_ISDIR(st.st_mode):
            fun = functools.partial(shutil.rmtree, path)
        else:
            fun = functools.partial(os.remove, path)
        if POSIX:
            fun()
        else:
            retry_fun(fun)
    except FileNotFoundError:
        pass


def touch(name):
    """Create a file and return its name."""
    with open(name, 'w') as f:
        return f.name


def configure_logging():
    """Set pyftpdlib logger to "WARNING" level."""
    handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt=LOG_FMT)
    handler.setFormatter(formatter)
    logger = logging.getLogger('pyftpdlib')
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)



def disable_log_warning(fun):
    """Temporarily set FTP server's logging level to ERROR."""
    @functools.wraps(fun)
    def wrapper(self, *args, **kwargs):
        logger = logging.getLogger('pyftpdlib')
        level = logger.getEffectiveLevel()
        logger.setLevel(logging.ERROR)
        try:
            return fun(self, *args, **kwargs)
        finally:
            logger.setLevel(level)
    return wrapper


def cleanup():
    """Cleanup function executed on interpreter exit."""
    map = IOLoop.instance().socket_map
    for x in list(map.values()):
        try:
            sys.stderr.write("garbage: %s\n" % repr(x))
            x.close()
        except Exception:  # noqa
            pass
    map.clear()


class retry:
    """A retry decorator."""

    def __init__(self,
                 exception=Exception,
                 timeout=None,
                 retries=None,
                 interval=0.001,
                 logfun=None,
                 ):
        if timeout and retries:
            raise ValueError("timeout and retries args are mutually exclusive")
        self.exception = exception
        self.timeout = timeout
        self.retries = retries
        self.interval = interval
        self.logfun = logfun

    def __iter__(self):
        if self.timeout:
            stop_at = time.time() + self.timeout
            while time.time() < stop_at:
                yield
        elif self.retries:
            for _ in range(self.retries):
                yield
        else:
            while True:
                yield

    def sleep(self):
        if self.interval is not None:
            time.sleep(self.interval)

    def __call__(self, fun):
        @functools.wraps(fun)
        def wrapper(cls, *args, **kwargs):
            exc = None
            for _ in self:
                try:
                    return fun(cls, *args, **kwargs)
                except self.exception as _:
                    exc = _
                    if self.logfun is not None:
                        self.logfun(exc)
                    self.sleep()
                    if isinstance(cls, unittest.TestCase):
                        cls.tearDown()
                        cls.setUp()
                    continue
            if PY3:
                raise exc
            else:
                raise

        # This way the user of the decorated function can change config
        # parameters.
        wrapper.decorator = self
        return wrapper


def retry_on_failure(retries=NO_RETRIES):
    """Decorator which runs a test function and retries N times before
    actually failing.
    """
    def logfun(exc):
        print("%r, retrying" % exc, file=sys.stderr)  # NOQA

    return retry(exception=AssertionError, timeout=None, retries=retries,
                 logfun=logfun)


def call_until(fun, expr, timeout=GLOBAL_TIMEOUT):
    """Keep calling function for timeout secs and exit if eval()
    expression is True.
    """
    stop_at = time.time() + timeout
    while time.time() < stop_at:
        ret = fun()
        if eval(expr):  # noqa
            return ret
        time.sleep(0.001)
    raise RuntimeError('timed out (ret=%r)' % ret)


def get_server_handler():
    """Return the first FTPHandler instance running in the IOLoop."""
    ioloop = IOLoop.instance()
    for fd in ioloop.socket_map:
        instance = ioloop.socket_map[fd]
        if isinstance(instance, FTPHandler):
            return instance
    raise RuntimeError("can't find any FTPHandler instance")


# commented out as per bug http://bugs.python.org/issue10354
# tempfile.template = 'tmp-pyftpdlib'

def setup_server(handler, server_class, addr=None):
    addr = (HOST, 0) if addr is None else addr
    authorizer = DummyAuthorizer()
    # full perms
    authorizer.add_user(USER, PASSWD, HOME, perm='elradfmwMT')
    authorizer.add_anonymous(HOME)
    handler.authorizer = authorizer
    handler.auth_failed_timeout = 0.001
    # lower buffer sizes = more "loops" while transferring data
    # = less false positives
    handler.dtp_handler.ac_in_buffer_size = 4096
    handler.dtp_handler.ac_out_buffer_size = 4096
    server = server_class(addr, handler)
    return server


def assert_free_resources(parent_pid=None):
    # check orphaned threads
    ts = threading.enumerate()
    assert len(ts) == 1, ts
    # check orphaned process children
    this_proc = psutil.Process(parent_pid or os.getpid())
    children = this_proc.children()
    if children:
        warnings.warn("some children didn't terminate %r" % str(children),
                      UserWarning, stacklevel=2)
        for child in children:
            try:
                child.kill()
                child.wait(GLOBAL_TIMEOUT)
            except psutil.NoSuchProcess:
                pass
    # check unclosed connections
    if POSIX:
        cons = [x for x in this_proc.connections('tcp')
                if x.status != psutil.CONN_CLOSE_WAIT]
        if cons:
            warnings.warn("some connections didn't close %r" % str(cons),
                          UserWarning, stacklevel=2)


def reset_server_opts():
    # Since all pyftpdlib configurable "options" are class attributes
    # we reset them at module.class level.
    import pyftpdlib.handlers
    import pyftpdlib.servers

    # Control handlers.
    tls_handler = getattr(pyftpdlib.handlers, "TLS_FTPHandler",
                          pyftpdlib.handlers.FTPHandler)
    for klass in (pyftpdlib.handlers.FTPHandler, tls_handler):
        klass.auth_failed_timeout = 0.001
        klass.authorizer = DummyAuthorizer()
        klass.banner = "pyftpdlib ready."
        klass.masquerade_address = None
        klass.masquerade_address_map = {}
        klass.max_login_attempts = 3
        klass.passive_ports = None
        klass.permit_foreign_addresses = False
        klass.permit_privileged_ports = False
        klass.tcp_no_delay = hasattr(socket, 'TCP_NODELAY')
        klass.timeout = 300
        klass.unicode_errors = "replace"
        klass.use_gmt_times = True
        klass.use_sendfile = _import_sendfile() is not None
        klass.ac_in_buffer_size = 4096
        klass.ac_out_buffer_size = 4096
        if klass.__name__ == 'TLS_FTPHandler':
            klass.tls_control_required = False
            klass.tls_data_required = False

    # Data handlers.
    tls_handler = getattr(pyftpdlib.handlers, "TLS_DTPHandler",
                          pyftpdlib.handlers.DTPHandler)
    for klass in (pyftpdlib.handlers.DTPHandler, tls_handler):
        klass.timeout = 300
        klass.ac_in_buffer_size = 4096
        klass.ac_out_buffer_size = 4096
    pyftpdlib.handlers.ThrottledDTPHandler.read_limit = 0
    pyftpdlib.handlers.ThrottledDTPHandler.write_limit = 0
    pyftpdlib.handlers.ThrottledDTPHandler.auto_sized_buffers = True

    # Acceptors.
    ls = [pyftpdlib.servers.FTPServer,
          pyftpdlib.servers.ThreadedFTPServer]
    if POSIX:
        ls.append(pyftpdlib.servers.MultiprocessFTPServer)
    for klass in ls:
        klass.max_cons = 0
        klass.max_cons_per_ip = 0


class ThreadedTestFTPd(threading.Thread):
    """A threaded FTP server used for running tests.
    This is basically a modified version of the FTPServer class which
    wraps the polling loop into a thread.
    The instance returned can be start()ed and stop()ped.
    """
    handler = FTPHandler
    server_class = FTPServer
    poll_interval = 0.001 if CI_TESTING else 0.000001
    # Makes the thread stop on interpreter exit.
    daemon = True

    def __init__(self, addr=None):
        self.parent_pid = os.getpid()
        super().__init__(name='test-ftpd')
        self.server = setup_server(self.handler, self.server_class, addr=addr)
        self.host, self.port = self.server.socket.getsockname()[:2]

        self.lock = threading.Lock()
        self._stop_flag = False
        self._event_stop = threading.Event()

    def run(self):
        try:
            while not self._stop_flag:
                with self.lock:
                    self.server.serve_forever(timeout=self.poll_interval,
                                              blocking=False)
        finally:
            self._event_stop.set()

    def stop(self):
        self._stop_flag = True  # signal the main loop to exit
        self._event_stop.wait()
        self.server.close_all()
        self.join()
        reset_server_opts()
        assert_free_resources(self.parent_pid)


if POSIX:
    class MProcessTestFTPd(multiprocessing.Process):
        """Same as above but using a sub process instead."""
        handler = FTPHandler
        server_class = FTPServer

        def __init__(self, addr=None):
            super().__init__()
            self.server = setup_server(
                self.handler, self.server_class, addr=addr)
            self.host, self.port = self.server.socket.getsockname()[:2]
            self._started = False

        def run(self):
            assert not self._started
            self._started = True
            self.name = "%s(%s)" % (self.__class__.__name__, self.pid)
            self.server.serve_forever()

        def stop(self):
            self.server.close_all()
            self.terminate()
            self.join()
            reset_server_opts()
            assert_free_resources()
else:
    # Windows
    MProcessTestFTPd = ThreadedTestFTPd


@atexit.register
def exit_cleanup():
    for name in os.listdir(ROOT_DIR):
        if name.startswith(TESTFN_PREFIX):
            safe_rmpath(os.path.join(ROOT_DIR, name))
