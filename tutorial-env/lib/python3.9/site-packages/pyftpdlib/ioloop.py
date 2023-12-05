# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""
A specialized IO loop on top of asyncore adding support for epoll()
on Linux and kqueue() and OSX/BSD, dramatically increasing performances
offered by base asyncore module.

poll() and select() loops are also reimplemented and are an order of
magnitude faster as they support fd un/registration and modification.

This module is not supposed to be used directly unless you want to
include a new dispatcher which runs within the main FTP server loop,
in which case:
  __________________________________________________________________
 |                      |                                           |
 | INSTEAD OF           | ...USE:                                   |
 |______________________|___________________________________________|
 |                      |                                           |
 | asyncore.dispacher   | Acceptor (for servers)                    |
 | asyncore.dispacher   | Connector (for clients)                   |
 | asynchat.async_chat  | AsyncChat (for a full duplex connection ) |
 | asyncore.loop        | FTPServer.server_forever()                |
 |______________________|___________________________________________|

asyncore.dispatcher_with_send is not supported, same for "map" argument
for asyncore.loop and asyncore.dispatcher and asynchat.async_chat
constructors.

Follows a server example:

import socket
from pyftpdlib.ioloop import IOLoop, Acceptor, AsyncChat

class Handler(AsyncChat):

    def __init__(self, sock):
        AsyncChat.__init__(self, sock)
        self.push('200 hello\r\n')
        self.close_when_done()

class Server(Acceptor):

    def __init__(self, host, port):
        Acceptor.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)

    def handle_accepted(self, sock, addr):
        Handler(sock)

