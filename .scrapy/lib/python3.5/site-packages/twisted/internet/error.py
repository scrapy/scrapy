# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Exceptions and errors for use in twisted.internet modules.
"""

from __future__ import division, absolute_import

import socket

from twisted.python import deprecate
from twisted.python.versions import Version



class BindError(Exception):
    """An error occurred binding to an interface"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class CannotListenError(BindError):
    """
    This gets raised by a call to startListening, when the object cannotstart
    listening.

    @ivar interface: the interface I tried to listen on
    @ivar port: the port I tried to listen on
    @ivar socketError: the exception I got when I tried to listen
    @type socketError: L{socket.error}
    """
    def __init__(self, interface, port, socketError):
        BindError.__init__(self, interface, port, socketError)
        self.interface = interface
        self.port = port
        self.socketError = socketError

    def __str__(self):
        iface = self.interface or 'any'
        return "Couldn't listen on %s:%s: %s." % (iface, self.port,
                                                 self.socketError)



class MulticastJoinError(Exception):
    """
    An attempt to join a multicast group failed.
    """



class MessageLengthError(Exception):
    """Message is too long to send"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class DNSLookupError(IOError):
    """DNS lookup failed"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class ConnectInProgressError(Exception):
    """A connect operation was started and isn't done yet."""


# connection errors

class ConnectError(Exception):
    """An error occurred while connecting"""

    def __init__(self, osError=None, string=""):
        self.osError = osError
        Exception.__init__(self, string)

    def __str__(self):
        s = self.__doc__ or self.__class__.__name__
        if self.osError:
            s = '%s: %s' % (s, self.osError)
        if self.args[0]:
            s = '%s: %s' % (s, self.args[0])
        s = '%s.' % s
        return s



class ConnectBindError(ConnectError):
    """Couldn't bind"""



class UnknownHostError(ConnectError):
    """Hostname couldn't be looked up"""



class NoRouteError(ConnectError):
    """No route to host"""



class ConnectionRefusedError(ConnectError):
    """Connection was refused by other side"""



class TCPTimedOutError(ConnectError):
    """TCP connection timed out"""



class BadFileError(ConnectError):
    """File used for UNIX socket is no good"""



class ServiceNameUnknownError(ConnectError):
    """Service name given as port is unknown"""



class UserError(ConnectError):
    """User aborted connection"""



class TimeoutError(UserError):
    """User timeout caused connection failure"""



class SSLError(ConnectError):
    """An SSL error occurred"""



class VerifyError(Exception):
    """Could not verify something that was supposed to be signed.
    """



class PeerVerifyError(VerifyError):
    """The peer rejected our verify error.
    """



class CertificateError(Exception):
    """
    We did not find a certificate where we expected to find one.
    """



try:
    import errno
    errnoMapping = {
        errno.ENETUNREACH: NoRouteError,
        errno.ECONNREFUSED: ConnectionRefusedError,
        errno.ETIMEDOUT: TCPTimedOutError,
    }
    if hasattr(errno, "WSAECONNREFUSED"):
        errnoMapping[errno.WSAECONNREFUSED] = ConnectionRefusedError
        errnoMapping[errno.WSAENETUNREACH] = NoRouteError
except ImportError:
    errnoMapping = {}



def getConnectError(e):
    """Given a socket exception, return connection error."""
    if isinstance(e, Exception):
        args = e.args
    else:
        args = e
    try:
        number, string = args
    except ValueError:
        return ConnectError(string=e)

    if hasattr(socket, 'gaierror') and isinstance(e, socket.gaierror):
        # Only works in 2.2 in newer. Really that means always; #5978 covers
        # this and other weirdnesses in this function.
        klass = UnknownHostError
    else:
        klass = errnoMapping.get(number, ConnectError)
    return klass(number, string)



class ConnectionClosed(Exception):
    """
    Connection was closed, whether cleanly or non-cleanly.
    """



class ConnectionLost(ConnectionClosed):
    """Connection to the other side was lost in a non-clean fashion"""

    def __str__(self):
        s = self.__doc__.strip().splitlines()[0]
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class ConnectionAborted(ConnectionLost):
    """
    Connection was aborted locally, using
    L{twisted.internet.interfaces.ITCPTransport.abortConnection}.

    @since: 11.1
    """



