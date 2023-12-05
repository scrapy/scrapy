#   Id: asyncore.py,v 2.51 2000/09/07 22:29:26 rushing Exp
#   Author: Sam Rushing <rushing@nightmare.com>

# ======================================================================
# Copyright 1996 by Sam Rushing
#
#                         All Rights Reserved
#
# Permission to use, copy, modify, and distribute this software and
# its documentation for any purpose and without fee is hereby
# granted, provided that the above copyright notice appear in all
# copies and that both that copyright notice and this permission
# notice appear in supporting documentation, and that the name of Sam
# Rushing not be used in advertising or publicity pertaining to
# distribution of the software without specific, written prior
# permission.
#
# SAM RUSHING DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
# NO EVENT SHALL SAM RUSHING BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
# ======================================================================


import os
import select
import socket
import sys
import time
import warnings
from errno import EAGAIN
from errno import EALREADY
from errno import EBADF
from errno import ECONNABORTED
from errno import ECONNRESET
from errno import EINPROGRESS
from errno import EINVAL
from errno import EISCONN
from errno import ENOTCONN
from errno import EPIPE
from errno import ESHUTDOWN
from errno import EWOULDBLOCK
from errno import errorcode


_DISCONNECTED = frozenset(
    {ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED, EPIPE, EBADF})


socket_map = {}


def _strerror(err):
    try:
        return os.strerror(err)
    except (ValueError, OverflowError, NameError):
        if err in errorcode:
            return errorcode[err]
        return "Unknown error %s" % err


_reraised_exceptions = (KeyboardInterrupt, SystemExit)


def read(obj):
    try:
        obj.handle_read_event()
    except _reraised_exceptions:
        raise
    except Exception:
        obj.handle_error()


def write(obj):
    try:
        obj.handle_write_event()
    except _reraised_exceptions:
        raise
    except Exception:
        obj.handle_error()


def _exception(obj):
    try:
        obj.handle_expt_event()
    except _reraised_exceptions:
        raise
    except Exception:
        obj.handle_error()


def readwrite(obj, flags):
    try:
        if flags & select.POLLIN:
            obj.handle_read_event()
        if flags & select.POLLOUT:
            obj.handle_write_event()
        if flags & select.POLLPRI:
            obj.handle_expt_event()
        if flags & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
            obj.handle_close()
    except OSError as e:
        if e.errno not in _DISCONNECTED:
            obj.handle_error()
        else:
            obj.handle_close()
    except _reraised_exceptions:
        raise
    except Exception:
        obj.handle_error()


def poll(timeout=0.0, map=None):
    if map is None:
        map = socket_map
    if map:
        r = []
        w = []
        e = []
        for fd, obj in list(map.items()):
            is_r = obj.readable()
            is_w = obj.writable()
            if is_r:
                r.append(fd)
            if is_w and not obj.accepting:
                w.append(fd)
            if is_r or is_w:
                e.append(fd)
        if [] == r == w == e:
            time.sleep(timeout)
            return

        r, w, e = select.select(r, w, e, timeout)

        for fd in r:
            obj = map.get(fd)
            if obj is None:
                continue
            read(obj)

        for fd in w:
            obj = map.get(fd)
            if obj is None:
                continue
            write(obj)

        for fd in e:
            obj = map.get(fd)
            if obj is None:
                continue
            _exception(obj)


def poll2(timeout=0.0, map=None):
    if map is None:
        map = socket_map
    if timeout is not None:
        timeout = int(timeout * 1000)
    pollster = select.poll()
    if map:
        for fd, obj in list(map.items()):
            flags = 0
            if obj.readable():
                flags |= select.POLLIN | select.POLLPRI
            if obj.writable() and not obj.accepting:
                flags |= select.POLLOUT
            if flags:
                pollster.register(fd, flags)

        r = pollster.poll(timeout)
        for fd, flags in r:
            obj = map.get(fd)
            if obj is None:
                continue
            readwrite(obj, flags)


poll3 = poll2                           # Alias for backward compatibility


def loop(timeout=30.0, use_poll=False, map=None, count=None):
    if map is None:
        map = socket_map

    poll_fun = poll2 if use_poll and hasattr(select, "poll") else poll

    if count is None:
        while map:
            poll_fun(timeout, map)

    else:
        while map and count > 0:
            poll_fun(timeout, map)
            count = count - 1