server = Server('localhost', 8021)
IOLoop.instance().loop()
"""

import errno
import heapq
import os
import select
import socket
import sys
import time
import traceback


try:
    import threading
except ImportError:
    import dummy_threading as threading

from ._compat import callable
from .log import config_logging
from .log import debug
from .log import is_logging_configured
from .log import logger


if sys.version_info[:2] >= (3, 12):
    from . import _asynchat as asynchat
    from . import _asyncore as asyncore
else:
    import asynchat
    import asyncore


timer = getattr(time, 'monotonic', time.time)
_read = asyncore.read
_write = asyncore.write

# These errnos indicate that a connection has been abruptly terminated.
_ERRNOS_DISCONNECTED = set((
    errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN, errno.ECONNABORTED,
    errno.EPIPE, errno.EBADF, errno.ETIMEDOUT))
if hasattr(errno, "WSAECONNRESET"):
    _ERRNOS_DISCONNECTED.add(errno.WSAECONNRESET)
if hasattr(errno, "WSAECONNABORTED"):
    _ERRNOS_DISCONNECTED.add(errno.WSAECONNABORTED)

# These errnos indicate that a non-blocking operation must be retried
# at a later time.
_ERRNOS_RETRY = set((errno.EAGAIN, errno.EWOULDBLOCK))
if hasattr(errno, "WSAEWOULDBLOCK"):
    _ERRNOS_RETRY.add(errno.WSAEWOULDBLOCK)


class RetryError(Exception):
    pass


# ===================================================================
# --- scheduler
# ===================================================================

class _Scheduler:
    """Run the scheduled functions due to expire soonest (if any)."""

    def __init__(self):
        # the heap used for the scheduled tasks
        self._tasks = []
        self._cancellations = 0

    def poll(self):
        """Run the scheduled functions due to expire soonest and
        return the timeout of the next one (if any, else None).
        """
        now = timer()
        calls = []
        while self._tasks:
            if now < self._tasks[0].timeout:
                break
            call = heapq.heappop(self._tasks)
            if call.cancelled:
                self._cancellations -= 1
            else:
                calls.append(call)

        for call in calls:
            if call._repush:
                heapq.heappush(self._tasks, call)
                call._repush = False
                continue
            try:
                call.call()
            except Exception:
                logger.error(traceback.format_exc())

        # remove cancelled tasks and re-heapify the queue if the
        # number of cancelled tasks is more than the half of the
        # entire queue
        if self._cancellations > 512 and \
                self._cancellations > (len(self._tasks) >> 1):
            debug("re-heapifying %s cancelled tasks" % self._cancellations)
            self.reheapify()

        try:
            return max(0, self._tasks[0].timeout - now)
        except IndexError:
            pass

    def register(self, what):
        """Register a _CallLater instance."""
        heapq.heappush(self._tasks, what)

    def unregister(self, what):
        """Unregister a _CallLater instance.
        The actual unregistration will happen at a later time though.
        """
        self._cancellations += 1

    def reheapify(self):
        """Get rid of cancelled calls and reinitialize the internal heap."""
        self._cancellations = 0
        self._tasks = [x for x in self._tasks if not x.cancelled]
        heapq.heapify(self._tasks)


class _CallLater:
    """Container object which instance is returned by ioloop.call_later()."""

    __slots__ = ('_delay', '_target', '_args', '_kwargs', '_errback', '_sched',
                 '_repush', 'timeout', 'cancelled')

    def __init__(self, seconds, target, *args, **kwargs):
        assert callable(target), "%s is not callable" % target
        assert sys.maxsize >= seconds >= 0, \
            "%s is not greater than or equal to 0 seconds" % seconds
        self._delay = seconds
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self._errback = kwargs.pop('_errback', None)
        self._sched = kwargs.pop('_scheduler')
        self._repush = False
        # seconds from the epoch at which to call the function
        if not seconds:
            self.timeout = 0
        else:
            self.timeout = timer() + self._delay
        self.cancelled = False
        self._sched.register(self)

    def __lt__(self, other):
        return self.timeout < other.timeout

    def __le__(self, other):
        return self.timeout <= other.timeout

    def __repr__(self):
        if self._target is None:
            sig = object.__repr__(self)
        else:
            sig = repr(self._target)
        sig += ' args=%s, kwargs=%s, cancelled=%s, secs=%s' % (
            self._args or '[]', self._kwargs or '{}', self.cancelled,
            self._delay)
        return '<%s>' % sig

    __str__ = __repr__

    def _post_call(self, exc):
        if not self.cancelled:
            self.cancel()

    def call(self):
        """Call this scheduled function."""
        assert not self.cancelled, "already cancelled"
        exc = None
        try:
            self._target(*self._args, **self._kwargs)
        except Exception as _:
            exc = _
            if self._errback is not None:
                self._errback()
            else:
                raise
        finally:
            self._post_call(exc)

    def reset(self):
        """Reschedule this call resetting the current countdown."""
        assert not self.cancelled, "already cancelled"
        self.timeout = timer() + self._delay
        self._repush = True

    def cancel(self):
        """Unschedule this call."""
        if not self.cancelled:
            self.cancelled = True
            self._target = self._args = self._kwargs = self._errback = None
            self._sched.unregister(self)


class _CallEvery(_CallLater):
    """Container object which instance is returned by IOLoop.call_every()."""

    def _post_call(self, exc):
        if not self.cancelled:
            if exc:
                self.cancel()
            else:
                self.timeout = timer() + self._delay
                self._sched.register(self)


class _IOLoop:
    """Base class which will later be referred as IOLoop."""

    READ = 1
    WRITE = 2
    _instance = None
    _lock = threading.Lock()
    _started_once = False

    def __init__(self):
        self.socket_map = {}
        self.sched = _Scheduler()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        status = [self.__class__.__module__ + "." + self.__class__.__name__]
        status.append("(fds=%s, tasks=%s)" % (
            len(self.socket_map), len(self.sched._tasks)))
        return '<%s at %#x>' % (' '.join(status), id(self))

    __str__ = __repr__

    @classmethod
    def instance(cls):
        """Return a global IOLoop instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def factory(cls):
        """Constructs a new IOLoop instance."""
        return cls()

    def register(self, fd, instance, events):
        """Register a fd, handled by instance for the given events."""
        raise NotImplementedError('must be implemented in subclass')

    def unregister(self, fd):
        """Register fd."""
        raise NotImplementedError('must be implemented in subclass')

    def modify(self, fd, events):
        """Changes the events assigned for fd."""
        raise NotImplementedError('must be implemented in subclass')

    def poll(self, timeout):
        """Poll once.  The subclass overriding this method is supposed
        to poll over the registered handlers and the scheduled functions
        and then return.
        """
        raise NotImplementedError('must be implemented in subclass')

    def loop(self, timeout=None, blocking=True):
        """Start the asynchronous IO loop.

         - (float) timeout: the timeout passed to the underlying
           multiplex syscall (select(), epoll() etc.).

         - (bool) blocking: if True poll repeatedly, as long as there
           are registered handlers and/or scheduled functions.
           If False poll only once and return the timeout of the next
           scheduled call (if any, else None).
        """
        if not _IOLoop._started_once:
            _IOLoop._started_once = True
            if not is_logging_configured():
                # If we get to this point it means the user hasn't
                # configured logging. We want to log by default so
                # we configure logging ourselves so that it will
                # print to stderr.
                config_logging()

        if blocking:
            # localize variable access to minimize overhead
            poll = self.poll
            socket_map = self.socket_map
            sched_poll = self.sched.poll

            if timeout is not None:
                while socket_map:
                    poll(timeout)
                    sched_poll()
            else:
                soonest_timeout = None
                while socket_map:
                    poll(soonest_timeout)
                    soonest_timeout = sched_poll()
        else:
            sched = self.sched
            if self.socket_map:
                self.poll(timeout)
            if sched._tasks:
                return sched.poll()

    def call_later(self, seconds, target, *args, **kwargs):
        """Calls a function at a later time.
        It can be used to asynchronously schedule a call within the polling
        loop without blocking it. The instance returned is an object that
        can be used to cancel or reschedule the call.

         - (int) seconds: the number of seconds to wait
         - (obj) target: the callable object to call later
         - args: the arguments to call it with
         - kwargs: the keyword arguments to call it with; a special
           '_errback' parameter can be passed: it is a callable
           called in case target function raises an exception.
       """
        kwargs['_scheduler'] = self.sched
        return _CallLater(seconds, target, *args, **kwargs)

    def call_every(self, seconds, target, *args, **kwargs):
        """Schedules the given callback to be called periodically."""
        kwargs['_scheduler'] = self.sched
        return _CallEvery(seconds, target, *args, **kwargs)

    def close(self):
        """Closes the IOLoop, freeing any resources used."""
        debug("closing IOLoop", self)
        self.__class__._instance = None

        # free connections
        instances = sorted(self.socket_map.values(), key=lambda x: x._fileno)
        for inst in instances:
            try:
                inst.close()
            except OSError as err:
                if err.errno != errno.EBADF:
                    logger.error(traceback.format_exc())
            except Exception:
                logger.error(traceback.format_exc())
        self.socket_map.clear()

        # free scheduled functions
        for x in self.sched._tasks:
            try:
                if not x.cancelled:
                    x.cancel()
            except Exception:
                logger.error(traceback.format_exc())
        del self.sched._tasks[:]


