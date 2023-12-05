# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Exceptions and errors for use in twisted.internet modules.
"""


import socket

from incremental import Version

from twisted.python import deprecate


class BindError(Exception):
    __doc__ = MESSAGE = "An error occurred binding to an interface"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
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

    def __str__(self) -> str:
        iface = self.interface or "any"
        return "Couldn't listen on {}:{}: {}.".format(
            iface, self.port, self.socketError
        )


class MulticastJoinError(Exception):
    """
    An attempt to join a multicast group failed.
    """


class MessageLengthError(Exception):
    __doc__ = MESSAGE = "Message is too long to send"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
        return s


class DNSLookupError(IOError):
    __doc__ = MESSAGE = "DNS lookup failed"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
        return s


class ConnectInProgressError(Exception):
    """A connect operation was started and isn't done yet."""


# connection errors


class ConnectError(Exception):
    __doc__ = MESSAGE = "An error occurred while connecting"

    def __init__(self, osError=None, string=""):
        self.osError = osError
        Exception.__init__(self, string)

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.osError:
            s = f"{s}: {self.osError}"
        if self.args[0]:
            s = f"{s}: {self.args[0]}"
        s = "%s." % s
        return s


class ConnectBindError(ConnectError):
    __doc__ = MESSAGE = "Couldn't bind"


class UnknownHostError(ConnectError):
    __doc__ = MESSAGE = "Hostname couldn't be looked up"


class NoRouteError(ConnectError):
    __doc__ = MESSAGE = "No route to host"


class ConnectionRefusedError(ConnectError):
    __doc__ = MESSAGE = "Connection was refused by other side"


class TCPTimedOutError(ConnectError):
    __doc__ = MESSAGE = "TCP connection timed out"


class BadFileError(ConnectError):
    __doc__ = MESSAGE = "File used for UNIX socket is no good"


class ServiceNameUnknownError(ConnectError):
    __doc__ = MESSAGE = "Service name given as port is unknown"


class UserError(ConnectError):
    __doc__ = MESSAGE = "User aborted connection"


class TimeoutError(UserError):
    __doc__ = MESSAGE = "User timeout caused connection failure"


class SSLError(ConnectError):
    __doc__ = MESSAGE = "An SSL error occurred"


class VerifyError(Exception):
    __doc__ = MESSAGE = "Could not verify something that was supposed to be signed."


class PeerVerifyError(VerifyError):
    __doc__ = MESSAGE = "The peer rejected our verify error."


class CertificateError(Exception):
    __doc__ = MESSAGE = "We did not find a certificate where we expected to find one."


try:
    import errno

    errnoMapping = {
        errno.ENETUNREACH: NoRouteError,
        errno.ECONNREFUSED: ConnectionRefusedError,
        errno.ETIMEDOUT: TCPTimedOutError,
    }
    if hasattr(errno, "WSAECONNREFUSED"):
        errnoMapping[errno.WSAECONNREFUSED] = ConnectionRefusedError  # type: ignore[attr-defined]
        errnoMapping[errno.WSAENETUNREACH] = NoRouteError  # type: ignore[attr-defined]
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

    if hasattr(socket, "gaierror") and isinstance(e, socket.gaierror):
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
    __doc__ = MESSAGE = """
    Connection to the other side was lost in a non-clean fashion
    """

    def __str__(self) -> str:
        s = self.MESSAGE.strip().splitlines()[:1]
        if self.args:
            s.append(": ")
            s.append(" ".join(self.args))
        s.append(".")
        return "".join(s)


class ConnectionAborted(ConnectionLost):
    """
    Connection was aborted locally, using
    L{twisted.internet.interfaces.ITCPTransport.abortConnection}.

    @since: 11.1
    """

    MESSAGE = "Connection was aborted locally using " "ITCPTransport.abortConnection"


class ConnectionDone(ConnectionClosed):
    __doc__ = MESSAGE = "Connection was closed cleanly"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
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

    MESSAGE = (
        "A mis-use of IUNIXTransport.sendFileDescriptor caused "
        "the connection to be closed."
    )


class ConnectionFdescWentAway(ConnectionLost):
    __doc__ = MESSAGE = "Uh"  # TODO


class AlreadyCalled(ValueError):
    __doc__ = MESSAGE = "Tried to cancel an already-called event"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
        return s


class AlreadyCancelled(ValueError):
    __doc__ = MESSAGE = "Tried to cancel an already-cancelled event"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
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
        "zombie process."
    )


deprecate.deprecatedModuleAttribute(
    Version("Twisted", 10, 0, 0),
    "There is no longer any potential for zombie process.",
    __name__,
    "PotentialZombieWarning",
)


class ProcessDone(ConnectionDone):
    __doc__ = MESSAGE = "A process has ended without apparent errors"

    def __init__(self, status):
        Exception.__init__(self, "process finished with exit code 0")
        self.exitCode = 0
        self.signal = None
        self.status = status


class ProcessTerminated(ConnectionLost):
    __doc__ = MESSAGE = """
    A process has ended with a probable error condition

    @ivar exitCode: See L{__init__}
    @ivar signal: See L{__init__}
    @ivar status: See L{__init__}
    """

    def __init__(self, exitCode=None, signal=None, status=None):
        """
        @param exitCode: The exit status of the process.  This is roughly like
            the value you might pass to L{os._exit}.  This is L{None} if the
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
        if exitCode is not None:
            s = s + " with exit code %s" % exitCode
        if signal is not None:
            s = s + " by signal %s" % signal
        Exception.__init__(self, s)


class ProcessExitedAlready(Exception):
    """
    The process has already exited and the operation requested can no longer
    be performed.
    """


class NotConnectingError(RuntimeError):
    __doc__ = (
        MESSAGE
    ) = "The Connector was not connecting when it was asked to stop connecting"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
        return s


class NotListeningError(RuntimeError):
    __doc__ = MESSAGE = "The Port was not listening when it was asked to stop listening"

    def __str__(self) -> str:
        s = self.MESSAGE
        if self.args:
            s = "{}: {}".format(s, " ".join(self.args))
        s = "%s." % s
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
    "BindError",
    "CannotListenError",
    "MulticastJoinError",
    "MessageLengthError",
    "DNSLookupError",
    "ConnectInProgressError",
    "ConnectError",
    "ConnectBindError",
    "UnknownHostError",
    "NoRouteError",
    "ConnectionRefusedError",
    "TCPTimedOutError",
    "BadFileError",
    "ServiceNameUnknownError",
    "UserError",
    "TimeoutError",
    "SSLError",
    "VerifyError",
    "PeerVerifyError",
    "CertificateError",
    "getConnectError",
    "ConnectionClosed",
    "ConnectionLost",
    "ConnectionDone",
    "ConnectionFdescWentAway",
    "AlreadyCalled",
    "AlreadyCancelled",
    "PotentialZombieWarning",
    "ProcessDone",
    "ProcessTerminated",
    "ProcessExitedAlready",
    "NotConnectingError",
    "NotListeningError",
    "ReactorNotRunning",
    "ReactorAlreadyRunning",
    "ReactorAlreadyInstalledError",
    "ConnectingCancelledError",
    "UnsupportedAddressFamily",
    "UnsupportedSocketType",
    "InvalidAddressError",
]
