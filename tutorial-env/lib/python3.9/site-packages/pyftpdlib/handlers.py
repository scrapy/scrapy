# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import contextlib
import errno
import glob
import logging
import os
import random
import socket
import sys
import time
import traceback
import warnings
from datetime import datetime


try:
    import grp
    import pwd
except ImportError:
    pwd = grp = None

try:
    from OpenSSL import SSL  # requires "pip install pyopenssl"
except ImportError:
    SSL = None

try:
    from collections import OrderedDict  # python >= 2.7
except ImportError:
    OrderedDict = dict

from . import __ver__
from ._compat import PY3
from ._compat import b
from ._compat import getcwdu
from ._compat import super
from ._compat import u
from ._compat import unicode
from ._compat import xrange
from .authorizers import AuthenticationFailed
from .authorizers import AuthorizerError
from .authorizers import DummyAuthorizer
from .filesystems import AbstractedFS
from .filesystems import FilesystemError
from .ioloop import _ERRNOS_DISCONNECTED
from .ioloop import _ERRNOS_RETRY
from .ioloop import Acceptor
from .ioloop import AsyncChat
from .ioloop import Connector
from .ioloop import RetryError
from .ioloop import timer
from .log import debug
from .log import logger


if sys.version_info[:2] >= (3, 12):
    from . import _asynchat as asynchat
else:
    import asynchat


CR_BYTE = ord('\r')


def _import_sendfile():
    # By default attempt to use os.sendfile introduced in Python 3.3:
    # http://bugs.python.org/issue10882
    # ...otherwise fallback on using third-party pysendfile module:
    # https://github.com/giampaolo/pysendfile/
    if os.name == 'posix':
        try:
            return os.sendfile  # py >= 3.3
        except AttributeError:
            try:
                import sendfile as sf

                # dirty hack to detect whether old 1.2.4 version is installed
                if hasattr(sf, 'has_sf_hdtr'):
                    raise ImportError
                return sf.sendfile
            except ImportError:
                pass
    return None


sendfile = _import_sendfile()

proto_cmds = {
    'ABOR': dict(
        perm=None, auth=True, arg=False,
        help='Syntax: ABOR (abort transfer).'),
    'ALLO': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: ALLO <SP> bytes (noop; allocate storage).'),
    'APPE': dict(
        perm='a', auth=True, arg=True,
        help='Syntax: APPE <SP> file-name (append data to file).'),
    'CDUP': dict(
        perm='e', auth=True, arg=False,
        help='Syntax: CDUP (go to parent directory).'),
    'CWD': dict(
        perm='e', auth=True, arg=None,
        help='Syntax: CWD [<SP> dir-name] (change working directory).'),
    'DELE': dict(
        perm='d', auth=True, arg=True,
        help='Syntax: DELE <SP> file-name (delete file).'),
    'EPRT': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: EPRT <SP> |proto|ip|port| (extended active mode).'),
    'EPSV': dict(
        perm=None, auth=True, arg=None,
        help='Syntax: EPSV [<SP> proto/"ALL"] (extended passive mode).'),
    'FEAT': dict(
        perm=None, auth=False, arg=False,
        help='Syntax: FEAT (list all new features supported).'),
    'HELP': dict(
        perm=None, auth=False, arg=None,
        help='Syntax: HELP [<SP> cmd] (show help).'),
    'LIST': dict(
        perm='l', auth=True, arg=None,
        help='Syntax: LIST [<SP> path] (list files).'),
    'MDTM': dict(
        perm='l', auth=True, arg=True,
        help='Syntax: MDTM [<SP> path] (file last modification time).'),
    'MFMT': dict(
        perm='T', auth=True, arg=True,
        help='Syntax: MFMT <SP> timeval <SP> path (file update last '
             'modification time).'),
    'MLSD': dict(
        perm='l', auth=True, arg=None,
        help='Syntax: MLSD [<SP> path] (list directory).'),
    'MLST': dict(
        perm='l', auth=True, arg=None,
        help='Syntax: MLST [<SP> path] (show information about path).'),
    'MODE': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: MODE <SP> mode (noop; set data transfer mode).'),
    'MKD': dict(
        perm='m', auth=True, arg=True,
        help='Syntax: MKD <SP> path (create directory).'),
    'NLST': dict(
        perm='l', auth=True, arg=None,
        help='Syntax: NLST [<SP> path] (list path in a compact form).'),
    'NOOP': dict(
        perm=None, auth=False, arg=False,
        help='Syntax: NOOP (just do nothing).'),
    'OPTS': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: OPTS <SP> cmd [<SP> option] (set option for command).'),
    'PASS': dict(
        perm=None, auth=False, arg=None,
        help='Syntax: PASS [<SP> password] (set user password).'),
    'PASV': dict(
        perm=None, auth=True, arg=False,
        help='Syntax: PASV (open passive data connection).'),
    'PORT': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: PORT <sp> h,h,h,h,p,p (open active data connection).'),
    'PWD': dict(
        perm=None, auth=True, arg=False,
        help='Syntax: PWD (get current working directory).'),
    'QUIT': dict(
        perm=None, auth=False, arg=False,
        help='Syntax: QUIT (quit current session).'),
    'REIN': dict(
        perm=None, auth=True, arg=False,
        help='Syntax: REIN (flush account).'),
    'REST': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: REST <SP> offset (set file offset).'),
    'RETR': dict(
        perm='r', auth=True, arg=True,
        help='Syntax: RETR <SP> file-name (retrieve a file).'),
    'RMD': dict(
        perm='d', auth=True, arg=True,
        help='Syntax: RMD <SP> dir-name (remove directory).'),
    'RNFR': dict(
        perm='f', auth=True, arg=True,
        help='Syntax: RNFR <SP> file-name (rename (source name)).'),
    'RNTO': dict(
        perm='f', auth=True, arg=True,
        help='Syntax: RNTO <SP> file-name (rename (destination name)).'),
    'SITE': dict(
        perm=None, auth=False, arg=True,
        help='Syntax: SITE <SP> site-command (execute SITE command).'),
    'SITE HELP': dict(
        perm=None, auth=False, arg=None,
        help='Syntax: SITE HELP [<SP> cmd] (show SITE command help).'),
    'SITE CHMOD': dict(
        perm='M', auth=True, arg=True,
        help='Syntax: SITE CHMOD <SP> mode path (change file mode).'),
    'SIZE': dict(
        perm='l', auth=True, arg=True,
        help='Syntax: SIZE <SP> file-name (get file size).'),
    'STAT': dict(
        perm='l', auth=False, arg=None,
        help='Syntax: STAT [<SP> path name] (server stats [list files]).'),
    'STOR': dict(
        perm='w', auth=True, arg=True,
        help='Syntax: STOR <SP> file-name (store a file).'),
    'STOU': dict(
        perm='w', auth=True, arg=None,
        help='Syntax: STOU [<SP> name] (store a file with a unique name).'),
    'STRU': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: STRU <SP> type (noop; set file structure).'),
    'SYST': dict(
        perm=None, auth=False, arg=False,
        help='Syntax: SYST (get operating system type).'),
    'TYPE': dict(
        perm=None, auth=True, arg=True,
        help='Syntax: TYPE <SP> [A | I] (set transfer type).'),
    'USER': dict(
        perm=None, auth=False, arg=True,
        help='Syntax: USER <SP> user-name (set username).'),
    'XCUP': dict(
        perm='e', auth=True, arg=False,
        help='Syntax: XCUP (obsolete; go to parent directory).'),
    'XCWD': dict(
        perm='e', auth=True, arg=None,
        help='Syntax: XCWD [<SP> dir-name] (obsolete; change directory).'),
    'XMKD': dict(
        perm='m', auth=True, arg=True,
        help='Syntax: XMKD <SP> dir-name (obsolete; create directory).'),
    'XPWD': dict(
        perm=None, auth=True, arg=False,
        help='Syntax: XPWD (obsolete; get current dir).'),
    'XRMD': dict(
        perm='d', auth=True, arg=True,
        help='Syntax: XRMD <SP> dir-name (obsolete; remove directory).'),
}

if not hasattr(os, 'chmod'):
    del proto_cmds['SITE CHMOD']


def _strerror(err):
    if isinstance(err, EnvironmentError):
        try:
            return os.strerror(err.errno)
        except AttributeError:
            # not available on PythonCE
            if not hasattr(os, 'strerror'):
                return err.strerror
            raise
    else:
        return str(err)


def _is_ssl_sock(sock):
    return SSL is not None and isinstance(sock, SSL.Connection)


def _support_hybrid_ipv6():
    """Return True if it is possible to use hybrid IPv6/IPv4 sockets
    on this platform.
    """
    # Note: IPPROTO_IPV6 constant is broken on Windows, see:
    # http://bugs.python.org/issue6926
    try:
        if not socket.has_ipv6:
            return False
        with contextlib.closing(socket.socket(socket.AF_INET6)) as sock:
            return not sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY)
    except (socket.error, AttributeError):
        return False


SUPPORTS_HYBRID_IPV6 = _support_hybrid_ipv6()


class _FileReadWriteError(OSError):
    """Exception raised when reading or writing a file during a transfer."""


class _GiveUpOnSendfile(Exception):
    """Exception raised in case use of sendfile() fails on first try,
    in which case send() will be used.
    """


# --- DTP classes