# ===================================================================
# --- select() - POSIX / Windows
# ===================================================================

class Select(_IOLoop):
    """select()-based poller."""

    def __init__(self):
        _IOLoop.__init__(self)
        self._r = []
        self._w = []

    def register(self, fd, instance, events):
        if fd not in self.socket_map:
            self.socket_map[fd] = instance
            if events & self.READ:
                self._r.append(fd)
            if events & self.WRITE:
                self._w.append(fd)

    def unregister(self, fd):
        try:
            del self.socket_map[fd]
        except KeyError:
            debug("call: unregister(); fd was no longer in socket_map", self)
        for ls in (self._r, self._w):
            try:
                ls.remove(fd)
            except ValueError:
                pass

    def modify(self, fd, events):
        inst = self.socket_map.get(fd)
        if inst is not None:
            self.unregister(fd)
            self.register(fd, inst, events)
        else:
            debug("call: modify(); fd was no longer in socket_map", self)

    def poll(self, timeout):
        try:
            r, w, _ = select.select(self._r, self._w, [], timeout)
        except select.error as err:
            if getattr(err, "errno", None) == errno.EINTR:
                return
            raise

        smap_get = self.socket_map.get
        for fd in r:
            obj = smap_get(fd)
            if obj is None or not obj.readable():
                continue
            _read(obj)
        for fd in w:
            obj = smap_get(fd)
            if obj is None or not obj.writable():
                continue
            _write(obj)


# ===================================================================
# --- poll() / epoll()
# ===================================================================

