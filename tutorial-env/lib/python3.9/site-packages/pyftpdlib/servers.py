# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""
This module contains the main FTPServer class which listens on a
host:port and dispatches the incoming connections to a handler.
The concurrency is handled asynchronously by the main process thread,
meaning the handler cannot block otherwise the whole server will hang.

Other than that we have 2 subclasses changing the asynchronous concurrency
model using multiple threads or processes.

You might be interested in these in case your code contains blocking
parts which cannot be adapted to the base async model or if the
underlying filesystem is particularly slow, see:

https://github.com/giampaolo/pyftpdlib/issues/197
https://github.com/giampaolo/pyftpdlib/issues/212

Two classes are provided:

 - ThreadingFTPServer
 - MultiprocessFTPServer

...spawning a new thread or process every time a client connects.

The main thread will be async-based and be used only to accept new
connections.
Every time a new connection comes in that will be dispatched to a
separate thread/process which internally will run its own IO loop.
This way the handler handling that connections will be free to block
without hanging the whole FTP server.
"""

import errno
import os
import select
import signal
import sys
import threading
import time
import traceback

from .ioloop import Acceptor
from .log import PREFIX
from .log import PREFIX_MPROC
from .log import config_logging
from .log import debug
from .log import is_logging_configured
from .log import logger
from .prefork import fork_processes


__all__ = ['FTPServer', 'ThreadedFTPServer']
_BSD = 'bsd' in sys.platform


# ===================================================================
# --- base class
# ===================================================================

class FTPServer(Acceptor):
    """Creates a socket listening on <address>, dispatching the requests
    to a <handler> (typically FTPHandler class).

    Depending on the type of address specified IPv4 or IPv6 connections
    (or both, depending from the underlying system) will be accepted.

    All relevant session information is stored in class attributes
    described below.

     - (int) max_cons:
        number of maximum simultaneous connections accepted (defaults
        to 512). Can be set to 0 for unlimited but it is recommended
        to always have a limit to avoid running out of file descriptors
        (DoS).

     - (int) max_cons_per_ip:
        number of maximum connections accepted for the same IP address
        (defaults to 0 == unlimited).
    """

    max_cons = 512
    max_cons_per_ip = 0

    def __init__(self, address_or_socket, handler, ioloop=None, backlog=100):
        """Creates a socket listening on 'address' dispatching
        connections to a 'handler'.

         - (tuple) address_or_socket: the (host, port) pair on which
           the command channel will listen for incoming connections or
           an existent socket object.

         - (instance) handler: the handler class to use.

         - (instance) ioloop: a pyftpdlib.ioloop.IOLoop instance

         - (int) backlog: the maximum number of queued connections
           passed to listen(). If a connection request arrives when
           the queue is full the client may raise ECONNRESET.
           Defaults to 5.
        """
        Acceptor.__init__(self, ioloop=ioloop)
        self.handler = handler
        self.backlog = backlog
        self.ip_map = []
        # in case of FTPS class not properly configured we want errors
        # to be raised here rather than later, when client connects
        if hasattr(handler, 'get_ssl_context'):
            handler.get_ssl_context()
        if callable(getattr(address_or_socket, 'listen', None)):
            sock = address_or_socket
            sock.setblocking(0)
            self.set_socket(sock)
        else:
            self.bind_af_unspecified(address_or_socket)
        self.listen(backlog)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_all()

    @property
    def address(self):
        """The address this server is listening on as a (ip, port) tuple."""
        return self.socket.getsockname()[:2]

    def _map_len(self):
        return len(self.ioloop.socket_map)

    def _accept_new_cons(self):
        """Return True if the server is willing to accept new connections."""
        if not self.max_cons:
            return True
        else:
            return self._map_len() <= self.max_cons

    def _log_start(self, prefork=False):
        def get_fqname(obj):
            try:
                return obj.__module__ + "." + obj.__class__.__name__
            except AttributeError:
                try:
                    return obj.__module__ + "." + obj.__name__
                except AttributeError:
                    return str(obj)

        if not is_logging_configured():
            # If we get to this point it means the user hasn't
            # configured any logger. We want logging to be on
            # by default (stderr).
            config_logging(prefix=PREFIX_MPROC if prefork else PREFIX)

        if self.handler.passive_ports:
            pasv_ports = "%s->%s" % (self.handler.passive_ports[0],
                                     self.handler.passive_ports[-1])
        else:
            pasv_ports = None
        model = 'prefork + ' if prefork else ''
        if 'ThreadedFTPServer' in __all__ and \
                issubclass(self.__class__, ThreadedFTPServer):
            model += 'multi-thread'
        elif 'MultiprocessFTPServer' in __all__ and \
                issubclass(self.__class__, MultiprocessFTPServer):
            model += 'multi-process'
        elif issubclass(self.__class__, FTPServer):
            model += 'async'
        else:
            model += 'unknown (custom class)'
        logger.info("concurrency model: " + model)
        logger.info("masquerade (NAT) address: %s",
                    self.handler.masquerade_address)
        logger.info("passive ports: %s", pasv_ports)
        logger.debug("poller: %r", get_fqname(self.ioloop))
        logger.debug("authorizer: %r", get_fqname(self.handler.authorizer))
        if os.name == 'posix':
            logger.debug("use sendfile(2): %s", self.handler.use_sendfile)
        logger.debug("handler: %r", get_fqname(self.handler))
        logger.debug("max connections: %s", self.max_cons or "unlimited")
        logger.debug("max connections per ip: %s",
                     self.max_cons_per_ip or "unlimited")
        logger.debug("timeout: %s", self.handler.timeout or "unlimited")
        logger.debug("banner: %r", self.handler.banner)
        logger.debug("max login attempts: %r", self.handler.max_login_attempts)
        if getattr(self.handler, 'certfile', None):
            logger.debug("SSL certfile: %r", self.handler.certfile)
        if getattr(self.handler, 'keyfile', None):
            logger.debug("SSL keyfile: %r", self.handler.keyfile)

    def serve_forever(self, timeout=None, blocking=True, handle_exit=True,
                      worker_processes=1):
        """Start serving.

         - (float) timeout: the timeout passed to the underlying IO
           loop expressed in seconds.

         - (bool) blocking: if False loop once and then return the
           timeout of the next scheduled call next to expire soonest
           (if any).

         - (bool) handle_exit: when True catches KeyboardInterrupt and
           SystemExit exceptions (generally caused by SIGTERM / SIGINT
           signals) and gracefully exits after cleaning up resources.
           Also, logs server start and stop.

         - (int) worker_processes: pre-fork a certain number of child
           processes before starting.
           Each child process will keep using a 1-thread, async
           concurrency model, handling multiple concurrent connections.
           If the number is None or <= 0 the number of usable cores
           available on this machine is detected and used.
           It is a good idea to use this option in case the app risks
           blocking for too long on a single function call (e.g.
           hard-disk is slow, long DB query on auth etc.).
           By splitting the work load over multiple processes the delay
           introduced by a blocking function call is amortized and divided
           by the number of worker processes.
        """
        log = handle_exit and blocking

        #
        if worker_processes != 1 and os.name == 'posix':
            if not blocking:
                raise ValueError(
                    "'worker_processes' and 'blocking' are mutually exclusive")
            if log:
                self._log_start(prefork=True)
            fork_processes(worker_processes)
        else:
            if log:
                self._log_start()

        #
        proto = "FTP+SSL" if hasattr(self.handler, 'ssl_protocol') else "FTP"
        logger.info(">>> starting %s server on %s:%s, pid=%i <<<"
                    % (proto, self.address[0], self.address[1], os.getpid()))

        #
        if handle_exit:
            try:
                self.ioloop.loop(timeout, blocking)
            except (KeyboardInterrupt, SystemExit):
                logger.info("received interrupt signal")
            if blocking:
                if log:
                    logger.info(
                        ">>> shutting down FTP server, %s socket(s), pid=%i "
                        "<<<", self._map_len(), os.getpid())
                self.close_all()
        else:
            self.ioloop.loop(timeout, blocking)

    def handle_accepted(self, sock, addr):
        """Called when remote client initiates a connection."""
        handler = None
        ip = None
        try:
            handler = self.handler(sock, self, ioloop=self.ioloop)
            if not handler.connected:
                return

            ip = addr[0]
            self.ip_map.append(ip)

            # For performance and security reasons we should always set a
            # limit for the number of file descriptors that socket_map
            # should contain.  When we're running out of such limit we'll
            # use the last available channel for sending a 421 response
            # to the client before disconnecting it.
            if not self._accept_new_cons():
                handler.handle_max_cons()
                return

            # accept only a limited number of connections from the same
            # source address.
            if self.max_cons_per_ip:
                if self.ip_map.count(ip) > self.max_cons_per_ip:
                    handler.handle_max_cons_per_ip()
                    return

            try:
                handler.handle()
            except Exception:
                handler.handle_error()
            else:
                return handler
        except Exception:
            # This is supposed to be an application bug that should
            # be fixed. We do not want to tear down the server though
            # (DoS). We just log the exception, hoping that someone
            # will eventually file a bug. References:
            # - https://github.com/giampaolo/pyftpdlib/issues/143
            # - https://github.com/giampaolo/pyftpdlib/issues/166
            # - https://groups.google.com/forum/#!topic/pyftpdlib/h7pPybzAx14
            logger.error(traceback.format_exc())
            if handler is not None:
                handler.close()
            else:
                if ip is not None and ip in self.ip_map:
                    self.ip_map.remove(ip)

    def handle_error(self):
        """Called to handle any uncaught exceptions."""
        try:
            raise
        except Exception:
            logger.error(traceback.format_exc())
        self.close()

    def close_all(self):
        """Stop serving and also disconnects all currently connected
        clients.
        """
        return self.ioloop.close()


# ===================================================================
# --- extra implementations
# ===================================================================

class _SpawnerBase(FTPServer):
    """Base class shared by multiple threads/process dispatcher.
    Not supposed to be used.
    """

    # How many seconds to wait when join()ing parent's threads
    # or processes.
    join_timeout = 5
    # How often thread/process finished tasks should be cleaned up.
    refresh_interval = 5
    _lock = None
    _exit = None

    def __init__(self, address_or_socket, handler, ioloop=None, backlog=100):
        FTPServer.__init__(self, address_or_socket, handler,
                           ioloop=ioloop, backlog=backlog)
        self._active_tasks = []
        self._active_tasks_idler = self.ioloop.call_every(
            self.refresh_interval,
            self._refresh_tasks,
            _errback=self.handle_error)

    def _start_task(self, *args, **kwargs):
        raise NotImplementedError('must be implemented in subclass')

    def _map_len(self):
        if len(self._active_tasks) >= self.max_cons:
            # Since refresh()ing is a potentially expensive operation
            # (O(N)) do it only if we're exceeding max connections
            # limit. Other than in here, tasks are refreshed every 10
            # seconds anyway.
            self._refresh_tasks()
        return len(self._active_tasks)

    def _refresh_tasks(self):
        """join() terminated tasks and update internal _tasks list.
        This gets called every X secs.
        """
        if self._active_tasks:
            logger.debug("refreshing tasks (%s join() potentials)" %
                         len(self._active_tasks))
            with self._lock:
                new = []
                for t in self._active_tasks:
                    if not t.is_alive():
                        self._join_task(t)
                    else:
                        new.append(t)

                self._active_tasks = new

    def _loop(self, handler):
        """Serve handler's IO loop in a separate thread or process."""
        with self.ioloop.factory() as ioloop:
            handler.ioloop = ioloop
            try:
                handler.add_channel()
            except EnvironmentError as err:
                if err.errno == errno.EBADF:
                    # we might get here in case the other end quickly
                    # disconnected (see test_quick_connect())
                    debug("call: %s._loop(); add_channel() returned EBADF",
                          self)
                    return
                else:
                    raise

            # Here we localize variable access to minimize overhead.
            poll = ioloop.poll
            sched_poll = ioloop.sched.poll
            poll_timeout = getattr(self, 'poll_timeout', None)
            soonest_timeout = poll_timeout

            while (ioloop.socket_map or ioloop.sched._tasks) and \
                    not self._exit.is_set():
                try:
                    if ioloop.socket_map:
                        poll(timeout=soonest_timeout)
                    if ioloop.sched._tasks:
                        soonest_timeout = sched_poll()
                        # Handle the case where socket_map is empty but some
                        # cancelled scheduled calls are still around causing
                        # this while loop to hog CPU resources.
                        # In theory this should never happen as all the sched
                        # functions are supposed to be cancel()ed on close()
                        # but by using threads we can incur into
                        # synchronization issues such as this one.
                        # https://github.com/giampaolo/pyftpdlib/issues/245
                        if not ioloop.socket_map:
                            # get rid of cancel()led calls
                            ioloop.sched.reheapify()
                            soonest_timeout = sched_poll()
                            if soonest_timeout:
                                time.sleep(min(soonest_timeout, 1))
                    else:
                        soonest_timeout = None
                except (KeyboardInterrupt, SystemExit):
                    # note: these two exceptions are raised in all sub
                    # processes
                    self._exit.set()
                except OSError as err:
                    # on Windows we can get WSAENOTSOCK if the client
                    # rapidly connect and disconnects
                    if os.name == 'nt' and err.winerror == 10038:
                        for fd in list(ioloop.socket_map.keys()):
                            try:
                                select.select([fd], [], [], 0)
                            except select.error:
                                try:
                                    logger.info("discarding broken socket %r",
                                                ioloop.socket_map[fd])
                                    del ioloop.socket_map[fd]
                                except KeyError:
                                    # dict changed during iteration
                                    pass
                    else:
                        raise
                else:
                    if poll_timeout:
                        if soonest_timeout is None or \
                                soonest_timeout > poll_timeout:
                            soonest_timeout = poll_timeout

    def handle_accepted(self, sock, addr):
        handler = FTPServer.handle_accepted(self, sock, addr)
        if handler is not None:
            # unregister the handler from the main IOLoop used by the
            # main thread to accept connections
            self.ioloop.unregister(handler._fileno)

            t = self._start_task(target=self._loop, args=(handler, ),
                                 name='ftpd')
            t.name = repr(addr)
            t.start()

            # it is a different process so free resources here
            if hasattr(t, 'pid'):
                handler.close()

            with self._lock:
                # add the new task
                self._active_tasks.append(t)

    def _log_start(self):
        FTPServer._log_start(self)

    def serve_forever(self, timeout=1.0, blocking=True, handle_exit=True):
        self._exit.clear()
        if handle_exit:
            log = handle_exit and blocking
            if log:
                self._log_start()
            try:
                self.ioloop.loop(timeout, blocking)
            except (KeyboardInterrupt, SystemExit):
                pass
            if blocking:
                if log:
                    logger.info(
                        ">>> shutting down FTP server (%s active workers) <<<",
                        self._map_len())
                self.close_all()
        else:
            self.ioloop.loop(timeout, blocking)

    def _terminate_task(self, t):
        if hasattr(t, 'terminate'):
            logger.debug("terminate()ing task %r" % t)
            try:
                if not _BSD:
                    t.terminate()
                else:
                    # XXX - On FreeBSD using SIGTERM doesn't work
                    # as the process hangs on kqueue.control() or
                    # select.select(). Use SIGKILL instead.
                    os.kill(t.pid, signal.SIGKILL)
            except OSError as err:
                if err.errno != errno.ESRCH:
                    raise

    def _join_task(self, t):
        logger.debug("join()ing task %r" % t)
        t.join(self.join_timeout)
        if t.is_alive():
            logger.warning("task %r remained alive after %r secs", t,
                           self.join_timeout)

    def close_all(self):
        self._active_tasks_idler.cancel()
        # this must be set after getting active tasks as it causes
        # thread objects to get out of the list too soon
        self._exit.set()

        with self._lock:
            for t in self._active_tasks:
                self._terminate_task(t)
            for t in self._active_tasks:
                self._join_task(t)
            del self._active_tasks[:]

        FTPServer.close_all(self)


class ThreadedFTPServer(_SpawnerBase):
    """A modified version of base FTPServer class which spawns a
    thread every time a new connection is established.
    """
    # The timeout passed to thread's IOLoop.poll() call on every
    # loop. Necessary since threads ignore KeyboardInterrupt.
    poll_timeout = 1.0
    _lock = threading.Lock()
    _exit = threading.Event()

    def _start_task(self, *args, **kwargs):
        return threading.Thread(*args, **kwargs)


if os.name == 'posix':
    try:
        import multiprocessing
        multiprocessing.Lock()
    except Exception:  # noqa
        # see https://github.com/giampaolo/pyftpdlib/issues/496
        pass
    else:
        __all__ += ['MultiprocessFTPServer']

        class MultiprocessFTPServer(_SpawnerBase):
            """A modified version of base FTPServer class which spawns a
            process every time a new connection is established.
            """
            _lock = multiprocessing.Lock()
            _exit = multiprocessing.Event()

            def _start_task(self, *args, **kwargs):
                return multiprocessing.Process(*args, **kwargs)