class ConnectionDone(ConnectionClosed):
    """Connection was closed cleanly"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class FileDescriptorOverrun(ConnectionLost):
    """
    A mis-use of L{IUNIXTransport.sendFileDescriptor} caused the connection to
    be closed.

    Each file descriptor sent using C{sendFileDescriptor} must be associated
    with at least one byte sent using L{ITransport.write}.  If at any point
    fewer bytes have been written than file descriptors have been sent, the
    connection is closed with this exception.
    """



class ConnectionFdescWentAway(ConnectionLost):
    """Uh""" #TODO



class AlreadyCalled(ValueError):
    """Tried to cancel an already-called event"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class AlreadyCancelled(ValueError):
    """Tried to cancel an already-cancelled event"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class PotentialZombieWarning(Warning):
    """
    Emitted when L{IReactorProcess.spawnProcess} is called in a way which may
    result in termination of the created child process not being reported.

    Deprecated in Twisted 10.0.
    """
    MESSAGE = (
        "spawnProcess called, but the SIGCHLD handler is not "
        "installed. This probably means you have not yet "
        "called reactor.run, or called "
        "reactor.run(installSignalHandler=0). You will probably "
        "never see this process finish, and it may become a "
        "zombie process.")

deprecate.deprecatedModuleAttribute(
    Version("Twisted", 10, 0, 0),
    "There is no longer any potential for zombie process.",
    __name__,
    "PotentialZombieWarning")



class ProcessDone(ConnectionDone):
    """A process has ended without apparent errors"""

    def __init__(self, status):
        Exception.__init__(self, "process finished with exit code 0")
        self.exitCode = 0
        self.signal = None
        self.status = status



class ProcessTerminated(ConnectionLost):
    """
    A process has ended with a probable error condition

    @ivar exitCode: See L{__init__}
    @ivar signal: See L{__init__}
    @ivar status: See L{__init__}
    """
    def __init__(self, exitCode=None, signal=None, status=None):
        """
        @param exitCode: The exit status of the process.  This is roughly like
            the value you might pass to L{os.exit}.  This is L{None} if the
            process exited due to a signal.
        @type exitCode: L{int} or L{None}

        @param signal: The exit signal of the process.  This is L{None} if the
            process did not exit due to a signal.
        @type signal: L{int} or L{None}

        @param status: The exit code of the process.  This is a platform
            specific combination of the exit code and the exit signal.  See
            L{os.WIFEXITED} and related functions.
        @type status: L{int}
        """
        self.exitCode = exitCode
        self.signal = signal
        self.status = status
        s = "process ended"
        if exitCode is not None: s = s + " with exit code %s" % exitCode
        if signal is not None: s = s + " by signal %s" % signal
        Exception.__init__(self, s)



class ProcessExitedAlready(Exception):
    """
    The process has already exited and the operation requested can no longer
    be performed.
    """



class NotConnectingError(RuntimeError):
    """The Connector was not connecting when it was asked to stop connecting"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class NotListeningError(RuntimeError):
    """The Port was not listening when it was asked to stop listening"""

    def __str__(self):
        s = self.__doc__
        if self.args:
            s = '%s: %s' % (s, ' '.join(self.args))
        s = '%s.' % s
        return s



class ReactorNotRunning(RuntimeError):
    """
    Error raised when trying to stop a reactor which is not running.
    """


class ReactorNotRestartable(RuntimeError):
    """
    Error raised when trying to run a reactor which was stopped.
    """



class ReactorAlreadyRunning(RuntimeError):
    """
    Error raised when trying to start the reactor multiple times.
    """


class ReactorAlreadyInstalledError(AssertionError):
    """
    Could not install reactor because one is already installed.
    """



class ConnectingCancelledError(Exception):
    """
    An C{Exception} that will be raised when an L{IStreamClientEndpoint} is
    cancelled before it connects.

    @ivar address: The L{IAddress} that is the destination of the
        cancelled L{IStreamClientEndpoint}.
    """

    def __init__(self, address):
        """
        @param address: The L{IAddress} that is the destination of the
            L{IStreamClientEndpoint} that was cancelled.
        """
        Exception.__init__(self, address)
        self.address = address



class NoProtocol(Exception):
    """
    An C{Exception} that will be raised when the factory given to a
    L{IStreamClientEndpoint} returns L{None} from C{buildProtocol}.
    """



class UnsupportedAddressFamily(Exception):
    """
    An attempt was made to use a socket with an address family (eg I{AF_INET},
    I{AF_INET6}, etc) which is not supported by the reactor.
    """



class UnsupportedSocketType(Exception):
    """
    An attempt was made to use a socket of a type (eg I{SOCK_STREAM},
    I{SOCK_DGRAM}, etc) which is not supported by the reactor.
    """


class AlreadyListened(Exception):
    """
    An attempt was made to listen on a file descriptor which can only be
    listened on once.
    """



class InvalidAddressError(ValueError):
    """
    An invalid address was specified (i.e. neither IPv4 or IPv6, or expected
    one and got the other).

    @ivar address: See L{__init__}
    @ivar message: See L{__init__}
    """

    def __init__(self, address, message):
        """
        @param address: The address that was provided.
        @type address: L{bytes}
        @param message: A native string of additional information provided by
            the calling context.
        @type address: L{str}
        """
        self.address = address
        self.message = message



__all__ = [
    'BindError', 'CannotListenError', 'MulticastJoinError',
    'MessageLengthError', 'DNSLookupError', 'ConnectInProgressError',
    'ConnectError', 'ConnectBindError', 'UnknownHostError', 'NoRouteError',
    'ConnectionRefusedError', 'TCPTimedOutError', 'BadFileError',
    'ServiceNameUnknownError', 'UserError', 'TimeoutError', 'SSLError',
    'VerifyError', 'PeerVerifyError', 'CertificateError',
    'getConnectError', 'ConnectionClosed', 'ConnectionLost',
    'ConnectionDone', 'ConnectionFdescWentAway', 'AlreadyCalled',
    'AlreadyCancelled', 'PotentialZombieWarning', 'ProcessDone',
    'ProcessTerminated', 'ProcessExitedAlready', 'NotConnectingError',
    'NotListeningError', 'ReactorNotRunning', 'ReactorAlreadyRunning',
    'ReactorAlreadyInstalledError', 'ConnectingCancelledError',
    'UnsupportedAddressFamily', 'UnsupportedSocketType', 'InvalidAddressError']