class _BasePollEpoll(_IOLoop):
    """This is common to both poll() (UNIX), epoll() (Linux) and
    /dev/poll (Solaris) implementations which share almost the same
    interface.
    Not supposed to be used directly.
    """

    def __init__(self):
        _IOLoop.__init__(self)
        self._poller = self._poller()

    def register(self, fd, instance, events):
        try:
            self._poller.register(fd, events)
        except EnvironmentError as err:
            if err.errno == errno.EEXIST:
                debug("call: register(); poller raised EEXIST; ignored", self)
            else:
                raise
        self.socket_map[fd] = instance

    def unregister(self, fd):
        try:
            del self.socket_map[fd]
        except KeyError:
            debug("call: unregister(); fd was no longer in socket_map", self)
        else:
            try:
                self._poller.unregister(fd)
            except EnvironmentError as err:
                if err.errno in (errno.ENOENT, errno.EBADF):
                    debug("call: unregister(); poller returned %r; "
                          "ignoring it" % err, self)
                else:
                    raise

    def modify(self, fd, events):
        try:
            self._poller.modify(fd, events)
        except OSError as err:
            if err.errno == errno.ENOENT and fd in self.socket_map:
                # XXX - see:
                # https://github.com/giampaolo/pyftpdlib/issues/329
                instance = self.socket_map[fd]
                self.register(fd, instance, events)
            else:
                raise

    def poll(self, timeout):
        if timeout is None:
            timeout = -1  # -1 waits indefinitely
        try:
            events = self._poller.poll(timeout)
        except (IOError, select.error) as err:
            # for epoll() and poll() respectively
            if err.errno == errno.EINTR:
                return
            raise
        # localize variable access to minimize overhead
        smap_get = self.socket_map.get
        for fd, event in events:
            inst = smap_get(fd)
            if inst is None:
                continue
            if event & self._ERROR and not event & self.READ:
                inst.handle_close()
            else:
                if event & self.READ and inst.readable():
                    _read(inst)
                if event & self.WRITE and inst.writable():
                    _write(inst)


# ===================================================================
# --- poll() - POSIX
# ===================================================================

if hasattr(select, 'poll'):

    class Poll(_BasePollEpoll):
        """poll() based poller."""

        READ = select.POLLIN
        WRITE = select.POLLOUT
        _ERROR = select.POLLERR | select.POLLHUP | select.POLLNVAL
        _poller = select.poll

        def modify(self, fd, events):
            inst = self.socket_map[fd]
            self.unregister(fd)
            self.register(fd, inst, events)

        def poll(self, timeout):
            # poll() timeout is expressed in milliseconds
            if timeout is not None:
                timeout = int(timeout * 1000)
            _BasePollEpoll.poll(self, timeout)


# ===================================================================
# --- /dev/poll - Solaris (introduced in python 3.3)
# ===================================================================

if hasattr(select, 'devpoll'):  # pragma: no cover

    class DevPoll(_BasePollEpoll):
        """/dev/poll based poller (introduced in python 3.3)."""

        READ = select.POLLIN
        WRITE = select.POLLOUT
        _ERROR = select.POLLERR | select.POLLHUP | select.POLLNVAL
        _poller = select.devpoll

        # introduced in python 3.4
        if hasattr(select.devpoll, 'fileno'):
            def fileno(self):
                """Return devpoll() fd."""
                return self._poller.fileno()

        def modify(self, fd, events):
            inst = self.socket_map[fd]
            self.unregister(fd)
            self.register(fd, inst, events)

        def poll(self, timeout):
            # /dev/poll timeout is expressed in milliseconds
            if timeout is not None:
                timeout = int(timeout * 1000)
            _BasePollEpoll.poll(self, timeout)

        # introduced in python 3.4
        if hasattr(select.devpoll, 'close'):
            def close(self):
                _IOLoop.close(self)
                self._poller.close()


# ===================================================================
# --- epoll() - Linux
# ===================================================================

if hasattr(select, 'epoll'):

    class Epoll(_BasePollEpoll):
        """epoll() based poller."""

        READ = select.EPOLLIN
        WRITE = select.EPOLLOUT
        _ERROR = select.EPOLLERR | select.EPOLLHUP
        _poller = select.epoll

        def fileno(self):
            """Return epoll() fd."""
            return self._poller.fileno()

        def close(self):
            _IOLoop.close(self)
            self._poller.close()


# ===================================================================
# --- kqueue() - BSD / OSX
# ===================================================================