class dispatcher:

    debug = False
    connected = False
    accepting = False
    connecting = False
    closing = False
    addr = None
    ignore_log_types = frozenset({'warning'})

    def __init__(self, sock=None, map=None):
        if map is None:
            self._map = socket_map
        else:
            self._map = map

        self._fileno = None

        if sock:
            sock.setblocking(False)
            self.set_socket(sock, map)
            self.connected = True
            try:
                self.addr = sock.getpeername()
            except OSError as err:
                if err.errno in (ENOTCONN, EINVAL):
                    self.connected = False
                else:
                    self.del_channel(map)
                    raise
        else:
            self.socket = None

    def __repr__(self):
        status = [self.__class__.__module__ +
                  "." + self.__class__.__qualname__]
        if self.accepting and self.addr:
            status.append('listening')
        elif self.connected:
            status.append('connected')
        if self.addr is not None:
            try:
                status.append('%s:%d' % self.addr)
            except TypeError:
                status.append(repr(self.addr))
        return '<%s at %#x>' % (' '.join(status), id(self))

    def add_channel(self, map=None):
        # self.log_info('adding channel %s' % self)
        if map is None:
            map = self._map
        map[self._fileno] = self

    def del_channel(self, map=None):
        fd = self._fileno
        if map is None:
            map = self._map
        if fd in map:
            del map[fd]
        self._fileno = None

    def create_socket(self, family=socket.AF_INET, type=socket.SOCK_STREAM):
        self.family_and_type = family, type
        sock = socket.socket(family, type)
        sock.setblocking(False)
        self.set_socket(sock)

    def set_socket(self, sock, map=None):
        self.socket = sock
        self._fileno = sock.fileno()
        self.add_channel(map)

    def set_reuse_addr(self):
        try:
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR,
                self.socket.getsockopt(socket.SOL_SOCKET,
                                       socket.SO_REUSEADDR) | 1
            )
        except OSError:
            pass

    def readable(self):
        return True

    def writable(self):
        return True

    def listen(self, num):
        self.accepting = True
        if os.name == 'nt' and num > 5:
            num = 5
        return self.socket.listen(num)

    def bind(self, addr):
        self.addr = addr
        return self.socket.bind(addr)

    def connect(self, address):
        self.connected = False
        self.connecting = True
        err = self.socket.connect_ex(address)
        if err in (EINPROGRESS, EALREADY, EWOULDBLOCK) \
                or err == EINVAL and os.name == 'nt':
            self.addr = address
            return
        if err in (0, EISCONN):
            self.addr = address
            self.handle_connect_event()
        else:
            raise OSError(err, errorcode[err])

    def accept(self):
        try:
            conn, addr = self.socket.accept()
        except TypeError:
            return None
        except OSError as why:
            if why.errno in (EWOULDBLOCK, ECONNABORTED, EAGAIN):
                return None
            else:
                raise
        else:
            return conn, addr

    def send(self, data):
        try:
            result = self.socket.send(data)
            return result
        except OSError as why:
            if why.errno == EWOULDBLOCK:
                return 0
            elif why.errno in _DISCONNECTED:
                self.handle_close()
                return 0
            else:
                raise

    def recv(self, buffer_size):
        try:
            data = self.socket.recv(buffer_size)
            if not data:
                self.handle_close()
                return b''
            else:
                return data
        except OSError as why:
            if why.errno in _DISCONNECTED:
                self.handle_close()
                return b''
            else:
                raise

    def close(self):
        self.connected = False
        self.accepting = False
        self.connecting = False
        self.del_channel()
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError as why:
                if why.errno not in (ENOTCONN, EBADF):
                    raise

    def log(self, message):
        sys.stderr.write('log: %s\n' % str(message))

    def log_info(self, message, type='info'):
        if type not in self.ignore_log_types:
            print('%s: %s' % (type, message))  # noqa

    def handle_read_event(self):
        if self.accepting:
            # accepting sockets are never connected, they "spawn" new
            # sockets that are connected
            self.handle_accept()
        elif not self.connected:
            if self.connecting:
                self.handle_connect_event()
            self.handle_read()
        else:
            self.handle_read()

    def handle_connect_event(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise OSError(err, _strerror(err))
        self.handle_connect()
        self.connected = True
        self.connecting = False

    def handle_write_event(self):
        if self.accepting:
            return

        if not self.connected and self.connecting:
            self.handle_connect_event()
        self.handle_write()

    def handle_expt_event(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            self.handle_close()
        else:
            self.handle_expt()

    def handle_error(self):
        nil, t, v, tbinfo = compact_traceback()
        try:
            self_repr = repr(self)
        except Exception:
            self_repr = '<__repr__(self) failed for object at %0x>' % id(self)

        self.log_info(
            'uncaptured python exception, closing channel %s (%s:%s %s)' % (
                self_repr,
                t,
                v,
                tbinfo
            ),
            'error'
        )
        self.handle_close()

    def handle_expt(self):
        self.log_info('unhandled incoming priority event', 'warning')

    def handle_read(self):
        self.log_info('unhandled read event', 'warning')

    def handle_write(self):
        self.log_info('unhandled write event', 'warning')

    def handle_connect(self):
        self.log_info('unhandled connect event', 'warning')

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            self.handle_accepted(*pair)

    def handle_accepted(self, sock, addr):
        sock.close()
        self.log_info('unhandled accepted event', 'warning')

    def handle_close(self):
        self.log_info('unhandled close event', 'warning')
        self.close()


class dispatcher_with_send(dispatcher):

    def __init__(self, sock=None, map=None):
        dispatcher.__init__(self, sock, map)
        self.out_buffer = b''

    def initiate_send(self):
        num_sent = 0
        num_sent = dispatcher.send(self, self.out_buffer[:65536])
        self.out_buffer = self.out_buffer[num_sent:]

    def handle_write(self):
        self.initiate_send()

    def writable(self):
        return (not self.connected) or len(self.out_buffer)

    def send(self, data):
        if self.debug:
            self.log_info('sending %s' % repr(data))
        self.out_buffer = self.out_buffer + data
        self.initiate_send()

# ---------------------------------------------------------------------------
# used for debugging.
# ---------------------------------------------------------------------------


def compact_traceback():
    t, v, tb = sys.exc_info()
    tbinfo = []
    if not tb:  # Must have a traceback
        raise AssertionError("traceback does not exist")
    while tb:
        tbinfo.append((
            tb.tb_frame.f_code.co_filename,
            tb.tb_frame.f_code.co_name,
            str(tb.tb_lineno)
        ))
        tb = tb.tb_next

    # just to be safe
    del tb

    file, function, line = tbinfo[-1]
    info = ' '.join(['[%s|%s|%s]' % x for x in tbinfo])
    return (file, function, line), t, v, info


def close_all(map=None, ignore_all=False):
    if map is None:
        map = socket_map
    for x in list(map.values()):
        try:
            x.close()
        except OSError as x:
            if x.errno == EBADF:
                pass
            elif not ignore_all:
                raise
        except _reraised_exceptions:
            raise
        except Exception:
            if not ignore_all:
                raise
    map.clear()


if os.name == 'posix':
    class file_wrapper:
        # Here we override just enough to make a file
        # look like a socket for the purposes of asyncore.
        # The passed fd is automatically os.dup()'d

        def __init__(self, fd):
            self.fd = os.dup(fd)

        def __del__(self):
            if self.fd >= 0:
                warnings.warn("unclosed file %r" % self, ResourceWarning,
                              source=self, stacklevel=2)
            self.close()

        def recv(self, *args):
            return os.read(self.fd, *args)

        def send(self, *args):
            return os.write(self.fd, *args)

        def getsockopt(self, level, optname, buflen=None):
            if (level == socket.SOL_SOCKET and
                optname == socket.SO_ERROR and
                    not buflen):
                return 0
            raise NotImplementedError("Only asyncore specific behaviour "
                                      "implemented.")

        read = recv
        write = send

        def close(self):
            if self.fd < 0:
                return
            fd = self.fd
            self.fd = -1
            os.close(fd)

        def fileno(self):
            return self.fd

    class file_dispatcher(dispatcher):

        def __init__(self, fd, map=None):
            dispatcher.__init__(self, None, map)
            self.connected = True
            try:
                fd = fd.fileno()
            except AttributeError:
                pass
            self.set_file(fd)
            # set it to non-blocking mode
            os.set_blocking(fd, False)

        def set_file(self, fd):
            self.socket = file_wrapper(fd)
            self._fileno = self.socket.fileno()
            self.add_channel()