class PassiveDTP(Acceptor):
    """Creates a socket listening on a local port, dispatching the
    resultant connection to DTPHandler. Used for handling PASV command.

     - (int) timeout: the timeout for a remote client to establish
       connection with the listening socket. Defaults to 30 seconds.

     - (int) backlog: the maximum number of queued connections passed
       to listen(). If a connection request arrives when the queue is
       full the client may raise ECONNRESET. Defaults to 5.
    """
    timeout = 30
    backlog = None

    def __init__(self, cmd_channel, extmode=False):
        """Initialize the passive data server.

         - (instance) cmd_channel: the command channel class instance.
         - (bool) extmode: whether use extended passive mode response type.
        """
        self.cmd_channel = cmd_channel
        self.log = cmd_channel.log
        self.log_exception = cmd_channel.log_exception
        Acceptor.__init__(self, ioloop=cmd_channel.ioloop)

        local_ip = self.cmd_channel.socket.getsockname()[0]
        if local_ip in self.cmd_channel.masquerade_address_map:
            masqueraded_ip = self.cmd_channel.masquerade_address_map[local_ip]
        elif self.cmd_channel.masquerade_address:
            masqueraded_ip = self.cmd_channel.masquerade_address
        else:
            masqueraded_ip = None

        if self.cmd_channel.server.socket.family != socket.AF_INET:
            # dual stack IPv4/IPv6 support
            af = self.bind_af_unspecified((local_ip, 0))
            self.socket.close()
            self.del_channel()
        else:
            af = self.cmd_channel.socket.family

        self.create_socket(af, socket.SOCK_STREAM)

        if self.cmd_channel.passive_ports is None:
            # By using 0 as port number value we let kernel choose a
            # free unprivileged random port.
            self.bind((local_ip, 0))
        else:
            ports = list(self.cmd_channel.passive_ports)
            while ports:
                port = ports.pop(random.randint(0, len(ports) - 1))
                self.set_reuse_addr()
                try:
                    self.bind((local_ip, port))
                except socket.error as err:
                    if err.errno == errno.EADDRINUSE:  # port already in use
                        if ports:
                            continue
                        # If cannot use one of the ports in the configured
                        # range we'll use a kernel-assigned port, and log
                        # a message reporting the issue.
                        # By using 0 as port number value we let kernel
                        # choose a free unprivileged random port.
                        else:
                            self.bind((local_ip, 0))
                            self.cmd_channel.log(
                                "Can't find a valid passive port in the "
                                "configured range. A random kernel-assigned "
                                "port will be used.",
                                logfun=logger.warning
                            )
                    else:
                        raise
                else:
                    break
        self.listen(self.backlog or self.cmd_channel.server.backlog)

        port = self.socket.getsockname()[1]
        if not extmode:
            ip = masqueraded_ip or local_ip
            if ip.startswith('::ffff:'):
                # In this scenario, the server has an IPv6 socket, but
                # the remote client is using IPv4 and its address is
                # represented as an IPv4-mapped IPv6 address which
                # looks like this ::ffff:151.12.5.65, see:
                # http://en.wikipedia.org/wiki/IPv6#IPv4-mapped_addresses
                # http://tools.ietf.org/html/rfc3493.html#section-3.7
                # We truncate the first bytes to make it look like a
                # common IPv4 address.
                ip = ip[7:]
            # The format of 227 response in not standardized.
            # This is the most expected:
            resp = '227 Entering passive mode (%s,%d,%d).' % (
                ip.replace('.', ','), port // 256, port % 256)
            self.cmd_channel.respond(resp)
        else:
            self.cmd_channel.respond('229 Entering extended passive mode '
                                     '(|||%d|).' % port)
        if self.timeout:
            self.call_later(self.timeout, self.handle_timeout)

    # --- connection / overridden

    def handle_accepted(self, sock, addr):
        """Called when remote client initiates a connection."""
        if not self.cmd_channel.connected:
            return self.close()

        # Check the origin of data connection.  If not expressively
        # configured we drop the incoming data connection if remote
        # IP address does not match the client's IP address.
        if self.cmd_channel.remote_ip != addr[0]:
            if not self.cmd_channel.permit_foreign_addresses:
                try:
                    sock.close()
                except socket.error:
                    pass
                msg = '425 Rejected data connection from foreign address ' \
                    + '%s:%s.' % (addr[0], addr[1])
                self.cmd_channel.respond_w_warning(msg)
                # do not close listening socket: it couldn't be client's blame
                return
            else:
                # site-to-site FTP allowed
                msg = 'Established data connection with foreign address ' \
                    + '%s:%s.' % (addr[0], addr[1])
                self.cmd_channel.log(msg, logfun=logger.warning)
        # Immediately close the current channel (we accept only one
        # connection at time) and avoid running out of max connections
        # limit.
        self.close()
        # delegate such connection to DTP handler
        if self.cmd_channel.connected:
            handler = self.cmd_channel.dtp_handler(sock, self.cmd_channel)
            if handler.connected:
                self.cmd_channel.data_channel = handler
                self.cmd_channel._on_dtp_connection()

    def handle_timeout(self):
        if self.cmd_channel.connected:
            self.cmd_channel.respond("421 Passive data channel timed out.",
                                     logfun=logger.info)
        self.close()

    def handle_error(self):
        """Called to handle any uncaught exceptions."""
        try:
            raise
        except Exception:
            logger.error(traceback.format_exc())
        try:
            self.close()
        except Exception:
            logger.critical(traceback.format_exc())

    def close(self):
        debug("call: close()", inst=self)
        Acceptor.close(self)


class ActiveDTP(Connector):
    """Connects to remote client and dispatches the resulting connection
    to DTPHandler. Used for handling PORT command.

     - (int) timeout: the timeout for us to establish connection with
       the client's listening data socket.
    """
    timeout = 30

    def __init__(self, ip, port, cmd_channel):
        """Initialize the active data channel attempting to connect
        to remote data socket.

         - (str) ip: the remote IP address.
         - (int) port: the remote port.
         - (instance) cmd_channel: the command channel class instance.
        """
        Connector.__init__(self, ioloop=cmd_channel.ioloop)
        self.cmd_channel = cmd_channel
        self.log = cmd_channel.log
        self.log_exception = cmd_channel.log_exception
        self._idler = None
        if self.timeout:
            self._idler = self.ioloop.call_later(self.timeout,
                                                 self.handle_timeout,
                                                 _errback=self.handle_error)

        if ip.count('.') == 3:
            self._cmd = "PORT"
            self._normalized_addr = "%s:%s" % (ip, port)
        else:
            self._cmd = "EPRT"
            self._normalized_addr = "[%s]:%s" % (ip, port)

        source_ip = self.cmd_channel.socket.getsockname()[0]
        # dual stack IPv4/IPv6 support
        try:
            self.connect_af_unspecified((ip, port), (source_ip, 0))
        except (socket.gaierror, socket.error):
            self.handle_close()

    def readable(self):
        return False

    def handle_connect(self):
        """Called when connection is established."""
        self.del_channel()
        if self._idler is not None and not self._idler.cancelled:
            self._idler.cancel()
        if not self.cmd_channel.connected:
            return self.close()
        # fix for asyncore on python < 2.6, meaning we aren't
        # actually connected.
        # test_active_conn_error tests this condition
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise socket.error(err)
        #
        msg = 'Active data connection established.'
        self.cmd_channel.respond('200 ' + msg)
        self.cmd_channel.log_cmd(self._cmd, self._normalized_addr, 200, msg)
        #
        if not self.cmd_channel.connected:
            return self.close()
        # delegate such connection to DTP handler
        handler = self.cmd_channel.dtp_handler(self.socket, self.cmd_channel)
        self.cmd_channel.data_channel = handler
        self.cmd_channel._on_dtp_connection()

    def handle_timeout(self):
        if self.cmd_channel.connected:
            msg = "Active data channel timed out."
            self.cmd_channel.respond("421 " + msg, logfun=logger.info)
            self.cmd_channel.log_cmd(
                self._cmd, self._normalized_addr, 421, msg)
        self.close()

    def handle_close(self):
        # With the new IO loop, handle_close() gets called in case
        # the fd appears in the list of exceptional fds.
        # This means connect() failed.
        if not self._closed:
            self.close()
            if self.cmd_channel.connected:
                msg = "Can't connect to specified address."
                self.cmd_channel.respond("425 " + msg)
                self.cmd_channel.log_cmd(
                    self._cmd, self._normalized_addr, 425, msg)

    def handle_error(self):
        """Called to handle any uncaught exceptions."""
        try:
            raise
        except (socket.gaierror, socket.error):
            pass
        except Exception:
            self.log_exception(self)
        try:
            self.handle_close()
        except Exception:
            logger.critical(traceback.format_exc())

    def close(self):
        debug("call: close()", inst=self)
        if not self._closed:
            Connector.close(self)
            if self._idler is not None and not self._idler.cancelled:
                self._idler.cancel()


class DTPHandler(AsyncChat):
    """Class handling server-data-transfer-process (server-DTP, see
    RFC-959) managing data-transfer operations involving sending
    and receiving data.

    Class attributes:

     - (int) timeout: the timeout which roughly is the maximum time we
       permit data transfers to stall for with no progress. If the
       timeout triggers, the remote client will be kicked off
       (defaults 300).

     - (int) ac_in_buffer_size: incoming data buffer size (defaults 65536)

     - (int) ac_out_buffer_size: outgoing data buffer size (defaults 65536)
    """

    timeout = 300
    ac_in_buffer_size = 65536
    ac_out_buffer_size = 65536

    def __init__(self, sock, cmd_channel):
        """Initialize the command channel.

         - (instance) sock: the socket object instance of the newly
            established connection.
         - (instance) cmd_channel: the command channel class instance.
        """
        self.cmd_channel = cmd_channel
        self.file_obj = None
        self.receive = False
        self.transfer_finished = False
        self.tot_bytes_sent = 0
        self.tot_bytes_received = 0
        self.cmd = None
        self.log = cmd_channel.log
        self.log_exception = cmd_channel.log_exception
        self._data_wrapper = None
        self._lastdata = 0
        self._had_cr = False
        self._start_time = timer()
        self._resp = ()
        self._offset = None
        self._filefd = None
        self._idler = None
        self._initialized = False
        try:
            AsyncChat.__init__(self, sock, ioloop=cmd_channel.ioloop)
        except socket.error as err:
            # if we get an exception here we want the dispatcher
            # instance to set socket attribute before closing, see:
            # https://github.com/giampaolo/pyftpdlib/issues/188
            AsyncChat.__init__(
                self, socket.socket(), ioloop=cmd_channel.ioloop)
            # https://github.com/giampaolo/pyftpdlib/issues/143
            self.close()
            if err.errno == errno.EINVAL:
                return
            self.handle_error()
            return

        # remove this instance from IOLoop's socket map
        if not self.connected:
            self.close()
            return
        if self.timeout:
            self._idler = self.ioloop.call_every(self.timeout,
                                                 self.handle_timeout,
                                                 _errback=self.handle_error)

    def __repr__(self):
        return '<%s(%s)>' % (self.__class__.__name__,
                             self.cmd_channel.get_repr_info(as_str=True))

    __str__ = __repr__

    def use_sendfile(self):
        if not self.cmd_channel.use_sendfile:
            # as per server config
            return False
        if self.file_obj is None or not hasattr(self.file_obj, "fileno"):
            # directory listing or unusual file obj
            return False
        try:
            # io.IOBase default implementation raises io.UnsupportedOperation
            # UnsupportedOperation inherits ValueError
            # also may raise ValueError if stream is closed
            # https://docs.python.org/3/library/io.html#io.IOBase
            self.file_obj.fileno()
        except (OSError, ValueError):
            return False
        if self.cmd_channel._current_type != 'i':
            # text file transfer (need to transform file content on the fly)
            return False
        return True

    def push(self, data):
        self._initialized = True
        self.modify_ioloop_events(self.ioloop.WRITE)
        self._wanted_io_events = self.ioloop.WRITE
        AsyncChat.push(self, data)

    def push_with_producer(self, producer):
        self._initialized = True
        self.modify_ioloop_events(self.ioloop.WRITE)
        self._wanted_io_events = self.ioloop.WRITE
        if self.use_sendfile():
            self._offset = producer.file.tell()
            self._filefd = self.file_obj.fileno()
            try:
                self.initiate_sendfile()
            except _GiveUpOnSendfile:
                pass
            else:
                self.initiate_send = self.initiate_sendfile
                return
        debug("starting transfer using send()", self)
        AsyncChat.push_with_producer(self, producer)

    def close_when_done(self):
        asynchat.async_chat.close_when_done(self)

    def initiate_send(self):
        asynchat.async_chat.initiate_send(self)

    def initiate_sendfile(self):
        """A wrapper around sendfile."""
        try:
            sent = sendfile(self._fileno, self._filefd, self._offset,
                            self.ac_out_buffer_size)
        except OSError as err:
            if err.errno in _ERRNOS_RETRY or err.errno == errno.EBUSY:
                return
            elif err.errno in _ERRNOS_DISCONNECTED:
                self.handle_close()
            else:
                if self.tot_bytes_sent == 0:
                    logger.warning(
                        "sendfile() failed; falling back on using plain send")
                    raise _GiveUpOnSendfile
                else:
                    raise
        else:
            if sent == 0:
                # this signals the channel that the transfer is completed
                self.discard_buffers()
                self.handle_close()
            else:
                self._offset += sent
                self.tot_bytes_sent += sent

    # --- utility methods

    def _posix_ascii_data_wrapper(self, chunk):
        """The data wrapper used for receiving data in ASCII mode on
        systems using a single line terminator, handling those cases
        where CRLF ('\r\n') gets delivered in two chunks.
        """
        if self._had_cr:
            chunk = b'\r' + chunk

        if chunk.endswith(b'\r'):
            self._had_cr = True
            chunk = chunk[:-1]
        else:
            self._had_cr = False

        return chunk.replace(b'\r\n', b(os.linesep))

    def enable_receiving(self, type, cmd):
        """Enable receiving of data over the channel. Depending on the
        TYPE currently in use it creates an appropriate wrapper for the
        incoming data.

         - (str) type: current transfer type, 'a' (ASCII) or 'i' (binary).
        """
        self._initialized = True
        self.modify_ioloop_events(self.ioloop.READ)
        self._wanted_io_events = self.ioloop.READ
        self.cmd = cmd
        if type == 'a':
            if os.linesep == '\r\n':
                self._data_wrapper = None
            else:
                self._data_wrapper = self._posix_ascii_data_wrapper
        elif type == 'i':
            self._data_wrapper = None
        else:
            raise TypeError("unsupported type")
        self.receive = True

    def get_transmitted_bytes(self):
        """Return the number of transmitted bytes."""
        return self.tot_bytes_sent + self.tot_bytes_received

    def get_elapsed_time(self):
        """Return the transfer elapsed time in seconds."""
        return timer() - self._start_time

    def transfer_in_progress(self):
        """Return True if a transfer is in progress, else False."""
        return self.get_transmitted_bytes() != 0

    # --- connection

    def send(self, data):
        result = AsyncChat.send(self, data)
        self.tot_bytes_sent += result
        return result

    def refill_buffer(self):  # pragma: no cover
        """Overridden as a fix around http://bugs.python.org/issue1740572
        (when the producer is consumed, close() was called instead of
        handle_close()).
        """
        while True:
            if len(self.producer_fifo):
                p = self.producer_fifo.first()
                # a 'None' in the producer fifo is a sentinel,
                # telling us to close the channel.
                if p is None:
                    if not self.ac_out_buffer:
                        self.producer_fifo.pop()
                        # self.close()
                        self.handle_close()
                    return
                elif isinstance(p, str):
                    self.producer_fifo.pop()
                    self.ac_out_buffer += p
                    return
                data = p.more()
                if data:
                    self.ac_out_buffer = self.ac_out_buffer + data
                    return
                else:
                    self.producer_fifo.pop()
            else:
                return

    def handle_read(self):
        """Called when there is data waiting to be read."""
        try:
            chunk = self.recv(self.ac_in_buffer_size)
        except RetryError:
            pass
        except socket.error:
            self.handle_error()
        else:
            self.tot_bytes_received += len(chunk)
            if not chunk:
                self.transfer_finished = True
                # self.close()  # <-- asyncore.recv() already do that...
                return
            if self._data_wrapper is not None:
                chunk = self._data_wrapper(chunk)
            try:
                self.file_obj.write(chunk)
            except OSError as err:
                raise _FileReadWriteError(err)

    handle_read_event = handle_read  # small speedup

    def readable(self):
        """Predicate for inclusion in the readable for select()."""
        # It the channel is not supposed to be receiving but yet it's
        # in the list of readable events, that means it has been
        # disconnected, in which case we explicitly close() it.
        # This is necessary as differently from FTPHandler this channel
        # is not supposed to be readable/writable at first, meaning the
        # upper IOLoop might end up calling readable() repeatedly,
        # hogging CPU resources.
        if not self.receive and not self._initialized:
            return self.close()
        return self.receive

    def writable(self):
        """Predicate for inclusion in the writable for select()."""
        return not self.receive and asynchat.async_chat.writable(self)

    def handle_timeout(self):
        """Called cyclically to check if data transfer is stalling with
        no progress in which case the client is kicked off.
        """
        if self.get_transmitted_bytes() > self._lastdata:
            self._lastdata = self.get_transmitted_bytes()
        else:
            msg = "Data connection timed out."
            self._resp = ("421 " + msg, logger.info)
            self.close()
            self.cmd_channel.close_when_done()

    def handle_error(self):
        """Called when an exception is raised and not otherwise handled."""
        try:
            raise
        # an error could occur in case we fail reading / writing
        # from / to file (e.g. file system gets full)
        except _FileReadWriteError as err:
            error = _strerror(err.errno)
        except Exception:
            # some other exception occurred;  we don't want to provide
            # confidential error messages
            self.log_exception(self)
            error = "Internal error"
        try:
            self._resp = ("426 %s; transfer aborted." % error, logger.warning)
            self.close()
        except Exception:
            logger.critical(traceback.format_exc())

    def handle_close(self):
        """Called when the socket is closed."""
        # If we used channel for receiving we assume that transfer is
        # finished when client closes the connection, if we used channel
        # for sending we have to check that all data has been sent
        # (responding with 226) or not (responding with 426).
        # In both cases handle_close() is automatically called by the
        # underlying asynchat module.
        if not self._closed:
            if self.receive:
                self.transfer_finished = True
            else:
                self.transfer_finished = len(self.producer_fifo) == 0
            try:
                if self.transfer_finished:
                    self._resp = ("226 Transfer complete.", logger.debug)
                else:
                    tot_bytes = self.get_transmitted_bytes()
                    self._resp = ("426 Transfer aborted; %d bytes transmitted."
                                  % tot_bytes, logger.debug)
            finally:
                self.close()

    def close(self):
        """Close the data channel, first attempting to close any remaining
        file handles."""
        debug("call: close()", inst=self)
        if not self._closed:
            # RFC-959 says we must close the connection before replying
            AsyncChat.close(self)

            # Close file object before responding successfully to client
            if self.file_obj is not None and not self.file_obj.closed:
                self.file_obj.close()

            if self._resp:
                self.cmd_channel.respond(self._resp[0], logfun=self._resp[1])

            if self._idler is not None and not self._idler.cancelled:
                self._idler.cancel()
            if self.file_obj is not None:
                filename = self.file_obj.name
                elapsed_time = round(self.get_elapsed_time(), 3)
                self.cmd_channel.log_transfer(
                    cmd=self.cmd,
                    filename=self.file_obj.name,
                    receive=self.receive,
                    completed=self.transfer_finished,
                    elapsed=elapsed_time,
                    bytes=self.get_transmitted_bytes())
                if self.transfer_finished:
                    if self.receive:
                        self.cmd_channel.on_file_received(filename)
                    else:
                        self.cmd_channel.on_file_sent(filename)
                else:
                    if self.receive:
                        self.cmd_channel.on_incomplete_file_received(filename)
                    else:
                        self.cmd_channel.on_incomplete_file_sent(filename)
            self.cmd_channel._on_dtp_close()


# dirty hack in order to turn AsyncChat into a new style class in
# python 2.x so that we can use super()
if PY3:
    class _AsyncChatNewStyle(AsyncChat):
        pass
else:
    class _AsyncChatNewStyle(object, AsyncChat):  # noqa

        def __init__(self, *args, **kwargs):
            super(object, self).__init__(*args, **kwargs)  # bypass object


class ThrottledDTPHandler(_AsyncChatNewStyle, DTPHandler):
    """A DTPHandler subclass which wraps sending and receiving in a data
    counter and temporarily "sleeps" the channel so that you burst to no
    more than x Kb/sec average.

     - (int) read_limit: the maximum number of bytes to read (receive)
       in one second (defaults to 0 == no limit).

     - (int) write_limit: the maximum number of bytes to write (send)
       in one second (defaults to 0 == no limit).

     - (bool) auto_sized_buffers: this option only applies when read
       and/or write limits are specified. When enabled it bumps down
       the data buffer sizes so that they are never greater than read
       and write limits which results in a less bursty and smoother
       throughput (default: True).
    """
    read_limit = 0
    write_limit = 0
    auto_sized_buffers = True

    def __init__(self, sock, cmd_channel):
        super().__init__(sock, cmd_channel)
        self._timenext = 0
        self._datacount = 0
        self.sleeping = False
        self._throttler = None
        if self.auto_sized_buffers:
            if self.read_limit:
                while self.ac_in_buffer_size > self.read_limit:
                    self.ac_in_buffer_size /= 2
            if self.write_limit:
                while self.ac_out_buffer_size > self.write_limit:
                    self.ac_out_buffer_size /= 2
        self.ac_in_buffer_size = int(self.ac_in_buffer_size)
        self.ac_out_buffer_size = int(self.ac_out_buffer_size)

    def __repr__(self):
        return DTPHandler.__repr__(self)

    def use_sendfile(self):
        return False

    def recv(self, buffer_size):
        chunk = super().recv(buffer_size)
        if self.read_limit:
            self._throttle_bandwidth(len(chunk), self.read_limit)
        return chunk

    def send(self, data):
        num_sent = super().send(data)
        if self.write_limit:
            self._throttle_bandwidth(num_sent, self.write_limit)
        return num_sent

    def _cancel_throttler(self):
        if self._throttler is not None and not self._throttler.cancelled:
            self._throttler.cancel()

    def _throttle_bandwidth(self, len_chunk, max_speed):
        """A method which counts data transmitted so that you burst to
        no more than x Kb/sec average.
        """
        self._datacount += len_chunk
        if self._datacount >= max_speed:
            self._datacount = 0
            now = timer()
            sleepfor = (self._timenext - now) * 2
            if sleepfor > 0:
                # we've passed bandwidth limits
                def unsleep():
                    if self.receive:
                        event = self.ioloop.READ
                    else:
                        event = self.ioloop.WRITE
                    self.add_channel(events=event)

                self.del_channel()
                self._cancel_throttler()
                self._throttler = self.ioloop.call_later(
                    sleepfor, unsleep, _errback=self.handle_error)
            self._timenext = now + 1

    def close(self):
        self._cancel_throttler()
        super().close()


# --- producers


class FileProducer:
    """Producer wrapper for file[-like] objects."""

    buffer_size = 65536

    def __init__(self, file, type):
        """Initialize the producer with a data_wrapper appropriate to TYPE.

         - (file) file: the file[-like] object.
         - (str) type: the current TYPE, 'a' (ASCII) or 'i' (binary).
        """
        self.file = file
        self.type = type
        self._prev_chunk_endswith_cr = False
        if type == 'a' and os.linesep != '\r\n':
            self._data_wrapper = self._posix_ascii_data_wrapper
        else:
            self._data_wrapper = None

    def _posix_ascii_data_wrapper(self, chunk):
        """The data wrapper used for sending data in ASCII mode on
        systems using a single line terminator, handling those cases
        where CRLF ('\r\n') gets delivered in two chunks.
        """
        chunk = bytearray(chunk)
        pos = 0
        if self._prev_chunk_endswith_cr and chunk.startswith(b'\n'):
            pos += 1
        while True:
            pos = chunk.find(b'\n', pos)
            if pos == -1:
                break
            if chunk[pos - 1] != CR_BYTE:
                chunk.insert(pos, CR_BYTE)
                pos += 1
            pos += 1
        self._prev_chunk_endswith_cr = chunk.endswith(b'\r')
        return chunk

    def more(self):
        """Attempt a chunk of data of size self.buffer_size."""
        try:
            data = self.file.read(self.buffer_size)
        except OSError as err:
            raise _FileReadWriteError(err)
        else:
            if self._data_wrapper is not None:
                data = self._data_wrapper(data)
            return data


class BufferedIteratorProducer:
    """Producer for iterator objects with buffer capabilities."""
    # how many times iterator.next() will be called before
    # returning some data
    loops = 20

    def __init__(self, iterator):
        self.iterator = iterator

    def more(self):
        """Attempt a chunk of data from iterator by calling
        its next() method different times.
        """
        buffer = []
        for _ in xrange(self.loops):
            try:
                buffer.append(next(self.iterator))
            except StopIteration:
                break
        return b''.join(buffer)


# --- FTP

class FTPHandler(AsyncChat):
    """Implements the FTP server Protocol Interpreter (see RFC-959),
    handling commands received from the client on the control channel.

    All relevant session information is stored in class attributes
    reproduced below and can be modified before instantiating this
    class.

     - (int) timeout:
       The timeout which is the maximum time a remote client may spend
       between FTP commands. If the timeout triggers, the remote client
       will be kicked off.  Defaults to 300 seconds.

     - (str) banner: the string sent when client connects.

     - (int) max_login_attempts:
        the maximum number of wrong authentications before disconnecting
        the client (default 3).

     - (bool)permit_foreign_addresses:
        FTP site-to-site transfer feature: also referenced as "FXP" it
        permits for transferring a file between two remote FTP servers
        without the transfer going through the client's host (not
        recommended for security reasons as described in RFC-2577).
        Having this attribute set to False means that all data
        connections from/to remote IP addresses which do not match the
        client's IP address will be dropped (defualt False).

     - (bool) permit_privileged_ports:
        set to True if you want to permit active data connections (PORT)
        over privileged ports (not recommended, defaulting to False).

     - (str) masquerade_address:
        the "masqueraded" IP address to provide along PASV reply when
        pyftpdlib is running behind a NAT or other types of gateways.
        When configured pyftpdlib will hide its local address and
        instead use the public address of your NAT (default None).

     - (dict) masquerade_address_map:
        in case the server has multiple IP addresses which are all
        behind a NAT router, you may wish to specify individual
        masquerade_addresses for each of them. The map expects a
        dictionary containing private IP addresses as keys, and their
        corresponding public (masquerade) addresses as values.

     - (list) passive_ports:
        what ports the ftpd will use for its passive data transfers.
        Value expected is a list of integers (e.g. range(60000, 65535)).
        When configured pyftpdlib will no longer use kernel-assigned
        random ports (default None).

     - (bool) use_gmt_times:
        when True causes the server to report all ls and MDTM times in
        GMT and not local time (default True).

     - (bool) use_sendfile: when True uses sendfile() system call to
        send a file resulting in faster uploads (from server to client).
        Works on UNIX only and requires pysendfile module to be
        installed separately:
        https://github.com/giampaolo/pysendfile/
        Automatically defaults to True if pysendfile module is
        installed.

     - (bool) tcp_no_delay: controls the use of the TCP_NODELAY socket
        option which disables the Nagle algorithm resulting in
        significantly better performances (default True on all systems
        where it is supported).

     - (str) unicode_errors:
       the error handler passed to ''.encode() and ''.decode():
       http://docs.python.org/library/stdtypes.html#str.decode
       (detaults to 'replace').

     - (str) log_prefix:
       the prefix string preceding any log line; all instance
       attributes can be used as arguments.


    All relevant instance attributes initialized when client connects
    are reproduced below.  You may be interested in them in case you
    want to subclass the original FTPHandler.

     - (bool) authenticated: True if client authenticated himself.
     - (str) username: the name of the connected user (if any).
     - (int) attempted_logins: number of currently attempted logins.
     - (str) current_type: the current transfer type (default "a")
     - (int) af: the connection's address family (IPv4/IPv6)
     - (instance) server: the FTPServer class instance.
     - (instance) data_channel: the data channel instance (if any).
    """
    # these are overridable defaults

    # default classes
    authorizer = DummyAuthorizer()
    active_dtp = ActiveDTP
    passive_dtp = PassiveDTP
    dtp_handler = DTPHandler
    abstracted_fs = AbstractedFS
    proto_cmds = proto_cmds

    # session attributes (explained in the docstring)
    timeout = 300
    banner = "pyftpdlib %s ready." % __ver__
    max_login_attempts = 3
    permit_foreign_addresses = False
    permit_privileged_ports = False
    masquerade_address = None
    masquerade_address_map = {}
    passive_ports = None
    use_gmt_times = True
    use_sendfile = sendfile is not None
    tcp_no_delay = hasattr(socket, "TCP_NODELAY")
    unicode_errors = 'replace'
    log_prefix = '%(remote_ip)s:%(remote_port)s-[%(username)s]'
    auth_failed_timeout = 3

    def __init__(self, conn, server, ioloop=None):
        """Initialize the command channel.

         - (instance) conn: the socket object instance of the newly
            established connection.
         - (instance) server: the ftp server class instance.
        """
        # public session attributes
        self.server = server
        self.fs = None
        self.authenticated = False
        self.username = ""
        self.password = ""
        self.attempted_logins = 0
        self.data_channel = None
        self.remote_ip = ""
        self.remote_port = ""
        self.started = time.time()

        # private session attributes
        self._last_response = ""
        self._current_type = 'a'
        self._restart_position = 0
        self._quit_pending = False
        self._in_buffer = []
        self._in_buffer_len = 0
        self._epsvall = False
        self._dtp_acceptor = None
        self._dtp_connector = None
        self._in_dtp_queue = None
        self._out_dtp_queue = None
        self._extra_feats = []
        self._current_facts = ['type', 'perm', 'size', 'modify']
        self._rnfr = None
        self._idler = None
        self._log_debug = logging.getLogger('pyftpdlib').getEffectiveLevel() \
            <= logging.DEBUG

        if os.name == 'posix':
            self._current_facts.append('unique')
        self._available_facts = self._current_facts[:]
        if pwd and grp:
            self._available_facts += ['unix.mode', 'unix.uid', 'unix.gid']
        if os.name == 'nt':
            self._available_facts.append('create')

        try:
            AsyncChat.__init__(self, conn, ioloop=ioloop)
        except socket.error as err:
            # if we get an exception here we want the dispatcher
            # instance to set socket attribute before closing, see:
            # https://github.com/giampaolo/pyftpdlib/issues/188
            AsyncChat.__init__(self, socket.socket(), ioloop=ioloop)
            self.close()
            debug("call: FTPHandler.__init__, err %r" % err, self)
            if err.errno == errno.EINVAL:
                # https://github.com/giampaolo/pyftpdlib/issues/143
                return
            self.handle_error()
            return
        self.set_terminator(b"\r\n")

        # connection properties
        try:
            self.remote_ip, self.remote_port = self.socket.getpeername()[:2]
        except socket.error as err:
            debug("call: FTPHandler.__init__, err on getpeername() %r" % err,
                  self)
            # A race condition  may occur if the other end is closing
            # before we can get the peername, hence ENOTCONN (see issue
            # #100) while EINVAL can occur on OSX (see issue #143).
            self.connected = False
            if err.errno in (errno.ENOTCONN, errno.EINVAL):
                self.close()
            else:
                self.handle_error()
            return
        else:
            self.log("FTP session opened (connect)")

        # try to handle urgent data inline
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_OOBINLINE, 1)
        except socket.error as err:
            debug("call: FTPHandler.__init__, err on SO_OOBINLINE %r" % err,
                  self)

        # disable Nagle algorithm for the control socket only, resulting
        # in significantly better performances
        if self.tcp_no_delay:
            try:
                self.socket.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
            except socket.error as err:
                debug(
                    "call: FTPHandler.__init__, err on TCP_NODELAY %r" % err,
                    self)

        # remove this instance from IOLoop's socket_map
        if not self.connected:
            self.close()
            return

        if self.timeout:
            self._idler = self.ioloop.call_later(
                self.timeout, self.handle_timeout, _errback=self.handle_error)

    def get_repr_info(self, as_str=False, extra_info=None):
        if extra_info is None:
            extra_info = {}
        info = OrderedDict()
        info['id'] = id(self)
        info['addr'] = "%s:%s" % (self.remote_ip, self.remote_port)
        if _is_ssl_sock(self.socket):
            info['ssl'] = True
        if self.username:
            info['user'] = self.username
        # If threads are involved sometimes "self" may be None (?!?).
        dc = getattr(self, 'data_channel', None)
        if dc is not None:
            if _is_ssl_sock(dc.socket):
                info['ssl-data'] = True
            if dc.file_obj:
                if self.data_channel.receive:
                    info['sending-file'] = dc.file_obj
                    if dc.use_sendfile():
                        info['use-sendfile(2)'] = True
                else:
                    info['receiving-file'] = dc.file_obj
                info['bytes-trans'] = dc.get_transmitted_bytes()
        info.update(extra_info)
        if as_str:
            return ', '.join(['%s=%r' % (k, v) for (k, v) in info.items()])
        return info

    def __repr__(self):
        return '<%s(%s)>' % (self.__class__.__name__, self.get_repr_info(True))

    __str__ = __repr__

    def handle(self):
        """Return a 220 'ready' response to the client over the command
        channel.
        """
        self.on_connect()
        if not self._closed and not self._closing:
            if len(self.banner) <= 75:
                self.respond("220 %s" % str(self.banner))
            else:
                self.push('220-%s\r\n' % str(self.banner))
                self.respond('220 ')

    def handle_max_cons(self):
        """Called when limit for maximum number of connections is reached."""
        msg = "421 Too many connections. Service temporarily unavailable."
        self.respond_w_warning(msg)
        # If self.push is used, data could not be sent immediately in
        # which case a new "loop" will occur exposing us to the risk of
        # accepting new connections.  Since this could cause asyncore to
        # run out of fds in case we're using select() on Windows  we
        # immediately close the channel by using close() instead of
        # close_when_done(). If data has not been sent yet client will
        # be silently disconnected.
        self.close()

    def handle_max_cons_per_ip(self):
        """Called when too many clients are connected from the same IP."""
        msg = "421 Too many connections from the same IP address."
        self.respond_w_warning(msg)
        self.close_when_done()

    def handle_timeout(self):
        """Called when client does not send any command within the time
        specified in <timeout> attribute."""
        msg = "Control connection timed out."
        self.respond("421 " + msg, logfun=logger.info)
        self.close_when_done()

    # --- asyncore / asynchat overridden methods

    def readable(self):
        # Checking for self.connected seems to be necessary as per:
        # https://github.com/giampaolo/pyftpdlib/issues/188#c18
        # In contrast to DTPHandler, here we are not interested in
        # attempting to receive any further data from a closed socket.
        return self.connected and AsyncChat.readable(self)

    def writable(self):
        return self.connected and AsyncChat.writable(self)

    def collect_incoming_data(self, data):
        """Read incoming data and append to the input buffer."""
        self._in_buffer.append(data)
        self._in_buffer_len += len(data)
        # Flush buffer if it gets too long (possible DoS attacks).
        # RFC-959 specifies that a 500 response could be given in
        # such cases
        buflimit = 2048
        if self._in_buffer_len > buflimit:
            self.respond_w_warning('500 Command too long.')
            self._in_buffer = []
            self._in_buffer_len = 0

    def decode(self, bytes):
        return bytes.decode('utf8', self.unicode_errors)

    def found_terminator(self):
        r"""Called when the incoming data stream matches the \r\n
        terminator.
        """
        if self._idler is not None and not self._idler.cancelled:
            self._idler.reset()

        line = b''.join(self._in_buffer)
        try:
            line = self.decode(line)
        except UnicodeDecodeError:
            # By default we'll never get here as we replace errors
            # but user might want to override this behavior.
            # RFC-2640 doesn't mention what to do in this case so
            # we'll just return 501 (bad arg).
            return self.respond("501 Can't decode command.")

        self._in_buffer = []
        self._in_buffer_len = 0

        cmd = line.split(' ')[0].upper()
        arg = line[len(cmd) + 1:]
        try:
            self.pre_process_command(line, cmd, arg)
        except UnicodeEncodeError:
            self.respond("501 can't decode path (server filesystem encoding "
                         "is %s)" % sys.getfilesystemencoding())

    def pre_process_command(self, line, cmd, arg):
        kwargs = {}
        if cmd == "SITE" and arg:
            cmd = "SITE %s" % arg.split(' ')[0].upper()
            arg = line[len(cmd) + 1:]

        if cmd != 'PASS':
            self.logline("<- %s" % line)
        else:
            self.logline("<- %s %s" % (line.split(' ')[0], '*' * 6))

        # Recognize those commands having a "special semantic". They
        # should be sent by following the RFC-959 procedure of sending
        # Telnet IP/Synch sequence (chr 242 and 255) as OOB data but
        # since many ftp clients don't do it correctly we check the
        # last 4 characters only.
        if cmd not in self.proto_cmds:
            if cmd[-4:] in ('ABOR', 'STAT', 'QUIT'):
                cmd = cmd[-4:]
            else:
                msg = 'Command "%s" not understood.' % cmd
                self.respond('500 ' + msg)
                if cmd:
                    self.log_cmd(cmd, arg, 500, msg)
                return

        if not arg and self.proto_cmds[cmd]['arg'] is True:  # NOQA
            msg = "Syntax error: command needs an argument."
            self.respond("501 " + msg)
            self.log_cmd(cmd, "", 501, msg)
            return
        if arg and self.proto_cmds[cmd]['arg'] is False:  # NOQA
            msg = "Syntax error: command does not accept arguments."
            self.respond("501 " + msg)
            self.log_cmd(cmd, arg, 501, msg)
            return

        if not self.authenticated:
            if self.proto_cmds[cmd]['auth'] or (cmd == 'STAT' and arg):
                msg = "Log in with USER and PASS first."
                self.respond("530 " + msg)
                self.log_cmd(cmd, arg, 530, msg)
            else:
                # call the proper ftp_* method
                self.process_command(cmd, arg)
                return
        else:
            if (cmd == 'STAT') and not arg:
                self.ftp_STAT(u(''))
                return

            # for file-system related commands check whether real path
            # destination is valid
            if self.proto_cmds[cmd]['perm'] and (cmd != 'STOU'):
                if cmd in ('CWD', 'XCWD'):
                    arg = self.fs.ftp2fs(arg or u('/'))
                elif cmd in ('CDUP', 'XCUP'):
                    arg = self.fs.ftp2fs(u('..'))
                elif cmd == 'LIST':
                    if arg.lower() in ('-a', '-l', '-al', '-la'):
                        arg = self.fs.ftp2fs(self.fs.cwd)
                    else:
                        arg = self.fs.ftp2fs(arg or self.fs.cwd)
                elif cmd == 'STAT':
                    if glob.has_magic(arg):
                        msg = 'Globbing not supported.'
                        self.respond('550 ' + msg)
                        self.log_cmd(cmd, arg, 550, msg)
                        return
                    arg = self.fs.ftp2fs(arg or self.fs.cwd)
                elif cmd == 'SITE CHMOD':
                    if ' ' not in arg:
                        msg = "Syntax error: command needs two arguments."
                        self.respond("501 " + msg)
                        self.log_cmd(cmd, "", 501, msg)
                        return
                    else:
                        mode, arg = arg.split(' ', 1)
                        arg = self.fs.ftp2fs(arg)
                        kwargs = dict(mode=mode)
                elif cmd == 'MFMT':
                    if ' ' not in arg:
                        msg = "Syntax error: command needs two arguments."
                        self.respond("501 " + msg)
                        self.log_cmd(cmd, "", 501, msg)
                        return
                    else:
                        timeval, arg = arg.split(' ', 1)
                        arg = self.fs.ftp2fs(arg)
                        kwargs = dict(timeval=timeval)

                else:  # LIST, NLST, MLSD, MLST
                    arg = self.fs.ftp2fs(arg or self.fs.cwd)

                if not self.fs.validpath(arg):
                    line = self.fs.fs2ftp(arg)
                    msg = "%r points to a path which is outside " % line
                    msg += "the user's root directory"
                    self.respond("550 %s." % msg)
                    self.log_cmd(cmd, arg, 550, msg)
                    return

            # check permission
            perm = self.proto_cmds[cmd]['perm']
            if perm is not None and cmd != 'STOU':
                if not self.authorizer.has_perm(self.username, perm, arg):
                    msg = "Not enough privileges."
                    self.respond("550 " + msg)
                    self.log_cmd(cmd, arg, 550, msg)
                    return

            # call the proper ftp_* method
            self.process_command(cmd, arg, **kwargs)

    def process_command(self, cmd, *args, **kwargs):
        """Process command by calling the corresponding ftp_* class
        method (e.g. for received command "MKD pathname", ftp_MKD()
        method is called with "pathname" as the argument).
        """
        if self._closed:
            return
        self._last_response = ""
        method = getattr(self, 'ftp_' + cmd.replace(' ', '_'))
        method(*args, **kwargs)
        if self._last_response:
            code = int(self._last_response[:3])
            resp = self._last_response[4:]
            self.log_cmd(cmd, args[0], code, resp)

    def handle_error(self):
        try:
            self.log_exception(self)
            self.close()
        except Exception:
            logger.critical(traceback.format_exc())

    def handle_close(self):
        self.close()

    def close(self):
        """Close the current channel disconnecting the client."""
        debug("call: close()", inst=self)
        if not self._closed:
            AsyncChat.close(self)

            self._shutdown_connecting_dtp()

            if self.data_channel is not None:
                self.data_channel.close()
                del self.data_channel

            if self._out_dtp_queue is not None:
                file = self._out_dtp_queue[2]
                if file is not None:
                    file.close()
            if self._in_dtp_queue is not None:
                file = self._in_dtp_queue[0]
                if file is not None:
                    file.close()

            del self._out_dtp_queue
            del self._in_dtp_queue

            if self._idler is not None and not self._idler.cancelled:
                self._idler.cancel()

            # remove client IP address from ip map
            if self.remote_ip in self.server.ip_map:
                self.server.ip_map.remove(self.remote_ip)

            if self.fs is not None:
                self.fs.cmd_channel = None
                self.fs = None
            self.log("FTP session closed (disconnect).")
            # Having self.remote_ip not set means that no connection
            # actually took place, hence we're not interested in
            # invoking the callback.
            if self.remote_ip:
                self.ioloop.call_later(0, self.on_disconnect,
                                       _errback=self.handle_error)

    def _shutdown_connecting_dtp(self):
        """Close any ActiveDTP or PassiveDTP instance waiting to
        establish a connection (passive or active).
        """
        if self._dtp_acceptor is not None:
            self._dtp_acceptor.close()
            self._dtp_acceptor = None
        if self._dtp_connector is not None:
            self._dtp_connector.close()
            self._dtp_connector = None

    # --- public callbacks
    # Note: to run a time consuming task make sure to use a separate
    # process or thread (see FAQs).

    def on_connect(self):
        """Called when client connects, *before* sending the initial
        220 reply.
        """

    def on_disconnect(self):
        """Called when connection is closed."""

    def on_login(self, username):
        """Called on user login."""

    def on_login_failed(self, username, password):
        """Called on failed login attempt.
        At this point client might have already been disconnected if it
        failed too many times.
        """

    def on_logout(self, username):
        """Called when user "cleanly" logs out due to QUIT or USER
        issued twice (re-login). This is not called if the connection
        is simply closed by client.
        """

    def on_file_sent(self, file):
        """Called every time a file has been successfully sent.
        "file" is the absolute name of the file just being sent.
        """

    def on_file_received(self, file):
        """Called every time a file has been successfully received.
        "file" is the absolute name of the file just being received.
        """

    def on_incomplete_file_sent(self, file):
        """Called every time a file has not been entirely sent.
        (e.g. ABOR during transfer or client disconnected).
        "file" is the absolute name of that file.
        """

    def on_incomplete_file_received(self, file):
        """Called every time a file has not been entirely received
        (e.g. ABOR during transfer or client disconnected).
        "file" is the absolute name of that file.
        """

    # --- internal callbacks

    def _on_dtp_connection(self):
        """Called every time data channel connects, either active or
        passive.

        Incoming and outgoing queues are checked for pending data.
        If outbound data is pending, it is pushed into the data channel.
        If awaiting inbound data, the data channel is enabled for
        receiving.
        """
        # Close accepting DTP only. By closing ActiveDTP DTPHandler
        # would receive a closed socket object.
        # self._shutdown_connecting_dtp()
        if self._dtp_acceptor is not None:
            self._dtp_acceptor.close()
            self._dtp_acceptor = None

        # stop the idle timer as long as the data transfer is not finished
        if self._idler is not None and not self._idler.cancelled:
            self._idler.cancel()

        # check for data to send
        if self._out_dtp_queue is not None:
            data, isproducer, file, cmd = self._out_dtp_queue
            self._out_dtp_queue = None
            self.data_channel.cmd = cmd
            if file:
                self.data_channel.file_obj = file
            try:
                if not isproducer:
                    self.data_channel.push(data)
                else:
                    self.data_channel.push_with_producer(data)
                if self.data_channel is not None:
                    self.data_channel.close_when_done()
            except Exception:
                # dealing with this exception is up to DTP (see bug #84)
                self.data_channel.handle_error()

        # check for data to receive
        elif self._in_dtp_queue is not None:
            file, cmd = self._in_dtp_queue
            self.data_channel.file_obj = file
            self._in_dtp_queue = None
            self.data_channel.enable_receiving(self._current_type, cmd)

    def _on_dtp_close(self):
        """Called every time the data channel is closed."""
        self.data_channel = None
        if self._quit_pending:
            self.close()
        elif self.timeout:
            # data transfer finished, restart the idle timer
            if self._idler is not None and not self._idler.cancelled:
                self._idler.cancel()
            self._idler = self.ioloop.call_later(
                self.timeout, self.handle_timeout, _errback=self.handle_error)

    # --- utility

    def push(self, data):
        asynchat.async_chat.push(self, data.encode('utf8'))

    def respond(self, resp, logfun=logger.debug):
        """Send a response to the client using the command channel."""
        self._last_response = resp
        self.push(resp + '\r\n')
        if self._log_debug:
            self.logline('-> %s' % resp, logfun=logfun)
        else:
            self.log(resp[4:], logfun=logfun)

    def respond_w_warning(self, resp):
        self.respond(resp, logfun=logger.warning)

    def push_dtp_data(self, data, isproducer=False, file=None, cmd=None):
        """Pushes data into the data channel.

        It is usually called for those commands requiring some data to
        be sent over the data channel (e.g. RETR).
        If data channel does not exist yet, it queues the data to send
        later; data will then be pushed into data channel when
        _on_dtp_connection() will be called.

         - (str/classobj) data: the data to send which may be a string
            or a producer object).
         - (bool) isproducer: whether treat data as a producer.
         - (file) file: the file[-like] object to send (if any).
        """
        if self.data_channel is not None:
            self.respond(
                "125 Data connection already open. Transfer starting.")
            if file:
                self.data_channel.file_obj = file
            try:
                if not isproducer:
                    self.data_channel.push(data)
                else:
                    self.data_channel.push_with_producer(data)
                if self.data_channel is not None:
                    self.data_channel.cmd = cmd
                    self.data_channel.close_when_done()
            except Exception:
                # dealing with this exception is up to DTP (see bug #84)
                self.data_channel.handle_error()
        else:
            self.respond(
                "150 File status okay. About to open data connection.")
            self._out_dtp_queue = (data, isproducer, file, cmd)

    def flush_account(self):
        """Flush account information by clearing attributes that need
        to be reset on a REIN or new USER command.
        """
        self._shutdown_connecting_dtp()
        # if there's a transfer in progress RFC-959 states we are
        # supposed to let it finish
        if self.data_channel is not None:
            if not self.data_channel.transfer_in_progress():
                self.data_channel.close()
                self.data_channel = None

        username = self.username
        if self.authenticated and username:
            self.on_logout(username)
        self.authenticated = False
        self.username = ""
        self.password = ""
        self.attempted_logins = 0
        self._current_type = 'a'
        self._restart_position = 0
        self._quit_pending = False
        self._in_dtp_queue = None
        self._rnfr = None
        self._out_dtp_queue = None

    def run_as_current_user(self, function, *args, **kwargs):
        """Execute a function impersonating the current logged-in user."""
        self.authorizer.impersonate_user(self.username, self.password)
        try:
            return function(*args, **kwargs)
        finally:
            self.authorizer.terminate_impersonation(self.username)

    # --- logging wrappers

    # this is defined earlier
    # log_prefix = '%(remote_ip)s:%(remote_port)s-[%(username)s]'

    def log(self, msg, logfun=logger.info):
        """Log a message, including additional identifying session data."""
        prefix = self.log_prefix % self.__dict__
        logfun("%s %s" % (prefix, msg))

    def logline(self, msg, logfun=logger.debug):
        """Log a line including additional identifying session data.
        By default this is disabled unless logging level == DEBUG.
        """
        if self._log_debug:
            prefix = self.log_prefix % self.__dict__
            logfun("%s %s" % (prefix, msg))

    def logerror(self, msg):
        """Log an error including additional identifying session data."""
        prefix = self.log_prefix % self.__dict__
        logger.error("%s %s" % (prefix, msg))

    def log_exception(self, instance):
        """Log an unhandled exception. 'instance' is the instance
        where the exception was generated.
        """
        logger.exception("unhandled exception in instance %r", instance)

    # the list of commands which gets logged when logging level
    # is >= logging.INFO
    log_cmds_list = ["DELE", "RNFR", "RNTO", "MKD", "RMD", "CWD",
                     "XMKD", "XRMD", "XCWD",
                     "REIN", "SITE CHMOD", "MFMT"]

    def log_cmd(self, cmd, arg, respcode, respstr):
        """Log commands and responses in a standardized format.
        This is disabled in case the logging level is set to DEBUG.

         - (str) cmd:
            the command sent by client

         - (str) arg:
            the command argument sent by client.
            For filesystem commands such as DELE, MKD, etc. this is
            already represented as an absolute real filesystem path
            like "/home/user/file.ext".

         - (int) respcode:
            the response code as being sent by server. Response codes
            starting with 4xx or 5xx are returned if the command has
            been rejected for some reason.

         - (str) respstr:
            the response string as being sent by server.

        By default only DELE, RMD, RNTO, MKD, CWD, ABOR, REIN, SITE CHMOD
        commands are logged and the output is redirected to self.log
        method.

        Can be overridden to provide alternate formats or to log
        further commands.
        """
        if not self._log_debug and cmd in self.log_cmds_list:
            line = '%s %s' % (' '.join([cmd, arg]).strip(), respcode)
            if str(respcode)[0] in ('4', '5'):
                line += ' %r' % respstr
            self.log(line)

    def log_transfer(self, cmd, filename, receive, completed, elapsed, bytes):
        """Log all file transfers in a standardized format.

         - (str) cmd:
            the original command who caused the transfer.

         - (str) filename:
            the absolutized name of the file on disk.

         - (bool) receive:
            True if the transfer was used for client uploading (STOR,
            STOU, APPE), False otherwise (RETR).

         - (bool) completed:
            True if the file has been entirely sent, else False.

         - (float) elapsed:
            transfer elapsed time in seconds.

         - (int) bytes:
            number of bytes transmitted.
        """
        line = '%s %s completed=%s bytes=%s seconds=%s' % \
            (cmd, filename, completed and 1 or 0, bytes, elapsed)
        self.log(line)

    # --- connection
    def _make_eport(self, ip, port):
        """Establish an active data channel with remote client which
        issued a PORT or EPRT command.
        """
        # FTP bounce attacks protection: according to RFC-2577 it's
        # recommended to reject PORT if IP address specified in it
        # does not match client IP address.
        remote_ip = self.remote_ip
        if remote_ip.startswith('::ffff:'):
            # In this scenario, the server has an IPv6 socket, but
            # the remote client is using IPv4 and its address is
            # represented as an IPv4-mapped IPv6 address which
            # looks like this ::ffff:151.12.5.65, see:
            # http://en.wikipedia.org/wiki/IPv6#IPv4-mapped_addresses
            # http://tools.ietf.org/html/rfc3493.html#section-3.7
            # We truncate the first bytes to make it look like a
            # common IPv4 address.
            remote_ip = remote_ip[7:]
        if not self.permit_foreign_addresses and ip != remote_ip:
            msg = "501 Rejected data connection to foreign address %s:%s." \
                % (ip, port)
            self.respond_w_warning(msg)
            return

        # ...another RFC-2577 recommendation is rejecting connections
        # to privileged ports (< 1024) for security reasons.
        if not self.permit_privileged_ports and port < 1024:
            msg = '501 PORT against the privileged port "%s" refused.' % port
            self.respond_w_warning(msg)
            return

        # close establishing DTP instances, if any
        self._shutdown_connecting_dtp()

        if self.data_channel is not None:
            self.data_channel.close()
            self.data_channel = None

        # make sure we are not hitting the max connections limit
        if not self.server._accept_new_cons():
            msg = "425 Too many connections. Can't open data channel."
            self.respond_w_warning(msg)
            return

        # open data channel
        self._dtp_connector = self.active_dtp(ip, port, self)

    def _make_epasv(self, extmode=False):
        """Initialize a passive data channel with remote client which
        issued a PASV or EPSV command.
        If extmode argument is True we assume that client issued EPSV in
        which case extended passive mode will be used (see RFC-2428).
        """
        # close establishing DTP instances, if any
        self._shutdown_connecting_dtp()

        # close established data connections, if any
        if self.data_channel is not None:
            self.data_channel.close()
            self.data_channel = None

        # make sure we are not hitting the max connections limit
        if not self.server._accept_new_cons():
            msg = "425 Too many connections. Can't open data channel."
            self.respond_w_warning(msg)
            return

        # open data channel
        self._dtp_acceptor = self.passive_dtp(self, extmode)

    def ftp_PORT(self, line):
        """Start an active data channel by using IPv4."""
        if self._epsvall:
            self.respond("501 PORT not allowed after EPSV ALL.")
            return
        # Parse PORT request for getting IP and PORT.
        # Request comes in as:
        # > h1,h2,h3,h4,p1,p2
        # ...where the client's IP address is h1.h2.h3.h4 and the TCP
        # port number is (p1 * 256) + p2.
        try:
            addr = list(map(int, line.split(',')))
            if len(addr) != 6:
                raise ValueError
            for x in addr[:4]:
                if not 0 <= x <= 255:
                    raise ValueError
            ip = '%d.%d.%d.%d' % tuple(addr[:4])
            port = (addr[4] * 256) + addr[5]
            if not 0 <= port <= 65535:
                raise ValueError
        except (ValueError, OverflowError):
            self.respond("501 Invalid PORT format.")
            return
        self._make_eport(ip, port)

    def ftp_EPRT(self, line):
        """Start an active data channel by choosing the network protocol
        to use (IPv4/IPv6) as defined in RFC-2428.
        """
        if self._epsvall:
            self.respond("501 EPRT not allowed after EPSV ALL.")
            return
        # Parse EPRT request for getting protocol, IP and PORT.
        # Request comes in as:
        # <d>proto<d>ip<d>port<d>
        # ...where <d> is an arbitrary delimiter character (usually "|") and
        # <proto> is the network protocol to use (1 for IPv4, 2 for IPv6).
        try:
            af, ip, port = line.split(line[0])[1:-1]
            port = int(port)
            if not 0 <= port <= 65535:
                raise ValueError
        except (ValueError, IndexError, OverflowError):
            self.respond("501 Invalid EPRT format.")
            return

        if af == "1":
            # test if AF_INET6 and IPV6_V6ONLY
            if (self.socket.family == socket.AF_INET6 and not
                    SUPPORTS_HYBRID_IPV6):
                self.respond('522 Network protocol not supported (use 2).')
            else:
                try:
                    octs = list(map(int, ip.split('.')))
                    if len(octs) != 4:
                        raise ValueError
                    for x in octs:
                        if not 0 <= x <= 255:
                            raise ValueError
                except (ValueError, OverflowError):
                    self.respond("501 Invalid EPRT format.")
                else:
                    self._make_eport(ip, port)
        elif af == "2":
            if self.socket.family == socket.AF_INET:
                self.respond('522 Network protocol not supported (use 1).')
            else:
                self._make_eport(ip, port)
        else:
            if self.socket.family == socket.AF_INET:
                self.respond('501 Unknown network protocol (use 1).')
            else:
                self.respond('501 Unknown network protocol (use 2).')

    def ftp_PASV(self, line):
        """Start a passive data channel by using IPv4."""
        if self._epsvall:
            self.respond("501 PASV not allowed after EPSV ALL.")
            return
        self._make_epasv(extmode=False)

    def ftp_EPSV(self, line):
        """Start a passive data channel by using IPv4 or IPv6 as defined
        in RFC-2428.
        """
        # RFC-2428 specifies that if an optional parameter is given,
        # we have to determine the address family from that otherwise
        # use the same address family used on the control connection.
        # In such a scenario a client may use IPv4 on the control channel
        # and choose to use IPv6 for the data channel.
        # But how could we use IPv6 on the data channel without knowing
        # which IPv6 address to use for binding the socket?
        # Unfortunately RFC-2428 does not provide satisfying information
        # on how to do that.  The assumption is that we don't have any way
        # to know wich address to use, hence we just use the same address
        # family used on the control connection.
        if not line:
            self._make_epasv(extmode=True)
        # IPv4
        elif line == "1":
            if self.socket.family != socket.AF_INET:
                self.respond('522 Network protocol not supported (use 2).')
            else:
                self._make_epasv(extmode=True)
        # IPv6
        elif line == "2":
            if self.socket.family == socket.AF_INET:
                self.respond('522 Network protocol not supported (use 1).')
            else:
                self._make_epasv(extmode=True)
        elif line.lower() == 'all':
            self._epsvall = True
            self.respond(
                '220 Other commands other than EPSV are now disabled.')
        else:
            if self.socket.family == socket.AF_INET:
                self.respond('501 Unknown network protocol (use 1).')
            else:
                self.respond('501 Unknown network protocol (use 2).')

    def ftp_QUIT(self, line):
        """Quit the current session disconnecting the client."""
        if self.authenticated:
            msg_quit = self.authorizer.get_msg_quit(self.username)
        else:
            msg_quit = "Goodbye."
        if len(msg_quit) <= 75:
            self.respond("221 %s" % msg_quit)
        else:
            self.push("221-%s\r\n" % msg_quit)
            self.respond("221 ")

        # From RFC-959:
        # If file transfer is in progress, the connection must remain
        # open for result response and the server will then close it.
        # We also stop responding to any further command.
        if self.data_channel:
            self._quit_pending = True
            self.del_channel()
        else:
            self._shutdown_connecting_dtp()
            self.close_when_done()
        if self.authenticated and self.username:
            self.on_logout(self.username)

        # --- data transferring

    def ftp_LIST(self, path):
        """Return a list of files in the specified directory to the
        client.
        On success return the directory path, else None.
        """
        # - If no argument, fall back on cwd as default.
        # - Some older FTP clients erroneously issue /bin/ls-like LIST
        #   formats in which case we fall back on cwd as default.
        try:
            isdir = self.fs.isdir(path)
            if isdir:
                listing = self.run_as_current_user(self.fs.listdir, path)
                if isinstance(listing, list):
                    try:
                        # RFC 959 recommends the listing to be sorted.
                        listing.sort()
                    except UnicodeDecodeError:
                        # (Python 2 only) might happen on filesystem not
                        # supporting UTF8 meaning os.listdir() returned a list
                        # of mixed bytes and unicode strings:
                        # http://goo.gl/6DLHD
                        # http://bugs.python.org/issue683592
                        pass
                iterator = self.fs.format_list(path, listing)
            else:
                basedir, filename = os.path.split(path)
                self.fs.lstat(path)  # raise exc in case of problems
                iterator = self.fs.format_list(basedir, [filename])
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            producer = BufferedIteratorProducer(iterator)
            self.push_dtp_data(producer, isproducer=True, cmd="LIST")
            return path

    def ftp_NLST(self, path):
        """Return a list of files in the specified directory in a
        compact form to the client.
        On success return the directory path, else None.
        """
        try:
            if self.fs.isdir(path):
                listing = list(self.run_as_current_user(self.fs.listdir, path))
            else:
                # if path is a file we just list its name
                self.fs.lstat(path)  # raise exc in case of problems
                listing = [os.path.basename(path)]
        except (OSError, FilesystemError) as err:
            self.respond('550 %s.' % _strerror(err))
        else:
            data = ''
            if listing:
                try:
                    listing.sort()
                except UnicodeDecodeError:
                    # (Python 2 only) might happen on filesystem not
                    # supporting UTF8 meaning os.listdir() returned a list
                    # of mixed bytes and unicode strings:
                    # http://goo.gl/6DLHD
                    # http://bugs.python.org/issue683592
                    ls = []
                    for x in listing:
                        if not isinstance(x, unicode):
                            x = unicode(x, 'utf8')
                        ls.append(x)
                    listing = sorted(ls)
                data = '\r\n'.join(listing) + '\r\n'
            data = data.encode('utf8', self.unicode_errors)
            self.push_dtp_data(data, cmd="NLST")
            return path

        # --- MLST and MLSD commands

    # The MLST and MLSD commands are intended to standardize the file and
    # directory information returned by the server-FTP process.  These
    # commands differ from the LIST command in that the format of the
    # replies is strictly defined although extensible.

    def ftp_MLST(self, path):
        """Return information about a pathname in a machine-processable
        form as defined in RFC-3659.
        On success return the path just listed, else None.
        """
        line = self.fs.fs2ftp(path)
        basedir, basename = os.path.split(path)
        perms = self.authorizer.get_perms(self.username)
        try:
            iterator = self.run_as_current_user(
                self.fs.format_mlsx, basedir, [basename], perms,
                self._current_facts, ignore_err=False)
            data = b''.join(iterator)
        except (OSError, FilesystemError) as err:
            self.respond('550 %s.' % _strerror(err))
        else:
            data = data.decode('utf8', self.unicode_errors)
            # since TVFS is supported (see RFC-3659 chapter 6), a fully
            # qualified pathname should be returned
            data = data.split(' ')[0] + ' %s\r\n' % line
            # response is expected on the command channel
            self.push('250-Listing "%s":\r\n' % line)
            # the fact set must be preceded by a space
            self.push(' ' + data)
            self.respond('250 End MLST.')
            return path

    def ftp_MLSD(self, path):
        """Return contents of a directory in a machine-processable form
        as defined in RFC-3659.
        On success return the path just listed, else None.
        """
        # RFC-3659 requires 501 response code if path is not a directory
        if not self.fs.isdir(path):
            self.respond("501 No such directory.")
            return
        try:
            listing = self.run_as_current_user(self.fs.listdir, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            perms = self.authorizer.get_perms(self.username)
            iterator = self.fs.format_mlsx(path, listing, perms,
                                           self._current_facts)
            producer = BufferedIteratorProducer(iterator)
            self.push_dtp_data(producer, isproducer=True, cmd="MLSD")
            return path

    def ftp_RETR(self, file):
        """Retrieve the specified file (transfer from the server to the
        client).  On success return the file path else None.
        """
        rest_pos = self._restart_position
        self._restart_position = 0
        try:
            fd = self.run_as_current_user(self.fs.open, file, 'rb')
        except (EnvironmentError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
            return

        try:
            if rest_pos:
                # Make sure that the requested offset is valid (within the
                # size of the file being resumed).
                # According to RFC-1123 a 554 reply may result in case that
                # the existing file cannot be repositioned as specified in
                # the REST.
                ok = 0
                try:
                    fsize = self.fs.getsize(file)
                    if rest_pos > fsize:
                        raise ValueError
                    fd.seek(rest_pos)
                    ok = 1
                except ValueError:
                    why = "REST position (%s) > file size (%s)" % (
                        rest_pos, fsize)
                except (EnvironmentError, FilesystemError) as err:
                    why = _strerror(err)
                if not ok:
                    fd.close()
                    self.respond('554 %s' % why)
                    return
            producer = FileProducer(fd, self._current_type)
            self.push_dtp_data(producer, isproducer=True, file=fd, cmd="RETR")
            return file
        except Exception:
            fd.close()
            raise

    def ftp_STOR(self, file, mode='w'):
        """Store a file (transfer from the client to the server).
        On success return the file path, else None.
        """
        # A resume could occur in case of APPE or REST commands.
        # In that case we have to open file object in different ways:
        # STOR: mode = 'w'
        # APPE: mode = 'a'
        # REST: mode = 'r+' (to permit seeking on file object)
        cmd = 'APPE' if 'a' in mode else 'STOR'
        rest_pos = self._restart_position
        self._restart_position = 0
        if rest_pos:
            mode = 'r+'
        try:
            fd = self.run_as_current_user(self.fs.open, file, mode + 'b')
        except (EnvironmentError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
            return

        try:
            if rest_pos:
                # Make sure that the requested offset is valid (within the
                # size of the file being resumed).
                # According to RFC-1123 a 554 reply may result in case
                # that the existing file cannot be repositioned as
                # specified in the REST.
                ok = 0
                try:
                    fsize = self.fs.getsize(file)
                    if rest_pos > fsize:
                        raise ValueError
                    fd.seek(rest_pos)
                    ok = 1
                except ValueError:
                    why = "REST position (%s) > file size (%s)" % (
                        rest_pos, fsize)
                except (EnvironmentError, FilesystemError) as err:
                    why = _strerror(err)
                if not ok:
                    fd.close()
                    self.respond('554 %s' % why)
                    return

            if self.data_channel is not None:
                resp = "Data connection already open. Transfer starting."
                self.respond("125 " + resp)
                self.data_channel.file_obj = fd
                self.data_channel.enable_receiving(self._current_type, cmd)
            else:
                resp = "File status okay. About to open data connection."
                self.respond("150 " + resp)
                self._in_dtp_queue = (fd, cmd)
            return file
        except Exception:
            fd.close()
            raise

    def ftp_STOU(self, line):
        """Store a file on the server with a unique name.
        On success return the file path, else None.
        """
        # Note 1: RFC-959 prohibited STOU parameters, but this
        # prohibition is obsolete.
        # Note 2: 250 response wanted by RFC-959 has been declared
        # incorrect in RFC-1123 that wants 125/150 instead.
        # Note 3: RFC-1123 also provided an exact output format
        # defined to be as follow:
        # > 125 FILE: pppp
        # ...where pppp represents the unique path name of the
        # file that will be written.

        # watch for STOU preceded by REST, which makes no sense.
        if self._restart_position:
            self.respond("450 Can't STOU while REST request is pending.")
            return

        if line:
            basedir, prefix = os.path.split(self.fs.ftp2fs(line))
            prefix = prefix + '.'
        else:
            basedir = self.fs.ftp2fs(self.fs.cwd)
            prefix = 'ftpd.'
        try:
            fd = self.run_as_current_user(self.fs.mkstemp, prefix=prefix,
                                          dir=basedir)
        except (EnvironmentError, FilesystemError) as err:
            # likely, we hit the max number of retries to find out a
            # file with a unique name
            if getattr(err, "errno", -1) == errno.EEXIST:
                why = 'No usable unique file name found'
            # something else happened
            else:
                why = _strerror(err)
            self.respond("450 %s." % why)
            return

        try:
            if not self.authorizer.has_perm(self.username, 'w', fd.name):
                try:
                    fd.close()
                    self.run_as_current_user(self.fs.remove, fd.name)
                except (OSError, FilesystemError):
                    pass
                self.respond("550 Not enough privileges.")
                return

            # now just acts like STOR except that restarting isn't allowed
            filename = os.path.basename(fd.name)
            if self.data_channel is not None:
                self.respond("125 FILE: %s" % filename)
                self.data_channel.file_obj = fd
                self.data_channel.enable_receiving(self._current_type, "STOU")
            else:
                self.respond("150 FILE: %s" % filename)
                self._in_dtp_queue = (fd, "STOU")
            return filename
        except Exception:
            fd.close()
            raise

    def ftp_APPE(self, file):
        """Append data to an existing file on the server.
        On success return the file path, else None.
        """
        # watch for APPE preceded by REST, which makes no sense.
        if self._restart_position:
            self.respond("450 Can't APPE while REST request is pending.")
        else:
            return self.ftp_STOR(file, mode='a')

    def ftp_REST(self, line):
        """Restart a file transfer from a previous mark."""
        if self._current_type == 'a':
            self.respond('501 Resuming transfers not allowed in ASCII mode.')
            return
        try:
            marker = int(line)
            if marker < 0:
                raise ValueError
        except (ValueError, OverflowError):
            self.respond("501 Invalid parameter.")
        else:
            self.respond("350 Restarting at position %s." % marker)
            self._restart_position = marker

    def ftp_ABOR(self, line):
        """Abort the current data transfer."""
        # ABOR received while no data channel exists
        if self._dtp_acceptor is None and \
                self._dtp_connector is None and \
                self.data_channel is None:
            self.respond("225 No transfer to abort.")
            return
        else:
            # a PASV or PORT was received but connection wasn't made yet
            if self._dtp_acceptor is not None or \
                    self._dtp_connector is not None:
                self._shutdown_connecting_dtp()
                resp = "225 ABOR command successful; data channel closed."

            # If a data transfer is in progress the server must first
            # close the data connection, returning a 426 reply to
            # indicate that the transfer terminated abnormally, then it
            # must send a 226 reply, indicating that the abort command
            # was successfully processed.
            # If no data has been transmitted we just respond with 225
            # indicating that no transfer was in progress.
            if self.data_channel is not None:
                if self.data_channel.transfer_in_progress():
                    self.data_channel.close()
                    self.data_channel = None
                    self.respond("426 Transfer aborted via ABOR.",
                                 logfun=logger.info)
                    resp = "226 ABOR command successful."
                else:
                    self.data_channel.close()
                    self.data_channel = None
                    resp = "225 ABOR command successful; data channel closed."
        self.respond(resp)

        # --- authentication
    def ftp_USER(self, line):
        """Set the username for the current session."""
        # RFC-959 specifies a 530 response to the USER command if the
        # username is not valid.  If the username is valid is required
        # ftpd returns a 331 response instead.  In order to prevent a
        # malicious client from determining valid usernames on a server,
        # it is suggested by RFC-2577 that a server always return 331 to
        # the USER command and then reject the combination of username
        # and password for an invalid username when PASS is provided later.
        if not self.authenticated:
            self.respond('331 Username ok, send password.')
        else:
            # a new USER command could be entered at any point in order
            # to change the access control flushing any user, password,
            # and account information already supplied and beginning the
            # login sequence again.
            self.flush_account()
            msg = 'Previous account information was flushed'
            self.respond('331 %s, send password.' % msg, logfun=logger.info)
        self.username = line

    def handle_auth_failed(self, msg, password):
        def callback(username, password, msg):
            self.add_channel()
            if hasattr(self, '_closed') and not self._closed:
                self.attempted_logins += 1
                if self.attempted_logins >= self.max_login_attempts:
                    msg += " Disconnecting."
                    self.respond("530 " + msg)
                    self.close_when_done()
                else:
                    self.respond("530 " + msg)
                self.log("USER '%s' failed login." % username)
            self.on_login_failed(username, password)

        self.del_channel()
        if not msg:
            if self.username == 'anonymous':
                msg = "Anonymous access not allowed."
            else:
                msg = "Authentication failed."
        else:
            # response string should be capitalized as per RFC-959
            msg = msg.capitalize()
        self.ioloop.call_later(self.auth_failed_timeout, callback,
                               self.username, password, msg,
                               _errback=self.handle_error)
        self.username = ""

    def handle_auth_success(self, home, password, msg_login):
        if not isinstance(home, unicode):
            if PY3:
                raise TypeError('type(home) != text')
            else:
                warnings.warn(
                    '%s.get_home_dir returned a non-unicode string; now '
                    'casting to unicode' % (
                        self.authorizer.__class__.__name__),
                    RuntimeWarning, stacklevel=2)
                home = home.decode('utf8')

        if len(msg_login) <= 75:
            self.respond('230 %s' % msg_login)
        else:
            self.push("230-%s\r\n" % msg_login)
            self.respond("230 ")
        self.log("USER '%s' logged in." % self.username)
        self.authenticated = True
        self.password = password
        self.attempted_logins = 0

        self.fs = self.abstracted_fs(home, self)
        self.on_login(self.username)

    def ftp_PASS(self, line):
        """Check username's password against the authorizer."""
        if self.authenticated:
            self.respond("503 User already authenticated.")
            return
        if not self.username:
            self.respond("503 Login with USER first.")
            return

        try:
            self.authorizer.validate_authentication(self.username, line, self)
            home = self.authorizer.get_home_dir(self.username)
            msg_login = self.authorizer.get_msg_login(self.username)
        except (AuthenticationFailed, AuthorizerError) as err:
            self.handle_auth_failed(str(err), line)
        else:
            self.handle_auth_success(home, line, msg_login)

    def ftp_REIN(self, line):
        """Reinitialize user's current session."""
        # From RFC-959:
        # REIN command terminates a USER, flushing all I/O and account
        # information, except to allow any transfer in progress to be
        # completed.  All parameters are reset to the default settings
        # and the control connection is left open.  This is identical
        # to the state in which a user finds himself immediately after
        # the control connection is opened.
        self.flush_account()
        # Note: RFC-959 erroneously mention "220" as the correct response
        # code to be given in this case, but this is wrong...
        self.respond("230 Ready for new user.")

        # --- filesystem operations
    def ftp_PWD(self, line):
        """Return the name of the current working directory to the client."""
        # The 257 response is supposed to include the directory
        # name and in case it contains embedded double-quotes
        # they must be doubled (see RFC-959, chapter 7, appendix 2).
        cwd = self.fs.cwd
        assert isinstance(cwd, unicode), cwd
        self.respond('257 "%s" is the current directory.'
                     % cwd.replace('"', '""'))

    def ftp_CWD(self, path):
        """Change the current working directory.
        On success return the new directory path, else None.
        """
        # Temporarily join the specified directory to see if we have
        # permissions to do so, then get back to original process's
        # current working directory.
        # Note that if for some reason os.getcwd() gets removed after
        # the process is started we'll get into troubles (os.getcwd()
        # will fail with ENOENT) but we can't do anything about that
        # except logging an error.
        init_cwd = getcwdu()
        try:
            self.run_as_current_user(self.fs.chdir, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            cwd = self.fs.cwd
            assert isinstance(cwd, unicode), cwd
            self.respond('250 "%s" is the current directory.' % cwd)
            if getcwdu() != init_cwd:
                os.chdir(init_cwd)
            return path

    def ftp_CDUP(self, path):
        """Change into the parent directory.
        On success return the new directory, else None.
        """
        # Note: RFC-959 says that code 200 is required but it also says
        # that CDUP uses the same codes as CWD.
        return self.ftp_CWD(path)

    def ftp_SIZE(self, path):
        """Return size of file in a format suitable for using with
        RESTart as defined in RFC-3659."""

        # Implementation note: properly handling the SIZE command when
        # TYPE ASCII is used would require to scan the entire file to
        # perform the ASCII translation logic
        # (file.read().replace(os.linesep, '\r\n')) and then calculating
        # the len of such data which may be different than the actual
        # size of the file on the server.  Considering that calculating
        # such result could be very resource-intensive and also dangerous
        # (DoS) we reject SIZE when the current TYPE is ASCII.
        # However, clients in general should not be resuming downloads
        # in ASCII mode.  Resuming downloads in binary mode is the
        # recommended way as specified in RFC-3659.

        line = self.fs.fs2ftp(path)
        if self._current_type == 'a':
            why = "SIZE not allowed in ASCII mode"
            self.respond("550 %s." % why)
            return
        if not self.fs.isfile(self.fs.realpath(path)):
            why = "%s is not retrievable" % line
            self.respond("550 %s." % why)
            return
        try:
            size = self.run_as_current_user(self.fs.getsize, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("213 %s" % size)

    def ftp_MDTM(self, path):
        """Return last modification time of file to the client as an ISO
        3307 style timestamp (YYYYMMDDHHMMSS) as defined in RFC-3659.
        On success return the file path, else None.
        """
        line = self.fs.fs2ftp(path)
        if not self.fs.isfile(self.fs.realpath(path)):
            self.respond("550 %s is not retrievable" % line)
            return
        timefunc = time.gmtime if self.use_gmt_times else time.localtime
        try:
            secs = self.run_as_current_user(self.fs.getmtime, path)
            lmt = time.strftime("%Y%m%d%H%M%S", timefunc(secs))
        except (ValueError, OSError, FilesystemError) as err:
            if isinstance(err, ValueError):
                # It could happen if file's last modification time
                # happens to be too old (prior to year 1900)
                why = "Can't determine file's last modification time"
            else:
                why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("213 %s" % lmt)
            return path

    def ftp_MFMT(self, path, timeval):
        """ Sets the last modification time of file to timeval
        3307 style timestamp (YYYYMMDDHHMMSS) as defined in RFC-3659.
        On success return the modified time and file path, else None.
        """
        # Note: the MFMT command is not a formal RFC command
        # but stated in the following MEMO:
        # https://tools.ietf.org/html/draft-somers-ftp-mfxx-04
        # this is implemented to assist with file synchronization

        line = self.fs.fs2ftp(path)

        if len(timeval) != len("YYYYMMDDHHMMSS"):
            why = "Invalid time format; expected: YYYYMMDDHHMMSS"
            self.respond('550 %s.' % why)
            return
        if not self.fs.isfile(self.fs.realpath(path)):
            self.respond("550 %s is not retrievable" % line)
            return
        timefunc = time.gmtime if self.use_gmt_times else time.localtime
        try:
            # convert timeval string to epoch seconds
            epoch = datetime.utcfromtimestamp(0)
            timeval_datetime_obj = datetime.strptime(timeval, '%Y%m%d%H%M%S')
            timeval_secs = (timeval_datetime_obj - epoch).total_seconds()
        except ValueError:
            why = "Invalid time format; expected: YYYYMMDDHHMMSS"
            self.respond('550 %s.' % why)
            return
        try:
            # Modify Time
            self.run_as_current_user(self.fs.utime, path, timeval_secs)
            # Fetch Time
            secs = self.run_as_current_user(self.fs.getmtime, path)
            lmt = time.strftime("%Y%m%d%H%M%S", timefunc(secs))
        except (ValueError, OSError, FilesystemError) as err:
            if isinstance(err, ValueError):
                # It could happen if file's last modification time
                # happens to be too old (prior to year 1900)
                why = "Can't determine file's last modification time"
            else:
                why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("213 Modify=%s; %s." % (lmt, line))
            return (lmt, path)

    def ftp_MKD(self, path):
        """Create the specified directory.
        On success return the directory path, else None.
        """
        line = self.fs.fs2ftp(path)
        try:
            self.run_as_current_user(self.fs.mkdir, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            # The 257 response is supposed to include the directory
            # name and in case it contains embedded double-quotes
            # they must be doubled (see RFC-959, chapter 7, appendix 2).
            self.respond(
                '257 "%s" directory created.' % line.replace('"', '""'))
            return path

    def ftp_RMD(self, path):
        """Remove the specified directory.
        On success return the directory path, else None.
        """
        if self.fs.realpath(path) == self.fs.realpath(self.fs.root):
            msg = "Can't remove root directory."
            self.respond("550 %s" % msg)
            return
        try:
            self.run_as_current_user(self.fs.rmdir, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("250 Directory removed.")

    def ftp_DELE(self, path):
        """Delete the specified file.
        On success return the file path, else None.
        """
        try:
            self.run_as_current_user(self.fs.remove, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("250 File removed.")
            return path

    def ftp_RNFR(self, path):
        """Rename the specified (only the source name is specified
        here, see RNTO command)."""
        if not self.fs.lexists(path):
            self.respond("550 No such file or directory.")
        elif self.fs.realpath(path) == self.fs.realpath(self.fs.root):
            self.respond("550 Can't rename home directory.")
        else:
            self._rnfr = path
            self.respond("350 Ready for destination name.")

    def ftp_RNTO(self, path):
        """Rename file (destination name only, source is specified with
        RNFR).
        On success return a (source_path, destination_path) tuple.
        """
        if not self._rnfr:
            self.respond("503 Bad sequence of commands: use RNFR first.")
            return
        src = self._rnfr
        self._rnfr = None
        try:
            self.run_as_current_user(self.fs.rename, src, path)
        except (OSError, FilesystemError) as err:
            why = _strerror(err)
            self.respond('550 %s.' % why)
        else:
            self.respond("250 Renaming ok.")
            return (src, path)

        # --- others
    def ftp_TYPE(self, line):
        """Set current type data type to binary/ascii."""
        type = line.upper().replace(' ', '')
        if type in ("A", "L7"):
            self.respond("200 Type set to: ASCII.")
            self._current_type = 'a'
        elif type in ("I", "L8"):
            self.respond("200 Type set to: Binary.")
            self._current_type = 'i'
        else:
            self.respond('504 Unsupported type "%s".' % line)

    def ftp_STRU(self, line):
        """Set file structure ("F" is the only one supported (noop))."""
        stru = line.upper()
        if stru == 'F':
            self.respond('200 File transfer structure set to: F.')
        elif stru in ('P', 'R'):
            # R is required in minimum implementations by RFC-959, 5.1.
            # RFC-1123, 4.1.2.13, amends this to only apply to servers
            # whose file systems support record structures, but also
            # suggests that such a server "may still accept files with
            # STRU R, recording the byte stream literally".
            # Should we accept R but with no operational difference from
            # F? proftpd and wu-ftpd don't accept STRU R. We just do
            # the same.
            #
            # RFC-1123 recommends against implementing P.
            self.respond('504 Unimplemented STRU type.')
        else:
            self.respond('501 Unrecognized STRU type.')

    def ftp_MODE(self, line):
        """Set data transfer mode ("S" is the only one supported (noop))."""
        mode = line.upper()
        if mode == 'S':
            self.respond('200 Transfer mode set to: S')
        elif mode in ('B', 'C'):
            self.respond('504 Unimplemented MODE type.')
        else:
            self.respond('501 Unrecognized MODE type.')

    def ftp_STAT(self, path):
        """Return statistics about current ftp session. If an argument
        is provided return directory listing over command channel.

        Implementation note:

        RFC-959 does not explicitly mention globbing but many FTP
        servers do support it as a measure of convenience for FTP
        clients and users.

        In order to search for and match the given globbing expression,
        the code has to search (possibly) many directories, examine
        each contained filename, and build a list of matching files in
        memory.  Since this operation can be quite intensive, both CPU-
        and memory-wise, we do not support globbing.
        """
        # return STATus information about ftpd
        if not path:
            s = []
            s.append('Connected to: %s:%s' % self.socket.getsockname()[:2])
            if self.authenticated:
                s.append('Logged in as: %s' % self.username)
            else:
                if not self.username:
                    s.append("Waiting for username.")
                else:
                    s.append("Waiting for password.")
            type = 'ASCII' if self._current_type == 'a' else 'Binary'
            s.append("TYPE: %s; STRUcture: File; MODE: Stream" % type)
            if self._dtp_acceptor is not None:
                s.append('Passive data channel waiting for connection.')
            elif self.data_channel is not None:
                bytes_sent = self.data_channel.tot_bytes_sent
                bytes_recv = self.data_channel.tot_bytes_received
                elapsed_time = self.data_channel.get_elapsed_time()
                s.append('Data connection open:')
                s.append('Total bytes sent: %s' % bytes_sent)
                s.append('Total bytes received: %s' % bytes_recv)
                s.append('Transfer elapsed time: %s secs' % elapsed_time)
            else:
                s.append('Data connection closed.')

            self.push('211-FTP server status:\r\n')
            self.push(''.join([' %s\r\n' % item for item in s]))
            self.respond('211 End of status.')
        # return directory LISTing over the command channel
        else:
            line = self.fs.fs2ftp(path)
            try:
                isdir = self.fs.isdir(path)
                if isdir:
                    listing = self.run_as_current_user(self.fs.listdir, path)
                    if isinstance(listing, list):
                        try:
                            # RFC 959 recommends the listing to be sorted.
                            listing.sort()
                        except UnicodeDecodeError:
                            # (Python 2 only) might happen on filesystem not
                            # supporting UTF8 meaning os.listdir() returned a
                            # list of mixed bytes and unicode strings:
                            # http://goo.gl/6DLHD
                            # http://bugs.python.org/issue683592
                            pass
                    iterator = self.fs.format_list(path, listing)
                else:
                    basedir, filename = os.path.split(path)
                    self.fs.lstat(path)  # raise exc in case of problems
                    iterator = self.fs.format_list(basedir, [filename])
            except (OSError, FilesystemError) as err:
                why = _strerror(err)
                self.respond('550 %s.' % why)
            else:
                self.push('213-Status of "%s":\r\n' % line)
                self.push_with_producer(BufferedIteratorProducer(iterator))
                self.respond('213 End of status.')
                return path

    def ftp_FEAT(self, line):
        """List all new features supported as defined in RFC-2398."""
        features = set(['UTF8', 'TVFS'])
        features.update([feat for feat in
                         ('EPRT', 'EPSV', 'MDTM', 'MFMT', 'SIZE')
                         if feat in self.proto_cmds])
        features.update(self._extra_feats)
        if 'MLST' in self.proto_cmds or 'MLSD' in self.proto_cmds:
            facts = ''
            for fact in self._available_facts:
                if fact in self._current_facts:
                    facts += fact + '*;'
                else:
                    facts += fact + ';'
            features.add('MLST ' + facts)
        if 'REST' in self.proto_cmds:
            features.add('REST STREAM')
        features = sorted(features)
        self.push("211-Features supported:\r\n")
        self.push("".join([" %s\r\n" % x for x in features]))
        self.respond('211 End FEAT.')

    def ftp_OPTS(self, line):
        """Specify options for FTP commands as specified in RFC-2389."""
        try:
            if line.count(' ') > 1:
                raise ValueError('Invalid number of arguments')
            if ' ' in line:
                cmd, arg = line.split(' ')
                if ';' not in arg:
                    raise ValueError('Invalid argument')
            else:
                cmd, arg = line, ''
            # actually the only command able to accept options is MLST
            if cmd.upper() != 'MLST' or 'MLST' not in self.proto_cmds:
                raise ValueError('Unsupported command "%s"' % cmd)
        except ValueError as err:
            self.respond('501 %s.' % err)
        else:
            facts = [x.lower() for x in arg.split(';')]
            self._current_facts = \
                [x for x in facts if x in self._available_facts]
            f = ''.join([x + ';' for x in self._current_facts])
            self.respond('200 MLST OPTS ' + f)

    def ftp_NOOP(self, line):
        """Do nothing."""
        self.respond("200 I successfully did nothing'.")

    def ftp_SYST(self, line):
        """Return system type (always returns UNIX type: L8)."""
        # This command is used to find out the type of operating system
        # at the server.  The reply shall have as its first word one of
        # the system names listed in RFC-943.
        # Since that we always return a "/bin/ls -lA"-like output on
        # LIST we  prefer to respond as if we would on Unix in any case.
        self.respond("215 UNIX Type: L8")

    def ftp_ALLO(self, line):
        """Allocate bytes for storage (noop)."""
        # not necessary (always respond with 202)
        self.respond("202 No storage allocation necessary.")

    def ftp_HELP(self, line):
        """Return help text to the client."""
        if line:
            line = line.upper()
            if line in self.proto_cmds:
                self.respond("214 %s" % self.proto_cmds[line]['help'])
            else:
                self.respond("501 Unrecognized command.")
        else:
            # provide a compact list of recognized commands
            def formatted_help():
                cmds = []
                keys = sorted([x for x in self.proto_cmds
                               if not x.startswith('SITE ')])
                while keys:
                    elems = tuple(keys[0:8])
                    cmds.append(' %-6s' * len(elems) % elems + '\r\n')
                    del keys[0:8]
                return ''.join(cmds)

            self.push("214-The following commands are recognized:\r\n")
            self.push(formatted_help())
            self.respond("214 Help command successful.")

        # --- site commands

    # The user willing to add support for a specific SITE command must
    # update self.proto_cmds dictionary and define a new ftp_SITE_%CMD%
    # method in the subclass.

    def ftp_SITE_CHMOD(self, path, mode):
        """Change file mode.
        On success return a (file_path, mode) tuple.
        """
        # Note: although most UNIX servers implement it, SITE CHMOD is not
        # defined in any official RFC.
        try:
            assert len(mode) in (3, 4)
            for x in mode:
                assert 0 <= int(x) <= 7
            mode = int(mode, 8)
        except (AssertionError, ValueError):
            self.respond("501 Invalid SITE CHMOD format.")
        else:
            try:
                self.run_as_current_user(self.fs.chmod, path, mode)
            except (OSError, FilesystemError) as err:
                why = _strerror(err)
                self.respond('550 %s.' % why)
            else:
                self.respond('200 SITE CHMOD successful.')
                return (path, mode)

    def ftp_SITE_HELP(self, line):
        """Return help text to the client for a given SITE command."""
        if line:
            line = line.upper()
            if line in self.proto_cmds:
                self.respond("214 %s" % self.proto_cmds[line]['help'])
            else:
                self.respond("501 Unrecognized SITE command.")
        else:
            self.push("214-The following SITE commands are recognized:\r\n")
            site_cmds = []
            for cmd in sorted(self.proto_cmds.keys()):
                if cmd.startswith('SITE '):
                    site_cmds.append(' %s\r\n' % cmd[5:])
            self.push(''.join(site_cmds))
            self.respond("214 Help SITE command successful.")

        # --- support for deprecated cmds

    # RFC-1123 requires that the server treat XCUP, XCWD, XMKD, XPWD
    # and XRMD commands as synonyms for CDUP, CWD, MKD, LIST and RMD.
    # Such commands are obsoleted but some ftp clients (e.g. Windows
    # ftp.exe) still use them.

    def ftp_XCUP(self, line):
        """Change to the parent directory. Synonym for CDUP. Deprecated."""
        return self.ftp_CDUP(line)

    def ftp_XCWD(self, line):
        """Change the current working directory. Synonym for CWD.
        Deprecated."""
        return self.ftp_CWD(line)

    def ftp_XMKD(self, line):
        """Create the specified directory. Synonym for MKD. Deprecated."""
        return self.ftp_MKD(line)

    def ftp_XPWD(self, line):
        """Return the current working directory. Synonym for PWD.
        Deprecated."""
        return self.ftp_PWD(line)

    def ftp_XRMD(self, line):
        """Remove the specified directory. Synonym for RMD. Deprecated."""
        return self.ftp_RMD(line)


# ===================================================================
# --- FTP over SSL
# ===================================================================


if SSL is not None:

    class SSLConnection(_AsyncChatNewStyle):
        """An AsyncChat subclass supporting TLS/SSL."""

        _ssl_accepting = False
        _ssl_established = False
        _ssl_closing = False
        _ssl_requested = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._error = False
            self._ssl_want_read = False
            self._ssl_want_write = False

        def readable(self):
            return self._ssl_accepting or \
                self._ssl_want_read or \
                super().readable()

        def writable(self):
            return self._ssl_want_write or super().writable()

        def secure_connection(self, ssl_context):
            """Secure the connection switching from plain-text to
            SSL/TLS.
            """
            debug("securing SSL connection", self)
            self._ssl_requested = True
            try:
                self.socket = SSL.Connection(ssl_context, self.socket)
            except socket.error as err:
                # may happen in case the client connects/disconnects
                # very quickly
                debug(
                    "call: secure_connection(); can't secure SSL connection "
                    "%r; closing" % err, self)
                self.close()
            except ValueError:
                # may happen in case the client connects/disconnects
                # very quickly
                if self.socket.fileno() == -1:
                    debug(
                        "ValueError and fd == -1 on secure_connection()", self)
                    return
                raise
            else:
                self.socket.set_accept_state()
                self._ssl_accepting = True

        @contextlib.contextmanager
        def _handle_ssl_want_rw(self):
            prev_row_pending = self._ssl_want_read or self._ssl_want_write
            try:
                yield
            except SSL.WantReadError:
                # we should never get here; it's just for extra safety
                self._ssl_want_read = True
            except SSL.WantWriteError:
                # we should never get here; it's just for extra safety
                self._ssl_want_write = True

            if self._ssl_want_read:
                self.modify_ioloop_events(
                    self._wanted_io_events | self.ioloop.READ, logdebug=True)
            elif self._ssl_want_write:
                self.modify_ioloop_events(
                    self._wanted_io_events | self.ioloop.WRITE, logdebug=True)
            else:
                if prev_row_pending:
                    self.modify_ioloop_events(self._wanted_io_events)

        def _do_ssl_handshake(self):
            self._ssl_accepting = True
            self._ssl_want_read = False
            self._ssl_want_write = False
            try:
                self.socket.do_handshake()
            except SSL.WantReadError:
                self._ssl_want_read = True
                debug("call: _do_ssl_handshake, err: ssl-want-read", inst=self)
            except SSL.WantWriteError:
                self._ssl_want_write = True
                debug("call: _do_ssl_handshake, err: ssl-want-write",
                      inst=self)
            except SSL.SysCallError as err:
                debug("call: _do_ssl_handshake, err: %r" % err, inst=self)
                retval, desc = err.args
                if (retval == -1 and desc == 'Unexpected EOF') or retval > 0:
                    # Happens when the other side closes the socket before
                    # completing the SSL handshake, e.g.:
                    # client.sock.sendall(b"PORT ...\r\n")
                    # client.getresp()
                    # sock, _ = sock.accept()
                    # sock.close()
                    self.log("Unexpected SSL EOF.")
                    self.close()
                else:
                    raise
            except SSL.Error as err:
                debug("call: _do_ssl_handshake, err: %r" % err, inst=self)
                self.handle_failed_ssl_handshake()
            else:
                debug("SSL connection established", self)
                self._ssl_accepting = False
                self._ssl_established = True
                self.handle_ssl_established()

        def handle_ssl_established(self):
            """Called when SSL handshake has completed."""

        def handle_ssl_shutdown(self):
            """Called when SSL shutdown() has completed."""
            super().close()

        def handle_failed_ssl_handshake(self):
            raise NotImplementedError("must be implemented in subclass")

        def handle_read_event(self):
            if not self._ssl_requested:
                super().handle_read_event()
            else:
                with self._handle_ssl_want_rw():
                    self._ssl_want_read = False
                    if self._ssl_accepting:
                        self._do_ssl_handshake()
                    elif self._ssl_closing:
                        self._do_ssl_shutdown()
                    else:
                        super().handle_read_event()

        def handle_write_event(self):
            if not self._ssl_requested:
                super().handle_write_event()
            else:
                with self._handle_ssl_want_rw():
                    self._ssl_want_write = False
                    if self._ssl_accepting:
                        self._do_ssl_handshake()
                    elif self._ssl_closing:
                        self._do_ssl_shutdown()
                    else:
                        super().handle_write_event()

        def handle_error(self):
            self._error = True
            try:
                raise
            except Exception:
                self.log_exception(self)
            # when facing an unhandled exception in here it's better
            # to rely on base class (FTPHandler or DTPHandler)
            # close() method as it does not imply SSL shutdown logic
            try:
                super().close()
            except Exception:
                logger.critical(traceback.format_exc())

        def send(self, data):
            if not isinstance(data, bytes):
                data = bytes(data)
            try:
                return super().send(data)
            except SSL.WantReadError:
                debug("call: send(), err: ssl-want-read", inst=self)
                self._ssl_want_read = True
                return 0
            except SSL.WantWriteError:
                debug("call: send(), err: ssl-want-write", inst=self)
                self._ssl_want_write = True
                return 0
            except SSL.ZeroReturnError:
                debug(
                    "call: send() -> shutdown(), err: zero-return", inst=self)
                super().handle_close()
                return 0
            except SSL.SysCallError as err:
                debug("call: send(), err: %r" % err, inst=self)
                errnum, errstr = err.args
                if errnum == errno.EWOULDBLOCK:
                    return 0
                elif errnum in _ERRNOS_DISCONNECTED or \
                        errstr == 'Unexpected EOF':
                    super().handle_close()
                    return 0
                else:
                    raise

        def recv(self, buffer_size):
            try:
                return super().recv(buffer_size)
            except SSL.WantReadError:
                debug("call: recv(), err: ssl-want-read", inst=self)
                self._ssl_want_read = True
                raise RetryError
            except SSL.WantWriteError:
                debug("call: recv(), err: ssl-want-write", inst=self)
                self._ssl_want_write = True
                raise RetryError
            except SSL.ZeroReturnError:
                debug("call: recv() -> shutdown(), err: zero-return",
                      inst=self)
                super().handle_close()
                return b''
            except SSL.SysCallError as err:
                debug("call: recv(), err: %r" % err, inst=self)
                errnum, errstr = err.args
                if errnum in _ERRNOS_DISCONNECTED or \
                        errstr == 'Unexpected EOF':
                    super().handle_close()
                    return b''
                else:
                    raise

        def _do_ssl_shutdown(self):
            """Executes a SSL_shutdown() call to revert the connection
            back to clear-text.
            twisted/internet/tcp.py code has been used as an example.
            """
            self._ssl_closing = True
            if os.name == 'posix':
                # since SSL_shutdown() doesn't report errors, an empty
                # write call is done first, to try to detect if the
                # connection has gone away
                try:
                    os.write(self.socket.fileno(), b'')
                except (OSError, socket.error) as err:
                    debug(
                        "call: _do_ssl_shutdown() -> os.write, err: %r" % err,
                        inst=self)
                    if err.errno in (errno.EINTR, errno.EWOULDBLOCK,
                                     errno.ENOBUFS):
                        return
                    elif err.errno in _ERRNOS_DISCONNECTED:
                        return super().close()
                    else:
                        raise
            # Ok, this a mess, but the underlying OpenSSL API simply
            # *SUCKS* and I really couldn't do any better.
            #
            # Here we just want to shutdown() the SSL layer and then
            # close() the connection so we're not interested in a
            # complete SSL shutdown() handshake, so let's pretend
            # we already received a "RECEIVED" shutdown notification
            # from the client.
            # Once the client received our "SENT" shutdown notification
            # then we close() the connection.
            #
            # Since it is not clear what errors to expect during the
            # entire procedure we catch them all and assume the
            # following:
            # - WantReadError and WantWriteError means "retry"
            # - ZeroReturnError, SysCallError[EOF], Error[] are all
            #   aliases for disconnection
            try:
                laststate = self.socket.get_shutdown()
                self.socket.set_shutdown(laststate | SSL.RECEIVED_SHUTDOWN)
                done = self.socket.shutdown()
                if not laststate & SSL.RECEIVED_SHUTDOWN:
                    self.socket.set_shutdown(SSL.SENT_SHUTDOWN)
            except SSL.WantReadError:
                self._ssl_want_read = True
                debug("call: _do_ssl_shutdown, err: ssl-want-read", inst=self)
            except SSL.WantWriteError:
                self._ssl_want_write = True
                debug("call: _do_ssl_shutdown, err: ssl-want-write", inst=self)
            except SSL.ZeroReturnError:
                debug(
                    "call: _do_ssl_shutdown() -> shutdown(), err: zero-return",
                    inst=self)
                super().close()
            except SSL.SysCallError as err:
                debug("call: _do_ssl_shutdown() -> shutdown(), err: %r" % err,
                      inst=self)
                errnum, errstr = err.args
                if errnum in _ERRNOS_DISCONNECTED or \
                        errstr == 'Unexpected EOF':
                    super().close()
                else:
                    raise
            except SSL.Error as err:
                debug("call: _do_ssl_shutdown() -> shutdown(), err: %r" % err,
                      inst=self)
                # see:
                # https://github.com/giampaolo/pyftpdlib/issues/171
                # https://bugs.launchpad.net/pyopenssl/+bug/785985
                if err.args and not getattr(err, "errno", None):
                    pass
                else:
                    raise
            except socket.error as err:
                debug("call: _do_ssl_shutdown() -> shutdown(), err: %r" % err,
                      inst=self)
                if err.errno in _ERRNOS_DISCONNECTED:
                    super().close()
                else:
                    raise
            else:
                if done:
                    debug("call: _do_ssl_shutdown(), shutdown completed",
                          inst=self)
                    self._ssl_established = False
                    self._ssl_closing = False
                    self.handle_ssl_shutdown()
                else:
                    debug(
                        "call: _do_ssl_shutdown(), shutdown not completed yet",
                        inst=self)

        def close(self):
            if self._ssl_established and not self._error:
                self._do_ssl_shutdown()
            else:
                self._ssl_accepting = False
                self._ssl_established = False
                self._ssl_closing = False
                super().close()

    class TLS_DTPHandler(SSLConnection, DTPHandler):
        """A DTPHandler subclass supporting TLS/SSL."""

        def __init__(self, sock, cmd_channel):
            super().__init__(sock, cmd_channel)
            if self.cmd_channel._prot:
                self.secure_connection(self.cmd_channel.ssl_context)

        def __repr__(self):
            return DTPHandler.__repr__(self)

        def use_sendfile(self):
            if isinstance(self.socket, SSL.Connection):
                return False
            else:
                return super().use_sendfile()

        def handle_failed_ssl_handshake(self):
            # TLS/SSL handshake failure, probably client's fault which
            # used a SSL version different from server's.
            # RFC-4217, chapter 10.2 expects us to return 522 over the
            # command channel.
            self.cmd_channel.respond("522 SSL handshake failed.")
            self.cmd_channel.log_cmd("PROT", "P", 522, "SSL handshake failed.")
            self.close()

    class TLS_FTPHandler(SSLConnection, FTPHandler):
        """A FTPHandler subclass supporting TLS/SSL.
        Implements AUTH, PBSZ and PROT commands (RFC-2228 and RFC-4217).

        Configurable attributes:

         - (bool) tls_control_required:
            When True requires SSL/TLS to be established on the control
            channel, before logging in.  This means the user will have
            to issue AUTH before USER/PASS (default False).

         - (bool) tls_data_required:
            When True requires SSL/TLS to be established on the data
            channel.  This means the user will have to issue PROT
            before PASV or PORT (default False).

        SSL-specific options:

         - (string) certfile:
            the path to the file which contains a certificate to be
            used to identify the local side of the connection.
            This  must always be specified, unless context is provided
            instead.

         - (string) keyfile:
            the path to the file containing the private RSA key;
            can be omitted if certfile already contains the private
            key (defaults: None).

         - (int) ssl_protocol:
            the desired SSL protocol version to use. This defaults to
            PROTOCOL_SSLv23 which will negotiate the highest protocol
            that both the server and your installation of OpenSSL
            support.

         - (int) ssl_options:
            specific OpenSSL options. These default to:
            SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3| SSL.OP_NO_COMPRESSION
            which are all considered insecure features.
            Can be set to None in order to improve compatibility with
            older (insecure) FTP clients.

          - (instance) ssl_context:
            a SSL Context object previously configured; if specified
            all other parameters will be ignored.
            (default None).
        """

        # configurable attributes
        tls_control_required = False
        tls_data_required = False
        certfile = None
        keyfile = None
        ssl_protocol = SSL.SSLv23_METHOD
        # - SSLv2 is easily broken and is considered harmful and dangerous
        # - SSLv3 has several problems and is now dangerous
        # - Disable compression to prevent CRIME attacks for OpenSSL 1.0+
        #   (see https://github.com/shazow/urllib3/pull/309)
        ssl_options = SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3
        if hasattr(SSL, "OP_NO_COMPRESSION"):
            ssl_options |= SSL.OP_NO_COMPRESSION
        ssl_context = None

        # overridden attributes
        dtp_handler = TLS_DTPHandler
        proto_cmds = FTPHandler.proto_cmds.copy()
        proto_cmds.update({
            'AUTH': dict(
                perm=None, auth=False, arg=True,
                help='Syntax: AUTH <SP> TLS|SSL (set up secure control '
                     'channel).'),
            'PBSZ': dict(
                perm=None, auth=False, arg=True,
                help='Syntax: PBSZ <SP> 0 (negotiate TLS buffer).'),
            'PROT': dict(
                perm=None, auth=False, arg=True,
                help='Syntax: PROT <SP> [C|P] (set up un/secure data '
                     'channel).'),
        })

        def __init__(self, conn, server, ioloop=None):
            super().__init__(conn, server, ioloop)
            if not self.connected:
                return
            self._extra_feats = ['AUTH TLS', 'AUTH SSL', 'PBSZ', 'PROT']
            self._pbsz = False
            self._prot = False
            self.ssl_context = self.get_ssl_context()

        def __repr__(self):
            return FTPHandler.__repr__(self)

        @classmethod
        def get_ssl_context(cls):
            if cls.ssl_context is None:
                if cls.certfile is None:
                    raise ValueError("at least certfile must be specified")
                cls.ssl_context = SSL.Context(cls.ssl_protocol)
                cls.ssl_context.use_certificate_chain_file(cls.certfile)
                if not cls.keyfile:
                    cls.keyfile = cls.certfile
                cls.ssl_context.use_privatekey_file(cls.keyfile)
                if cls.ssl_options:
                    cls.ssl_context.set_options(cls.ssl_options)
            return cls.ssl_context

        # --- overridden methods

        def flush_account(self):
            FTPHandler.flush_account(self)
            self._pbsz = False
            self._prot = False

        def process_command(self, cmd, *args, **kwargs):
            if cmd in ('USER', 'PASS'):
                if self.tls_control_required and not self._ssl_established:
                    msg = "SSL/TLS required on the control channel."
                    self.respond("550 " + msg)
                    self.log_cmd(cmd, args[0], 550, msg)
                    return
            elif cmd in ('PASV', 'EPSV', 'PORT', 'EPRT'):
                if self.tls_data_required and not self._prot:
                    msg = "SSL/TLS required on the data channel."
                    self.respond("550 " + msg)
                    self.log_cmd(cmd, args[0], 550, msg)
                    return
            FTPHandler.process_command(self, cmd, *args, **kwargs)

        def close(self):
            SSLConnection.close(self)
            FTPHandler.close(self)
        
        # --- new methods

        def handle_failed_ssl_handshake(self):
            # TLS/SSL handshake failure, probably client's fault which
            # used a SSL version different from server's.
            # We can't rely on the control connection anymore so we just
            # disconnect the client without sending any response.
            self.log("SSL handshake failed.")
            self.close()

        def ftp_AUTH(self, line):
            """Set up secure control channel."""
            arg = line.upper()
            if isinstance(self.socket, SSL.Connection):
                self.respond("503 Already using TLS.")
            elif arg in ('TLS', 'TLS-C', 'SSL', 'TLS-P'):
                # From RFC-4217: "As the SSL/TLS protocols self-negotiate
                # their levels, there is no need to distinguish between SSL
                # and TLS in the application layer".
                self.respond('234 AUTH %s successful.' % arg)
                self.secure_connection(self.ssl_context)
            else:
                self.respond(
                    "502 Unrecognized encryption type (use TLS or SSL).")

        def ftp_PBSZ(self, line):
            """Negotiate size of buffer for secure data transfer.
            For TLS/SSL the only valid value for the parameter is '0'.
            Any other value is accepted but ignored.
            """
            if not isinstance(self.socket, SSL.Connection):
                self.respond(
                    "503 PBSZ not allowed on insecure control connection.")
            else:
                self.respond('200 PBSZ=0 successful.')
                self._pbsz = True

        def ftp_PROT(self, line):
            """Setup un/secure data channel."""
            arg = line.upper()
            if not isinstance(self.socket, SSL.Connection):
                self.respond(
                    "503 PROT not allowed on insecure control connection.")
            elif not self._pbsz:
                self.respond(
                    "503 You must issue the PBSZ command prior to PROT.")
            elif arg == 'C':
                self.respond('200 Protection set to Clear')
                self._prot = False
            elif arg == 'P':
                self.respond('200 Protection set to Private')
                self._prot = True
            elif arg in ('S', 'E'):
                self.respond('521 PROT %s unsupported (use C or P).' % arg)
            else:
                self.respond("502 Unrecognized PROT type (use C or P).")