if hasattr(select, 'kqueue'):  # pragma: no cover

    class Kqueue(_IOLoop):
        """kqueue() based poller."""

        def __init__(self):
            _IOLoop.__init__(self)
            self._kqueue = select.kqueue()
            self._active = {}

        def fileno(self):
            """Return kqueue() fd."""
            return self._kqueue.fileno()

        def close(self):
            _IOLoop.close(self)
            self._kqueue.close()

        def register(self, fd, instance, events):
            self.socket_map[fd] = instance
            try:
                self._control(fd, events, select.KQ_EV_ADD)
            except EnvironmentError as err:
                if err.errno == errno.EEXIST:
                    debug("call: register(); poller raised EEXIST; ignored",
                          self)
                else:
                    raise
            self._active[fd] = events

        def unregister(self, fd):
            try:
                del self.socket_map[fd]
                events = self._active.pop(fd)
            except KeyError:
                pass
            else:
                try:
                    self._control(fd, events, select.KQ_EV_DELETE)
                except EnvironmentError as err:
                    if err.errno in (errno.ENOENT, errno.EBADF):
                        debug("call: unregister(); poller returned %r; "
                              "ignoring it" % err, self)
                    else:
                        raise

        def modify(self, fd, events):
            instance = self.socket_map[fd]
            self.unregister(fd)
            self.register(fd, instance, events)

        def _control(self, fd, events, flags):
            kevents = []
            if events & self.WRITE:
                kevents.append(select.kevent(
                    fd, filter=select.KQ_FILTER_WRITE, flags=flags))
            if events & self.READ or not kevents:
                # always read when there is not a write
                kevents.append(select.kevent(
                    fd, filter=select.KQ_FILTER_READ, flags=flags))
            # even though control() takes a list, it seems to return
            # EINVAL on Mac OS X (10.6) when there is more than one
            # event in the list
            for kevent in kevents:
                self._kqueue.control([kevent], 0)

        # localize variable access to minimize overhead
        def poll(self,
                 timeout,
                 _len=len,
                 _READ=select.KQ_FILTER_READ,
                 _WRITE=select.KQ_FILTER_WRITE,
                 _EOF=select.KQ_EV_EOF,
                 _ERROR=select.KQ_EV_ERROR):
            try:
                kevents = self._kqueue.control(None, _len(self.socket_map),
                                               timeout)
            except OSError as err:
                if err.errno == errno.EINTR:
                    return
                raise
            for kevent in kevents:
                inst = self.socket_map.get(kevent.ident)
                if inst is None:
                    continue
                if kevent.filter == _READ and inst.readable():
                    _read(inst)
                if kevent.filter == _WRITE:
                    if kevent.flags & _EOF:
                        # If an asynchronous connection is refused,
                        # kqueue returns a write event with the EOF
                        # flag set.
                        # Note that for read events, EOF may be returned
                        # before all data has been consumed from the
                        # socket buffer, so we only check for EOF on
                        # write events.
                        inst.handle_close()
                    else:
                        if inst.writable():
                            _write(inst)
                if kevent.flags & _ERROR:
                    inst.handle_close()


# ===================================================================
# --- choose the better poller for this platform
# ===================================================================

if hasattr(select, 'epoll'):      # epoll() - Linux
    IOLoop = Epoll
elif hasattr(select, 'kqueue'):   # kqueue() - BSD / OSX
    IOLoop = Kqueue
elif hasattr(select, 'devpoll'):  # /dev/poll - Solaris
    IOLoop = DevPoll
elif hasattr(select, 'poll'):     # poll() - POSIX
    IOLoop = Poll
else:                             # select() - POSIX and Windows
    IOLoop = Select


# ===================================================================
# --- asyncore dispatchers
# ===================================================================

# these are overridden in order to register() and unregister()
# file descriptors against the new pollers


