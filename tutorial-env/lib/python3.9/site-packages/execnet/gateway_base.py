"""
base execnet gateway code send to the other side for bootstrapping.

NOTE: aims to be compatible to Python 2.5-3.X, Jython and IronPython

:copyright: 2004-2015
:authors:
    - Holger Krekel
    - Armin Rigo
    - Benjamin Peterson
    - Ronny Pfannschmidt
    - many others
"""
from __future__ import annotations

import abc
import os
import struct
import sys
import traceback
import weakref
from _thread import interrupt_main
from io import BytesIO
from typing import Callable


class ExecModel(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def backend(self):
        raise NotImplementedError()

    def __repr__(self):
        return "<ExecModel %r>" % self.backend

    @property
    @abc.abstractmethod
    def queue(self):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def subprocess(self):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def socket(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def start(self, func, args=()):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_ident(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def sleep(self, delay):
        raise NotImplementedError()

    @abc.abstractmethod
    def fdopen(self, fd, mode, bufsize=1):
        raise NotImplementedError()

    @abc.abstractmethod
    def Lock(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def RLock(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def Event(self):
        raise NotImplementedError()


class ThreadExecModel(ExecModel):
    backend = "thread"

    @property
    def queue(self):
        import queue

        return queue

    @property
    def subprocess(self):
        import subprocess

        return subprocess

    @property
    def socket(self):
        import socket

        return socket

    def get_ident(self):
        import _thread

        return _thread.get_ident()

    def sleep(self, delay):
        import time

        time.sleep(delay)

    def start(self, func, args=()):
        import _thread

        return _thread.start_new_thread(func, args)

    def fdopen(self, fd, mode, bufsize=1):
        import os

        return os.fdopen(fd, mode, bufsize, encoding="utf-8")

    def Lock(self):
        import threading

        return threading.RLock()

    def RLock(self):
        import threading

        return threading.RLock()

    def Event(self):
        import threading

        return threading.Event()


class EventletExecModel(ExecModel):
    backend = "eventlet"

    @property
    def queue(self):
        import eventlet

        return eventlet.queue

    @property
    def subprocess(self):
        import eventlet.green.subprocess

        return eventlet.green.subprocess

    @property
    def socket(self):
        import eventlet.green.socket

        return eventlet.green.socket

    def get_ident(self):
        import eventlet.green.thread

        return eventlet.green.thread.get_ident()

    def sleep(self, delay):
        import eventlet

        eventlet.sleep(delay)

    def start(self, func, args=()):
        import eventlet

        return eventlet.spawn_n(func, *args)

    def fdopen(self, fd, mode, bufsize=1):
        import eventlet.green.os

        return eventlet.green.os.fdopen(fd, mode, bufsize)

    def Lock(self):
        import eventlet.green.threading

        return eventlet.green.threading.RLock()

    def RLock(self):
        import eventlet.green.threading

        return eventlet.green.threading.RLock()

    def Event(self):
        import eventlet.green.threading

        return eventlet.green.threading.Event()


class GeventExecModel(ExecModel):
    backend = "gevent"

    @property
    def queue(self):
        import gevent.queue

        return gevent.queue

    @property
    def subprocess(self):
        import gevent.subprocess

        return gevent.subprocess

    @property
    def socket(self):
        import gevent

        return gevent.socket

    def get_ident(self):
        import gevent.thread

        return gevent.thread.get_ident()

    def sleep(self, delay):
        import gevent

        gevent.sleep(delay)

    def start(self, func, args=()):
        import gevent

        return gevent.spawn(func, *args)

    def fdopen(self, fd, mode, bufsize=1):
        # XXX
        import gevent.fileobject

        return gevent.fileobject.FileObjectThread(fd, mode, bufsize)

    def Lock(self):
        import gevent.lock

        return gevent.lock.RLock()

    def RLock(self):
        import gevent.lock

        return gevent.lock.RLock()

    def Event(self):
        import gevent.event

        return gevent.event.Event()


def get_execmodel(backend):
    if hasattr(backend, "backend"):
        return backend
    if backend == "thread":
        return ThreadExecModel()
    elif backend == "eventlet":
        return EventletExecModel()
    elif backend == "gevent":
        return GeventExecModel()
    else:
        raise ValueError(f"unknown execmodel {backend!r}")


class Reply:
    """reply instances provide access to the result
    of a function execution that got dispatched
    through WorkerPool.spawn()
    """

    def __init__(self, task, threadmodel):
        self.task = task
        self._result_ready = threadmodel.Event()
        self.running = True

    def get(self, timeout=None):
        """get the result object from an asynchronous function execution.
        if the function execution raised an exception,
        then calling get() will reraise that exception
        including its traceback.
        """
        self.waitfinish(timeout)
        try:
            return self._result
        except AttributeError:
            raise self._excinfo[1].with_traceback(self._excinfo[2])

    def waitfinish(self, timeout=None):
        if not self._result_ready.wait(timeout):
            raise OSError(f"timeout waiting for {self.task!r}")

    def run(self):
        func, args, kwargs = self.task
        try:
            try:
                self._result = func(*args, **kwargs)
            except BaseException:
                # sys may be already None when shutting down the interpreter
                if sys is not None:
                    self._excinfo = sys.exc_info()
        finally:
            self._result_ready.set()
            self.running = False


class WorkerPool:
    """A WorkerPool allows to spawn function executions
    to threads, returning a reply object on which you
    can ask for the result (and get exceptions reraised).

    This implementation allows the main thread to integrate
    itself into performing function execution through
    calling integrate_as_primary_thread() which will return
    when the pool received a trigger_shutdown().
    """

    def __init__(self, execmodel, hasprimary=False):
        """by default allow unlimited number of spawns."""
        self.execmodel = execmodel
        self._running_lock = self.execmodel.Lock()
        self._running = set()
        self._shuttingdown = False
        self._waitall_events = []
        if hasprimary:
            if self.execmodel.backend != "thread":
                raise ValueError("hasprimary=True requires thread model")
            self._primary_thread_task_ready = self.execmodel.Event()
        else:
            self._primary_thread_task_ready = None

    def integrate_as_primary_thread(self):
        """integrate the thread with which we are called as a primary
        thread for executing functions triggered with spawn().
        """
        assert self.execmodel.backend == "thread", self.execmodel
        primary_thread_task_ready = self._primary_thread_task_ready
        # interacts with code at REF1
        while 1:
            primary_thread_task_ready.wait()
            reply = self._primary_thread_task
            if reply is None:  # trigger_shutdown() woke us up
                break
            self._perform_spawn(reply)
            # we are concurrent with trigger_shutdown and spawn
            with self._running_lock:
                if self._shuttingdown:
                    break
                primary_thread_task_ready.clear()

    def trigger_shutdown(self):
        with self._running_lock:
            self._shuttingdown = True
            if self._primary_thread_task_ready is not None:
                self._primary_thread_task = None
                self._primary_thread_task_ready.set()

    def active_count(self):
        return len(self._running)

    def _perform_spawn(self, reply):
        reply.run()
        with self._running_lock:
            self._running.remove(reply)
            if not self._running:
                while self._waitall_events:
                    waitall_event = self._waitall_events.pop()
                    waitall_event.set()

    def _try_send_to_primary_thread(self, reply):
        # REF1 in 'thread' model we give priority to running in main thread
        # note that we should be called with _running_lock hold
        primary_thread_task_ready = self._primary_thread_task_ready
        if primary_thread_task_ready is not None:
            if not primary_thread_task_ready.is_set():
                self._primary_thread_task = reply
                # wake up primary thread
                primary_thread_task_ready.set()
                return True
        return False

    def spawn(self, func, *args, **kwargs):
        """return Reply object for the asynchronous dispatch
        of the given func(*args, **kwargs).
        """
        reply = Reply((func, args, kwargs), self.execmodel)
        with self._running_lock:
            if self._shuttingdown:
                raise ValueError("pool is shutting down")
            self._running.add(reply)
            if not self._try_send_to_primary_thread(reply):
                self.execmodel.start(self._perform_spawn, (reply,))
        return reply

    def terminate(self, timeout=None):
        """trigger shutdown and wait for completion of all executions."""
        self.trigger_shutdown()
        return self.waitall(timeout=timeout)

    def waitall(self, timeout=None):
        """wait until all active spawns have finished executing."""
        with self._running_lock:
            if not self._running:
                return True
            # if a Reply still runs, we let run_and_release
            # signal us -- note that we are still holding the
            # _running_lock to avoid race conditions
            my_waitall_event = self.execmodel.Event()
            self._waitall_events.append(my_waitall_event)
        return my_waitall_event.wait(timeout=timeout)


sysex = (KeyboardInterrupt, SystemExit)


DEBUG = os.environ.get("EXECNET_DEBUG")
pid = os.getpid()
if DEBUG == "2":

    def trace(*msg):
        try:
            line = " ".join(map(str, msg))
            sys.stderr.write(f"[{pid}] {line}\n")
            sys.stderr.flush()
        except Exception:
            pass  # nothing we can do, likely interpreter-shutdown

elif DEBUG:
    import tempfile
    import os

    fn = os.path.join(tempfile.gettempdir(), "execnet-debug-%d" % pid)
    # sys.stderr.write("execnet-debug at %r" % (fn,))
    debugfile = open(fn, "w")

    def trace(*msg):
        try:
            line = " ".join(map(str, msg))
            debugfile.write(line + "\n")
            debugfile.flush()
        except Exception:
            try:
                v = sys.exc_info()[1]
                sys.stderr.write(f"[{pid}] exception during tracing: {v!r}\n")
            except Exception:
                pass  # nothing we can do, likely interpreter-shutdown

else:
    notrace = trace = lambda *msg: None


class Popen2IO:
    error = (IOError, OSError, EOFError)

    def __init__(self, outfile, infile, execmodel):
        # we need raw byte streams
        self.outfile, self.infile = outfile, infile
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.setmode(infile.fileno(), os.O_BINARY)
                msvcrt.setmode(outfile.fileno(), os.O_BINARY)
            except (AttributeError, OSError):
                pass
        self._read = getattr(infile, "buffer", infile).read
        self._write = getattr(outfile, "buffer", outfile).write
        self.execmodel = execmodel

    def read(self, numbytes):
        """Read exactly 'numbytes' bytes from the pipe."""
        # a file in non-blocking mode may return less bytes, so we loop
        buf = b""
        while numbytes > len(buf):
            data = self._read(numbytes - len(buf))
            if not data:
                raise EOFError("expected %d bytes, got %d" % (numbytes, len(buf)))
            buf += data
        return buf

    def write(self, data):
        """write out all data bytes."""
        assert isinstance(data, bytes)
        self._write(data)
        self.outfile.flush()

    def close_read(self):
        self.infile.close()

    def close_write(self):
        self.outfile.close()


class Message:
    """encapsulates Messages and their wire protocol."""

    # message code -> name, handler
    _types: dict[int, tuple[str, Callable[[Message, BaseGateway], None]]] = {}

    def __init__(self, msgcode, channelid=0, data=b""):
        self.msgcode = msgcode
        self.channelid = channelid
        self.data = data

    @staticmethod
    def from_io(io):
        try:
            header = io.read(9)  # type 1, channel 4, payload 4
            if not header:
                raise EOFError("empty read")
        except EOFError:
            e = sys.exc_info()[1]
            raise EOFError("couldn't load message header, " + e.args[0])
        msgtype, channel, payload = struct.unpack("!bii", header)
        return Message(msgtype, channel, io.read(payload))

    def to_io(self, io):
        header = struct.pack("!bii", self.msgcode, self.channelid, len(self.data))
        io.write(header + self.data)

    def received(self, gateway):
        handler = self._types[self.msgcode][1]
        handler(self, gateway)

    def __repr__(self):
        name = self._types[self.msgcode][0]
        return "<Message {} channel={} lendata={}>".format(
            name, self.channelid, len(self.data)
        )

    def _status(message, gateway):
        # we use the channelid to send back information
        # but don't instantiate a channel object
        d = {
            "numchannels": len(gateway._channelfactory._channels),
            "numexecuting": gateway._execpool.active_count(),
            "execmodel": gateway.execmodel.backend,
        }
        gateway._send(Message.CHANNEL_DATA, message.channelid, dumps_internal(d))
        gateway._send(Message.CHANNEL_CLOSE, message.channelid)

    STATUS = 0
    _types[STATUS] = ("STATUS", _status)

    def _reconfigure(message, gateway):
        if message.channelid == 0:
            target = gateway
        else:
            target = gateway._channelfactory.new(message.channelid)
        target._strconfig = loads_internal(message.data, gateway)

    RECONFIGURE = 1
    _types[RECONFIGURE] = ("RECONFIGURE", _reconfigure)

    def _gateway_terminate(message, gateway):
        raise GatewayReceivedTerminate(gateway)

    GATEWAY_TERMINATE = 2
    _types[GATEWAY_TERMINATE] = ("GATEWAY_TERMINATE", _gateway_terminate)

    def _channel_exec(message, gateway):
        channel = gateway._channelfactory.new(message.channelid)
        gateway._local_schedulexec(channel=channel, sourcetask=message.data)

    CHANNEL_EXEC = 3
    _types[CHANNEL_EXEC] = ("CHANNEL_EXEC", _channel_exec)

    def _channel_data(message, gateway):
        gateway._channelfactory._local_receive(message.channelid, message.data)

    CHANNEL_DATA = 4
    _types[CHANNEL_DATA] = ("CHANNEL_DATA", _channel_data)

    def _channel_close(message, gateway):
        gateway._channelfactory._local_close(message.channelid)

    CHANNEL_CLOSE = 5
    _types[CHANNEL_CLOSE] = ("CHANNEL_CLOSE", _channel_close)

    def _channel_close_error(message, gateway):
        remote_error = RemoteError(loads_internal(message.data))
        gateway._channelfactory._local_close(message.channelid, remote_error)

    CHANNEL_CLOSE_ERROR = 6
    _types[CHANNEL_CLOSE_ERROR] = ("CHANNEL_CLOSE_ERROR", _channel_close_error)

    def _channel_last_message(message, gateway):
        gateway._channelfactory._local_close(message.channelid, sendonly=True)

    CHANNEL_LAST_MESSAGE = 7
    _types[CHANNEL_LAST_MESSAGE] = ("CHANNEL_LAST_MESSAGE", _channel_last_message)


class GatewayReceivedTerminate(Exception):
    """Receiverthread got termination message."""


def geterrortext(excinfo, format_exception=traceback.format_exception, sysex=sysex):
    try:
        l = format_exception(*excinfo)
        errortext = "".join(l)
    except sysex:
        raise
    except BaseException:
        errortext = f"{excinfo[0].__name__}: {excinfo[1]}"
    return errortext


class RemoteError(Exception):
    """Exception containing a stringified error from the other side."""

    def __init__(self, formatted):
        super().__init__()
        self.formatted = formatted

    def __str__(self):
        return self.formatted

    def __repr__(self):
        return f"{self.__class__.__name__}: {self.formatted}"

    def warn(self):
        if self.formatted != INTERRUPT_TEXT:
            # XXX do this better
            sys.stderr.write(f"[{os.getpid()}] Warning: unhandled {self!r}\n")


class TimeoutError(IOError):
    """Exception indicating that a timeout was reached."""


NO_ENDMARKER_WANTED = object()


class Channel:
    "Communication channel between two Python Interpreter execution points."
    RemoteError = RemoteError
    TimeoutError = TimeoutError
    _INTERNALWAKEUP = 1000
    _executing = False

    def __init__(self, gateway, id):
        assert isinstance(id, int)
        assert not isinstance(gateway, type)
        self.gateway = gateway
        # XXX: defaults copied from Unserializer
        self._strconfig = getattr(gateway, "_strconfig", (True, False))
        self.id = id
        self._items = self.gateway.execmodel.queue.Queue()
        self._closed = False
        self._receiveclosed = self.gateway.execmodel.Event()
        self._remoteerrors = []

    def _trace(self, *msg):
        self.gateway._trace(self.id, *msg)

    def setcallback(self, callback, endmarker=NO_ENDMARKER_WANTED):
        """set a callback function for receiving items.

        All already queued items will immediately trigger the callback.
        Afterwards the callback will execute in the receiver thread
        for each received data item and calls to ``receive()`` will
        raise an error.
        If an endmarker is specified the callback will eventually
        be called with the endmarker when the channel closes.
        """
        _callbacks = self.gateway._channelfactory._callbacks
        with self.gateway._receivelock:
            if self._items is None:
                raise OSError(f"{self!r} has callback already registered")
            items = self._items
            self._items = None
            while 1:
                try:
                    olditem = items.get(block=False)
                except self.gateway.execmodel.queue.Empty:
                    if not (self._closed or self._receiveclosed.is_set()):
                        _callbacks[self.id] = (callback, endmarker, self._strconfig)
                    break
                else:
                    if olditem is ENDMARKER:
                        items.put(olditem)  # for other receivers
                        if endmarker is not NO_ENDMARKER_WANTED:
                            callback(endmarker)
                        break
                    else:
                        callback(olditem)

    def __repr__(self):
        flag = self.isclosed() and "closed" or "open"
        return "<Channel id=%d %s>" % (self.id, flag)

    def __del__(self):
        if self.gateway is None:  # can be None in tests
            return
        self._trace("channel.__del__")
        # no multithreading issues here, because we have the last ref to 'self'
        if self._closed:
            # state transition "closed" --> "deleted"
            for error in self._remoteerrors:
                error.warn()
        elif self._receiveclosed.is_set():
            # state transition "sendonly" --> "deleted"
            # the remote channel is already in "deleted" state, nothing to do
            pass
        else:
            # state transition "opened" --> "deleted"
            # check if we are in the middle of interpreter shutdown
            # in which case the process will go away and we probably
            # don't need to try to send a closing or last message
            # (and often it won't work anymore to send things out)
            if Message is not None:
                if self._items is None:  # has_callback
                    msgcode = Message.CHANNEL_LAST_MESSAGE
                else:
                    msgcode = Message.CHANNEL_CLOSE
                try:
                    self.gateway._send(msgcode, self.id)
                except (OSError, ValueError):  # ignore problems with sending
                    pass

    def _getremoteerror(self):
        try:
            return self._remoteerrors.pop(0)
        except IndexError:
            try:
                return self.gateway._error
            except AttributeError:
                pass
            return None

    #
    # public API for channel objects
    #
    def isclosed(self):
        """return True if the channel is closed. A closed
        channel may still hold items.
        """
        return self._closed

    def makefile(self, mode="w", proxyclose=False):
        """return a file-like object.
        mode can be 'w' or 'r' for writeable/readable files.
        if proxyclose is true file.close() will also close the channel.
        """
        if mode == "w":
            return ChannelFileWrite(channel=self, proxyclose=proxyclose)
        elif mode == "r":
            return ChannelFileRead(channel=self, proxyclose=proxyclose)
        raise ValueError(f"mode {mode!r} not available")

    def close(self, error=None):
        """close down this channel with an optional error message.
        Note that closing of a channel tied to remote_exec happens
        automatically at the end of execution and cannot
        be done explicitly.
        """
        if self._executing:
            raise OSError("cannot explicitly close channel within remote_exec")
        if self._closed:
            self.gateway._trace(self, "ignoring redundant call to close()")
        if not self._closed:
            # state transition "opened/sendonly" --> "closed"
            # threads warning: the channel might be closed under our feet,
            # but it's never damaging to send too many CHANNEL_CLOSE messages
            # however, if the other side triggered a close already, we
            # do not send back a closed message.
            if not self._receiveclosed.is_set():
                put = self.gateway._send
                if error is not None:
                    put(Message.CHANNEL_CLOSE_ERROR, self.id, dumps_internal(error))
                else:
                    put(Message.CHANNEL_CLOSE, self.id)
                self._trace("sent channel close message")
            if isinstance(error, RemoteError):
                self._remoteerrors.append(error)
            self._closed = True  # --> "closed"
            self._receiveclosed.set()
            queue = self._items
            if queue is not None:
                queue.put(ENDMARKER)
            self.gateway._channelfactory._no_longer_opened(self.id)

    def waitclose(self, timeout=None):
        """wait until this channel is closed (or the remote side
        otherwise signalled that no more data was being sent).
        The channel may still hold receiveable items, but not receive
        any more after waitclose() has returned.  Exceptions from executing
        code on the other side are reraised as local channel.RemoteErrors.
        EOFError is raised if the reading-connection was prematurely closed,
        which often indicates a dying process.
        self.TimeoutError is raised after the specified number of seconds
        (default is None, i.e. wait indefinitely).
        """
        # wait for non-"opened" state
        self._receiveclosed.wait(timeout=timeout)
        if not self._receiveclosed.is_set():
            raise self.TimeoutError("Timeout after %r seconds" % timeout)
        error = self._getremoteerror()
        if error:
            raise error

    def send(self, item):
        """sends the given item to the other side of the channel,
        possibly blocking if the sender queue is full.
        The item must be a simple python type and will be
        copied to the other side by value.  IOError is
        raised if the write pipe was prematurely closed.
        """
        if self.isclosed():
            raise OSError(f"cannot send to {self!r}")
        self.gateway._send(Message.CHANNEL_DATA, self.id, dumps_internal(item))

    def receive(self, timeout=None):
        """receive a data item that was sent from the other side.
        timeout: None [default] blocked waiting.  A positive number
        indicates the number of seconds after which a channel.TimeoutError
        exception will be raised if no item was received.
        Note that exceptions from the remotely executing code will be
        reraised as channel.RemoteError exceptions containing
        a textual representation of the remote traceback.
        """
        itemqueue = self._items
        if itemqueue is None:
            raise OSError("cannot receive(), channel has receiver callback")
        try:
            x = itemqueue.get(timeout=timeout)
        except self.gateway.execmodel.queue.Empty:
            raise self.TimeoutError("no item after %r seconds" % timeout)
        if x is ENDMARKER:
            itemqueue.put(x)  # for other receivers
            raise self._getremoteerror() or EOFError()
        else:
            return x

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.receive()
        except EOFError:
            raise StopIteration

    __next__ = next

    def reconfigure(self, py2str_as_py3str=True, py3str_as_py2str=False):
        """
        set the string coercion for this channel
        the default is to try to convert py2 str as py3 str,
        but not to try and convert py3 str to py2 str
        """
        self._strconfig = (py2str_as_py3str, py3str_as_py2str)
        data = dumps_internal(self._strconfig)
        self.gateway._send(Message.RECONFIGURE, self.id, data=data)


ENDMARKER = object()
INTERRUPT_TEXT = "keyboard-interrupted"


class ChannelFactory:
    def __init__(self, gateway, startcount=1):
        self._channels = weakref.WeakValueDictionary()
        self._callbacks = {}
        self._writelock = gateway.execmodel.Lock()
        self.gateway = gateway
        self.count = startcount
        self.finished = False
        self._list = list  # needed during interp-shutdown

    def new(self, id=None):
        """create a new Channel with 'id' (or create new id if None)."""
        with self._writelock:
            if self.finished:
                raise OSError(f"connection already closed: {self.gateway}")
            if id is None:
                id = self.count
                self.count += 2
            try:
                channel = self._channels[id]
            except KeyError:
                channel = self._channels[id] = Channel(self.gateway, id)
            return channel

    def channels(self):
        return self._list(self._channels.values())

    #
    # internal methods, called from the receiver thread
    #
    def _no_longer_opened(self, id):
        try:
            del self._channels[id]
        except KeyError:
            pass
        try:
            callback, endmarker, strconfig = self._callbacks.pop(id)
        except KeyError:
            pass
        else:
            if endmarker is not NO_ENDMARKER_WANTED:
                callback(endmarker)

    def _local_close(self, id, remoteerror=None, sendonly=False):
        channel = self._channels.get(id)
        if channel is None:
            # channel already in "deleted" state
            if remoteerror:
                remoteerror.warn()
            self._no_longer_opened(id)
        else:
            # state transition to "closed" state
            if remoteerror:
                channel._remoteerrors.append(remoteerror)
            queue = channel._items
            if queue is not None:
                queue.put(ENDMARKER)
            self._no_longer_opened(id)
            if not sendonly:  # otherwise #--> "sendonly"
                channel._closed = True  # --> "closed"
            channel._receiveclosed.set()

    def _local_receive(self, id, data):
        # executes in receiver thread
        channel = self._channels.get(id)
        try:
            callback, endmarker, strconfig = self._callbacks[id]
        except KeyError:
            queue = channel and channel._items
            if queue is None:
                pass  # drop data
            else:
                item = loads_internal(data, channel)
                queue.put(item)
        else:
            try:
                data = loads_internal(data, channel, strconfig)
                callback(data)  # even if channel may be already closed
            except Exception:
                excinfo = sys.exc_info()
                self.gateway._trace("exception during callback: %s" % excinfo[1])
                errortext = self.gateway._geterrortext(excinfo)
                self.gateway._send(
                    Message.CHANNEL_CLOSE_ERROR, id, dumps_internal(errortext)
                )
                self._local_close(id, errortext)

    def _finished_receiving(self):
        with self._writelock:
            self.finished = True
        for id in self._list(self._channels):
            self._local_close(id, sendonly=True)
        for id in self._list(self._callbacks):
            self._no_longer_opened(id)


class ChannelFile:
    def __init__(self, channel, proxyclose=True):
        self.channel = channel
        self._proxyclose = proxyclose

    def isatty(self):
        return False

    def close(self):
        if self._proxyclose:
            self.channel.close()

    def __repr__(self):
        state = self.channel.isclosed() and "closed" or "open"
        return "<ChannelFile %d %s>" % (self.channel.id, state)


class ChannelFileWrite(ChannelFile):
    def write(self, out):
        self.channel.send(out)

    def flush(self):
        pass


class ChannelFileRead(ChannelFile):
    def __init__(self, channel, proxyclose=True):
        super().__init__(channel, proxyclose)
        self._buffer = None

    def read(self, n):
        try:
            if self._buffer is None:
                self._buffer = self.channel.receive()
            while len(self._buffer) < n:
                self._buffer += self.channel.receive()
        except EOFError:
            self.close()
        if self._buffer is None:
            ret = ""
        else:
            ret = self._buffer[:n]
            self._buffer = self._buffer[n:]
        return ret

    def readline(self):
        if self._buffer is not None:
            i = self._buffer.find("\n")
            if i != -1:
                return self.read(i + 1)
            line = self.read(len(self._buffer) + 1)
        else:
            line = self.read(1)
        while line and line[-1] != "\n":
            c = self.read(1)
            if not c:
                break
            line += c
        return line


class BaseGateway:
    exc_info = sys.exc_info
    _sysex = sysex
    id = "<worker>"

    def __init__(self, io, id, _startcount=2):
        self.execmodel = io.execmodel
        self._io = io
        self.id = id
        self._strconfig = (Unserializer.py2str_as_py3str, Unserializer.py3str_as_py2str)
        self._channelfactory = ChannelFactory(self, _startcount)
        self._receivelock = self.execmodel.RLock()
        # globals may be NONE at process-termination
        self.__trace = trace
        self._geterrortext = geterrortext
        self._receivepool = WorkerPool(self.execmodel)

    def _trace(self, *msg):
        self.__trace(self.id, *msg)

    def _initreceive(self):
        self._receivepool.spawn(self._thread_receiver)

    def _thread_receiver(self):
        def log(*msg):
            self._trace("[receiver-thread]", *msg)

        log("RECEIVERTHREAD: starting to run")
        io = self._io
        try:
            while 1:
                msg = Message.from_io(io)
                log("received", msg)
                with self._receivelock:
                    msg.received(self)
                    del msg
        except (KeyboardInterrupt, GatewayReceivedTerminate):
            pass
        except EOFError:
            log("EOF without prior gateway termination message")
            self._error = self.exc_info()[1]
        except Exception:
            log(self._geterrortext(self.exc_info()))
        log("finishing receiving thread")
        # wake up and terminate any execution waiting to receive
        self._channelfactory._finished_receiving()
        log("terminating execution")
        self._terminate_execution()
        log("closing read")
        self._io.close_read()
        log("closing write")
        self._io.close_write()
        log("terminating our receive pseudo pool")
        self._receivepool.trigger_shutdown()

    def _terminate_execution(self):
        pass

    def _send(self, msgcode, channelid=0, data=b""):
        message = Message(msgcode, channelid, data)
        try:
            message.to_io(self._io)
            self._trace("sent", message)
        except (OSError, ValueError):
            e = sys.exc_info()[1]
            self._trace("failed to send", message, e)
            # ValueError might be because the IO is already closed
            raise OSError("cannot send (already closed?)")

    def _local_schedulexec(self, channel, sourcetask):
        channel.close("execution disallowed")

    # _____________________________________________________________________
    #
    # High Level Interface
    # _____________________________________________________________________
    #
    def newchannel(self):
        """return a new independent channel."""
        return self._channelfactory.new()

    def join(self, timeout=None):
        """Wait for receiverthread to terminate."""
        self._trace("waiting for receiver thread to finish")
        self._receivepool.waitall()


class WorkerGateway(BaseGateway):
    def _local_schedulexec(self, channel, sourcetask):
        sourcetask = loads_internal(sourcetask)
        self._execpool.spawn(self.executetask, (channel, sourcetask))

    def _terminate_execution(self):
        # called from receiverthread
        self._trace("shutting down execution pool")
        self._execpool.trigger_shutdown()
        if not self._execpool.waitall(5.0):
            self._trace("execution ongoing after 5 secs," " trying interrupt_main")
            # We try hard to terminate execution based on the assumption
            # that there is only one gateway object running per-process.
            if sys.platform != "win32":
                self._trace("sending ourselves a SIGINT")
                os.kill(os.getpid(), 2)  # send ourselves a SIGINT
            elif interrupt_main is not None:
                self._trace("calling interrupt_main()")
                interrupt_main()
            if not self._execpool.waitall(10.0):
                self._trace(
                    "execution did not finish in another 10 secs, " "calling os._exit()"
                )
                os._exit(1)

    def serve(self):
        def trace(msg):
            self._trace("[serve] " + msg)

        hasprimary = self.execmodel.backend == "thread"
        self._execpool = WorkerPool(self.execmodel, hasprimary=hasprimary)
        trace("spawning receiver thread")
        self._initreceive()
        try:
            if hasprimary:
                # this will return when we are in shutdown
                trace("integrating as primary thread")
                self._execpool.integrate_as_primary_thread()
            trace("joining receiver thread")
            self.join()
        except KeyboardInterrupt:
            # in the worker we can't really do anything sensible
            trace("swallowing keyboardinterrupt, serve finished")

    def executetask(self, item):
        try:
            channel, (source, file_name, call_name, kwargs) = item
            loc = {"channel": channel, "__name__": "__channelexec__"}
            self._trace(f"execution starts[{channel.id}]: {repr(source)[:50]}")
            channel._executing = True
            try:
                co = compile(source + "\n", file_name or "<remote exec>", "exec")
                exec(co, loc)
                if call_name:
                    self._trace("calling %s(**%60r)" % (call_name, kwargs))
                    function = loc[call_name]
                    function(channel, **kwargs)
            finally:
                channel._executing = False
                self._trace("execution finished")
        except KeyboardInterrupt:
            channel.close(INTERRUPT_TEXT)
            raise
        except BaseException:
            excinfo = self.exc_info()
            if not isinstance(excinfo[1], EOFError):
                if not channel.gateway._channelfactory.finished:
                    self._trace(f"got exception: {excinfo[1]!r}")
                    errortext = self._geterrortext(excinfo)
                    channel.close(errortext)
                    return
            self._trace("ignoring EOFError because receiving finished")
        channel.close()


#
# Cross-Python pickling code, tested from test_serializer.py
#


class DataFormatError(Exception):
    pass


class DumpError(DataFormatError):
    """Error while serializing an object."""


class LoadError(DataFormatError):
    """Error while unserializing an object."""


def bchr(n):
    return bytes([n])


DUMPFORMAT_VERSION = bchr(2)

FOUR_BYTE_INT_MAX = 2147483647

FLOAT_FORMAT = "!d"
FLOAT_FORMAT_SIZE = struct.calcsize(FLOAT_FORMAT)
COMPLEX_FORMAT = "!dd"
COMPLEX_FORMAT_SIZE = struct.calcsize(COMPLEX_FORMAT)


class _Stop(Exception):
    pass


class opcode:
    """container for name -> num mappings."""

    BUILDTUPLE = b"@"
    BYTES = b"A"
    CHANNEL = b"B"
    FALSE = b"C"
    FLOAT = b"D"
    FROZENSET = b"E"
    INT = b"F"
    LONG = b"G"
    LONGINT = b"H"
    LONGLONG = b"I"
    NEWDICT = b"J"
    NEWLIST = b"K"
    NONE = b"L"
    PY2STRING = b"M"
    PY3STRING = b"N"
    SET = b"O"
    SETITEM = b"P"
    STOP = b"Q"
    TRUE = b"R"
    UNICODE = b"S"
    COMPLEX = b"T"


class Unserializer:
    num2func: dict[bytes, Callable[[Unserializer], None]] = {}
    py2str_as_py3str = True  # True
    py3str_as_py2str = False  # false means py2 will get unicode

    def __init__(self, stream, channel_or_gateway=None, strconfig=None):
        gateway = getattr(channel_or_gateway, "gateway", channel_or_gateway)
        strconfig = getattr(channel_or_gateway, "_strconfig", strconfig)
        if strconfig:
            self.py2str_as_py3str, self.py3str_as_py2str = strconfig
        self.stream = stream
        self.channelfactory = getattr(gateway, "_channelfactory", gateway)

    def load(self, versioned=False):
        if versioned:
            ver = self.stream.read(1)
            if ver != DUMPFORMAT_VERSION:
                raise LoadError("wrong dumpformat version %r" % ver)
        self.stack = []
        try:
            while True:
                opcode = self.stream.read(1)
                if not opcode:
                    raise EOFError
                try:
                    loader = self.num2func[opcode]
                except KeyError:
                    raise LoadError(
                        "unknown opcode %r - " "wire protocol corruption?" % (opcode,)
                    )
                loader(self)
        except _Stop:
            if len(self.stack) != 1:
                raise LoadError("internal unserialization error")
            return self.stack.pop(0)
        else:
            raise LoadError("didn't get STOP")

    def load_none(self):
        self.stack.append(None)

    num2func[opcode.NONE] = load_none

    def load_true(self):
        self.stack.append(True)

    num2func[opcode.TRUE] = load_true

    def load_false(self):
        self.stack.append(False)

    num2func[opcode.FALSE] = load_false

    def load_int(self):
        i = self._read_int4()
        self.stack.append(i)

    num2func[opcode.INT] = load_int

    def load_longint(self):
        s = self._read_byte_string()
        self.stack.append(int(s))

    num2func[opcode.LONGINT] = load_longint

    load_long = load_int
    num2func[opcode.LONG] = load_long
    load_longlong = load_longint
    num2func[opcode.LONGLONG] = load_longlong

    def load_float(self):
        binary = self.stream.read(FLOAT_FORMAT_SIZE)
        self.stack.append(struct.unpack(FLOAT_FORMAT, binary)[0])

    num2func[opcode.FLOAT] = load_float

    def load_complex(self):
        binary = self.stream.read(COMPLEX_FORMAT_SIZE)
        self.stack.append(complex(*struct.unpack(COMPLEX_FORMAT, binary)))

    num2func[opcode.COMPLEX] = load_complex

    def _read_int4(self):
        return struct.unpack("!i", self.stream.read(4))[0]

    def _read_byte_string(self):
        length = self._read_int4()
        as_bytes = self.stream.read(length)
        return as_bytes

    def load_py3string(self):
        as_bytes = self._read_byte_string()
        if self.py3str_as_py2str:
            # XXX Should we try to decode into latin-1?
            self.stack.append(as_bytes)
        else:
            self.stack.append(as_bytes.decode("utf-8"))

    num2func[opcode.PY3STRING] = load_py3string

    def load_py2string(self):
        as_bytes = self._read_byte_string()
        if self.py2str_as_py3str:
            s = as_bytes.decode("latin-1")
        else:
            s = as_bytes
        self.stack.append(s)

    num2func[opcode.PY2STRING] = load_py2string

    def load_bytes(self):
        s = self._read_byte_string()
        self.stack.append(s)

    num2func[opcode.BYTES] = load_bytes

    def load_unicode(self):
        self.stack.append(self._read_byte_string().decode("utf-8"))

    num2func[opcode.UNICODE] = load_unicode

    def load_newlist(self):
        length = self._read_int4()
        self.stack.append([None] * length)

    num2func[opcode.NEWLIST] = load_newlist

    def load_setitem(self):
        if len(self.stack) < 3:
            raise LoadError("not enough items for setitem")
        value = self.stack.pop()
        key = self.stack.pop()
        self.stack[-1][key] = value

    num2func[opcode.SETITEM] = load_setitem

    def load_newdict(self):
        self.stack.append({})

    num2func[opcode.NEWDICT] = load_newdict

    def _load_collection(self, type_):
        length = self._read_int4()
        if length:
            res = type_(self.stack[-length:])
            del self.stack[-length:]
            self.stack.append(res)
        else:
            self.stack.append(type_())

    def load_buildtuple(self):
        self._load_collection(tuple)

    num2func[opcode.BUILDTUPLE] = load_buildtuple

    def load_set(self):
        self._load_collection(set)

    num2func[opcode.SET] = load_set

    def load_frozenset(self):
        self._load_collection(frozenset)

    num2func[opcode.FROZENSET] = load_frozenset

    def load_stop(self):
        raise _Stop

    num2func[opcode.STOP] = load_stop

    def load_channel(self):
        id = self._read_int4()
        newchannel = self.channelfactory.new(id)
        self.stack.append(newchannel)

    num2func[opcode.CHANNEL] = load_channel


def dumps(obj):
    """return a serialized bytestring of the given obj.

    The obj and all contained objects must be of a builtin
    python type (so nested dicts, sets, etc. are all ok but
    not user-level instances).
    """
    return _Serializer().save(obj, versioned=True)


def dump(byteio, obj):
    """write a serialized bytestring of the given obj to the given stream."""
    _Serializer(write=byteio.write).save(obj, versioned=True)


def loads(bytestring, py2str_as_py3str=False, py3str_as_py2str=False):
    """return the object as deserialized from the given bytestring.

    py2str_as_py3str: if true then string (str) objects previously
                      dumped on Python2 will be loaded as Python3
                      strings which really are text objects.
    py3str_as_py2str: if true then string (str) objects previously
                      dumped on Python3 will be loaded as Python2
                      strings instead of unicode objects.

    if the bytestring was dumped with an incompatible protocol
    version or if the bytestring is corrupted, the
    ``execnet.DataFormatError`` will be raised.
    """
    io = BytesIO(bytestring)
    return load(
        io, py2str_as_py3str=py2str_as_py3str, py3str_as_py2str=py3str_as_py2str
    )


def load(io, py2str_as_py3str=False, py3str_as_py2str=False):
    """derserialize an object form the specified stream.

    Behaviour and parameters are otherwise the same as with ``loads``
    """
    strconfig = (py2str_as_py3str, py3str_as_py2str)
    return Unserializer(io, strconfig=strconfig).load(versioned=True)


def loads_internal(bytestring, channelfactory=None, strconfig=None):
    io = BytesIO(bytestring)
    return Unserializer(io, channelfactory, strconfig).load()


def dumps_internal(obj):
    return _Serializer().save(obj)


class _Serializer:
    _dispatch: dict[type, Callable[[_Serializer, object], None]] = {}

    def __init__(self, write=None):
        if write is None:
            self._streamlist = []
            write = self._streamlist.append
        self._write = write

    def save(self, obj, versioned=False):
        # calling here is not re-entrant but multiple instances
        # may write to the same stream because of the common platform
        # atomic-write guarantee (concurrent writes each happen atomically)
        if versioned:
            self._write(DUMPFORMAT_VERSION)
        self._save(obj)
        self._write(opcode.STOP)
        try:
            streamlist = self._streamlist
        except AttributeError:
            return None
        return b"".join(streamlist)

    def _save(self, obj):
        tp = type(obj)
        try:
            dispatch = self._dispatch[tp]
        except KeyError:
            methodname = "save_" + tp.__name__
            meth = getattr(self.__class__, methodname, None)
            if meth is None:
                raise DumpError(f"can't serialize {tp}")
            dispatch = self._dispatch[tp] = meth
        dispatch(self, obj)

    def save_NoneType(self, non):
        self._write(opcode.NONE)

    def save_bool(self, boolean):
        if boolean:
            self._write(opcode.TRUE)
        else:
            self._write(opcode.FALSE)

    def save_bytes(self, bytes_):
        self._write(opcode.BYTES)
        self._write_byte_sequence(bytes_)

    def save_str(self, s):
        self._write(opcode.PY3STRING)
        self._write_unicode_string(s)

    def _write_unicode_string(self, s):
        try:
            as_bytes = s.encode("utf-8")
        except UnicodeEncodeError:
            raise DumpError("strings must be utf-8 encodable")
        self._write_byte_sequence(as_bytes)

    def _write_byte_sequence(self, bytes_):
        self._write_int4(len(bytes_), "string is too long")
        self._write(bytes_)

    def _save_integral(self, i, short_op, long_op):
        if i <= FOUR_BYTE_INT_MAX:
            self._write(short_op)
            self._write_int4(i)
        else:
            self._write(long_op)
            self._write_byte_sequence(str(i).rstrip("L").encode("ascii"))

    def save_int(self, i):
        self._save_integral(i, opcode.INT, opcode.LONGINT)

    def save_long(self, l):
        self._save_integral(l, opcode.LONG, opcode.LONGLONG)

    def save_float(self, flt):
        self._write(opcode.FLOAT)
        self._write(struct.pack(FLOAT_FORMAT, flt))

    def save_complex(self, cpx):
        self._write(opcode.COMPLEX)
        self._write(struct.pack(COMPLEX_FORMAT, cpx.real, cpx.imag))

    def _write_int4(self, i, error="int must be less than %i" % (FOUR_BYTE_INT_MAX,)):
        if i > FOUR_BYTE_INT_MAX:
            raise DumpError(error)
        self._write(struct.pack("!i", i))

    def save_list(self, L):
        self._write(opcode.NEWLIST)
        self._write_int4(len(L), "list is too long")
        for i, item in enumerate(L):
            self._write_setitem(i, item)

    def _write_setitem(self, key, value):
        self._save(key)
        self._save(value)
        self._write(opcode.SETITEM)

    def save_dict(self, d):
        self._write(opcode.NEWDICT)
        for key, value in d.items():
            self._write_setitem(key, value)

    def save_tuple(self, tup):
        for item in tup:
            self._save(item)
        self._write(opcode.BUILDTUPLE)
        self._write_int4(len(tup), "tuple is too long")

    def _write_set(self, s, op):
        for item in s:
            self._save(item)
        self._write(op)
        self._write_int4(len(s), "set is too long")

    def save_set(self, s):
        self._write_set(s, opcode.SET)

    def save_frozenset(self, s):
        self._write_set(s, opcode.FROZENSET)

    def save_Channel(self, channel):
        self._write(opcode.CHANNEL)
        self._write_int4(channel.id)


def init_popen_io(execmodel):
    if not hasattr(os, "dup"):  # jython
        io = Popen2IO(sys.stdout, sys.stdin, execmodel)
        import tempfile

        sys.stdin = tempfile.TemporaryFile("r")
        sys.stdout = tempfile.TemporaryFile("w")
    else:
        try:
            devnull = os.devnull
        except AttributeError:
            if os.name == "nt":
                devnull = "NUL"
            else:
                devnull = "/dev/null"
        # stdin
        stdin = execmodel.fdopen(os.dup(0), "r", 1)
        fd = os.open(devnull, os.O_RDONLY)
        os.dup2(fd, 0)
        os.close(fd)

        # stdout
        stdout = execmodel.fdopen(os.dup(1), "w", 1)
        fd = os.open(devnull, os.O_WRONLY)
        os.dup2(fd, 1)

        # stderr for win32
        if os.name == "nt":
            sys.stderr = execmodel.fdopen(os.dup(2), "w", 1)
            os.dup2(fd, 2)
        os.close(fd)
        io = Popen2IO(stdout, stdin, execmodel)
        sys.stdin = execmodel.fdopen(0, "r", 1)
        sys.stdout = execmodel.fdopen(1, "w", 1)
    return io


def serve(io, id):
    trace(f"creating workergateway on {io!r}")
    WorkerGateway(io=io, id=id, _startcount=2).serve()