class AsyncChat(asynchat.async_chat):
    """Same as asynchat.async_chat, only working with the new IO poller
    and being more clever in avoid registering for read events when
    it shouldn't.
    """

    def __init__(self, sock=None, ioloop=None):
        self.ioloop = ioloop or IOLoop.instance()
        self._wanted_io_events = self.ioloop.READ
        self._current_io_events = self.ioloop.READ
        self._closed = False
        self._closing = False
        self._fileno = sock.fileno() if sock else None
        self._tasks = []
        asynchat.async_chat.__init__(self, sock)

    # --- IO loop related methods

    def add_channel(self, map=None, events=None):
        assert self._fileno, repr(self._fileno)
        events = events if events is not None else self.ioloop.READ
        self.ioloop.register(self._fileno, self, events)
        self._wanted_io_events = events
        self._current_io_events = events

    def del_channel(self, map=None):
        if self._fileno is not None:
            self.ioloop.unregister(self._fileno)

    def modify_ioloop_events(self, events, logdebug=False):
        if not self._closed:
            assert self._fileno, repr(self._fileno)
            if self._fileno not in self.ioloop.socket_map:
                debug(
                    "call: modify_ioloop_events(), fd was no longer in "
                    "socket_map, had to register() it again", inst=self)
                self.add_channel(events=events)
            else:
                if events != self._current_io_events:
                    if logdebug:
                        if events == self.ioloop.READ:
                            ev = "R"
                        elif events == self.ioloop.WRITE:
                            ev = "W"
                        elif events == self.ioloop.READ | self.ioloop.WRITE:
                            ev = "RW"
                        else:
                            ev = events
                        debug("call: IOLoop.modify(); setting %r IO events" % (
                            ev), self)
                    self.ioloop.modify(self._fileno, events)
            self._current_io_events = events
        else:
            debug(
                "call: modify_ioloop_events(), handler had already been "
                "close()d, skipping modify()", inst=self)

    # --- utils

    def call_later(self, seconds, target, *args, **kwargs):
        """Same as self.ioloop.call_later but also cancel()s the
        scheduled function on close().
        """
        if '_errback' not in kwargs and hasattr(self, 'handle_error'):
            kwargs['_errback'] = self.handle_error
        callback = self.ioloop.call_later(seconds, target, *args, **kwargs)
        self._tasks.append(callback)
        return callback

    # --- overridden asynchat methods

    def connect(self, addr):
        self.modify_ioloop_events(self.ioloop.WRITE)
        asynchat.async_chat.connect(self, addr)

    def connect_af_unspecified(self, addr, source_address=None):
        """Same as connect() but guesses address family from addr.
        Return the address family just determined.
        """
        assert self.socket is None
        host, port = addr
        err = "getaddrinfo() returned an empty list"
        info = socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM, 0, socket.AI_PASSIVE)
        for res in info:
            self.socket = None
            af, socktype, proto, canonname, sa = res
            try:
                self.create_socket(af, socktype)
                if source_address:
                    if source_address[0].startswith('::ffff:'):
                        # In this scenario, the server has an IPv6 socket, but
                        # the remote client is using IPv4 and its address is
                        # represented as an IPv4-mapped IPv6 address which
                        # looks like this ::ffff:151.12.5.65, see:
                        # http://en.wikipedia.org/wiki/IPv6\
                        #     IPv4-mapped_addresses
                        # http://tools.ietf.org/html/rfc3493.html#section-3.7
                        # We truncate the first bytes to make it look like a
                        # common IPv4 address.
                        source_address = (source_address[0][7:],
                                          source_address[1])
                    self.bind(source_address)
                self.connect((host, port))
            except socket.error as _:
                err = _
                if self.socket is not None:
                    self.socket.close()
                    self.del_channel()
                    self.socket = None
                continue
            break
        if self.socket is None:
            self.del_channel()
            raise socket.error(err)
        return af

    # send() and recv() overridden as a fix around various bugs:
    # - http://bugs.python.org/issue1736101
    # - https://github.com/giampaolo/pyftpdlib/issues/104
    # - https://github.com/giampaolo/pyftpdlib/issues/109

    def send(self, data):
        try:
            return self.socket.send(data)
        except socket.error as err:
            debug("call: send(), err: %s" % err, inst=self)
            if err.errno in _ERRNOS_RETRY:
                return 0
            elif err.errno in _ERRNOS_DISCONNECTED:
                self.handle_close()
                return 0
            else:
                raise

    def recv(self, buffer_size):
        try:
            data = self.socket.recv(buffer_size)
        except socket.error as err:
            debug("call: recv(), err: %s" % err, inst=self)
            if err.errno in _ERRNOS_DISCONNECTED:
                self.handle_close()
                return b''
            elif err.errno in _ERRNOS_RETRY:
                raise RetryError
            else:
                raise
        else:
            if not data:
                # a closed connection is indicated by signaling
                # a read condition, and having recv() return 0.
                self.handle_close()
                return b''
            else:
                return data

    def handle_read(self):
        try:
            asynchat.async_chat.handle_read(self)
        except RetryError:
            # This can be raised by (the overridden) recv().
            pass

    def initiate_send(self):
        asynchat.async_chat.initiate_send(self)
        if not self._closed:
            # if there's still data to send we want to be ready
            # for writing, else we're only interested in reading
            if not self.producer_fifo:
                wanted = self.ioloop.READ
            else:
                # In FTPHandler, we also want to listen for user input
                # hence the READ. DTPHandler has its own initiate_send()
                # which will either READ or WRITE.
                wanted = self.ioloop.READ | self.ioloop.WRITE
            if self._wanted_io_events != wanted:
                self.ioloop.modify(self._fileno, wanted)
                self._wanted_io_events = wanted
        else:
            debug("call: initiate_send(); called with no connection",
                  inst=self)

    def close_when_done(self):
        if len(self.producer_fifo) == 0:
            self.handle_close()
        else:
            self._closing = True
            asynchat.async_chat.close_when_done(self)

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                asynchat.async_chat.close(self)
            finally:
                for fun in self._tasks:
                    try:
                        fun.cancel()
                    except Exception:
                        logger.error(traceback.format_exc())
                self._tasks = []
                self._closed = True
                self._closing = False
                self.connected = False


class Connector(AsyncChat):
    """Same as base AsyncChat and supposed to be used for
    clients.
    """

    def add_channel(self, map=None, events=None):
        AsyncChat.add_channel(self, map=map, events=self.ioloop.WRITE)


class Acceptor(AsyncChat):
    """Same as base AsyncChat and supposed to be used to
    accept new connections.
    """

    def add_channel(self, map=None, events=None):
        AsyncChat.add_channel(self, map=map, events=self.ioloop.READ)

    def bind_af_unspecified(self, addr):
        """Same as bind() but guesses address family from addr.
        Return the address family just determined.
        """
        assert self.socket is None
        host, port = addr
        if host == "":
            # When using bind() "" is a symbolic name meaning all
            # available interfaces. People might not know we're
            # using getaddrinfo() internally, which uses None
            # instead of "", so we'll make the conversion for them.
            host = None
        err = "getaddrinfo() returned an empty list"
        info = socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM, 0, socket.AI_PASSIVE)
        for res in info:
            self.socket = None
            self.del_channel()
            af, socktype, proto, canonname, sa = res
            try:
                self.create_socket(af, socktype)
                self.set_reuse_addr()
                self.bind(sa)
            except socket.error as _:
                err = _
                if self.socket is not None:
                    self.socket.close()
                    self.del_channel()
                    self.socket = None
                continue
            break
        if self.socket is None:
            self.del_channel()
            raise socket.error(err)
        return af

    def listen(self, num):
        AsyncChat.listen(self, num)
        # XXX - this seems to be necessary, otherwise kqueue.control()
        # won't return listening fd events
        try:
            if isinstance(self.ioloop, Kqueue):
                self.ioloop.modify(self._fileno, self.ioloop.READ)
        except NameError:
            pass

    def handle_accept(self):
        try:
            sock, addr = self.accept()
        except TypeError:
            # sometimes accept() might return None, see:
            # https://github.com/giampaolo/pyftpdlib/issues/91
            debug("call: handle_accept(); accept() returned None", self)
            return
        except socket.error as err:
            # ECONNABORTED might be thrown on *BSD, see:
            # https://github.com/giampaolo/pyftpdlib/issues/105
            if err.errno != errno.ECONNABORTED:
                raise
            else:
                debug("call: handle_accept(); accept() returned ECONNABORTED",
                      self)
        else:
            # sometimes addr == None instead of (ip, port) (see issue 104)
            if addr is not None:
                self.handle_accepted(sock, addr)

    def handle_accepted(self, sock, addr):
        sock.close()
        self.log_info('unhandled accepted event', 'warning')

    # overridden for convenience; avoid to reuse address on Windows
    if (os.name in ('nt', 'ce')) or (sys.platform == 'cygwin'):
        def set_reuse_addr(self):
            pass
