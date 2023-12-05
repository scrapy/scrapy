# -*- test-case-name: twisted.test.test_amp -*-
# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module implements AMP, the Asynchronous Messaging Protocol.

AMP is a protocol for sending multiple asynchronous request/response pairs over
the same connection.  Requests and responses are both collections of key/value
pairs.

AMP is a very simple protocol which is not an application.  This module is a
"protocol construction kit" of sorts; it attempts to be the simplest wire-level
implementation of Deferreds.  AMP provides the following base-level features:

    - Asynchronous request/response handling (hence the name)

    - Requests and responses are both key/value pairs

    - Binary transfer of all data: all data is length-prefixed.  Your
      application will never need to worry about quoting.

    - Command dispatching (like HTTP Verbs): the protocol is extensible, and
      multiple AMP sub-protocols can be grouped together easily.

The protocol implementation also provides a few additional features which are
not part of the core wire protocol, but are nevertheless very useful:

    - Tight TLS integration, with an included StartTLS command.

    - Handshaking to other protocols: because AMP has well-defined message
      boundaries and maintains all incoming and outgoing requests for you, you
      can start a connection over AMP and then switch to another protocol.
      This makes it ideal for firewall-traversal applications where you may
      have only one forwarded port but multiple applications that want to use
      it.

Using AMP with Twisted is simple.  Each message is a command, with a response.
You begin by defining a command type.  Commands specify their input and output
in terms of the types that they expect to see in the request and response
key-value pairs.  Here's an example of a command that adds two integers, 'a'
and 'b'::

    class Sum(amp.Command):
        arguments = [('a', amp.Integer()),
                     ('b', amp.Integer())]
        response = [('total', amp.Integer())]

Once you have specified a command, you need to make it part of a protocol, and
define a responder for it.  Here's a 'JustSum' protocol that includes a
responder for our 'Sum' command::

    class JustSum(amp.AMP):
        def sum(self, a, b):
            total = a + b
            print 'Did a sum: %d + %d = %d' % (a, b, total)
            return {'total': total}
        Sum.responder(sum)

Later, when you want to actually do a sum, the following expression will return
a L{Deferred} which will fire with the result::

    ClientCreator(reactor, amp.AMP).connectTCP(...).addCallback(
        lambda p: p.callRemote(Sum, a=13, b=81)).addCallback(
            lambda result: result['total'])

Command responders may also return Deferreds, causing the response to be
sent only once the Deferred fires::

    class DelayedSum(amp.AMP):
        def slowSum(self, a, b):
            total = a + b
            result = defer.Deferred()
            reactor.callLater(3, result.callback, {'total': total})
            return result
        Sum.responder(slowSum)

This is transparent to the caller.

You can also define the propagation of specific errors in AMP.  For example,
for the slightly more complicated case of division, we might have to deal with
division by zero::

    class Divide(amp.Command):
        arguments = [('numerator', amp.Integer()),
                     ('denominator', amp.Integer())]
        response = [('result', amp.Float())]
        errors = {ZeroDivisionError: 'ZERO_DIVISION'}

The 'errors' mapping here tells AMP that if a responder to Divide emits a
L{ZeroDivisionError}, then the other side should be informed that an error of
the type 'ZERO_DIVISION' has occurred.  Writing a responder which takes
advantage of this is very simple - just raise your exception normally::

    class JustDivide(amp.AMP):
        def divide(self, numerator, denominator):
            result = numerator / denominator
            print 'Divided: %d / %d = %d' % (numerator, denominator, total)
            return {'result': result}
        Divide.responder(divide)

On the client side, the errors mapping will be used to determine what the
'ZERO_DIVISION' error means, and translated into an asynchronous exception,
which can be handled normally as any L{Deferred} would be::

    def trapZero(result):
        result.trap(ZeroDivisionError)
        print "Divided by zero: returning INF"
        return 1e1000
    ClientCreator(reactor, amp.AMP).connectTCP(...).addCallback(
        lambda p: p.callRemote(Divide, numerator=1234,
                               denominator=0)
        ).addErrback(trapZero)

For a complete, runnable example of both of these commands, see the files in
the Twisted repository::

    doc/core/examples/ampserver.py
    doc/core/examples/ampclient.py

On the wire, AMP is a protocol which uses 2-byte lengths to prefix keys and
values, and empty keys to separate messages::

    <2-byte length><key><2-byte length><value>
    <2-byte length><key><2-byte length><value>
    ...
    <2-byte length><key><2-byte length><value>
    <NUL><NUL>                  # Empty Key == End of Message

And so on.  Because it's tedious to refer to lengths and NULs constantly, the
documentation will refer to packets as if they were newline delimited, like
so::

    C: _command: sum
    C: _ask: ef639e5c892ccb54
    C: a: 13
    C: b: 81

    S: _answer: ef639e5c892ccb54
    S: total: 94

Notes:

In general, the order of keys is arbitrary.  Specific uses of AMP may impose an
ordering requirement, but unless this is specified explicitly, any ordering may
be generated and any ordering must be accepted.  This applies to the
command-related keys I{_command} and I{_ask} as well as any other keys.

Values are limited to the maximum encodable size in a 16-bit length, 65535
bytes.

Keys are limited to the maximum encodable size in a 8-bit length, 255 bytes.
Note that we still use 2-byte lengths to encode keys.  This small redundancy
has several features:

    - If an implementation becomes confused and starts emitting corrupt data,
      or gets keys confused with values, many common errors will be signalled
      immediately instead of delivering obviously corrupt packets.

    - A single NUL will separate every key, and a double NUL separates
      messages.  This provides some redundancy when debugging traffic dumps.

    - NULs will be present at regular intervals along the protocol, providing
      some padding for otherwise braindead C implementations of the protocol,
      so that <stdio.h> string functions will see the NUL and stop.

    - This makes it possible to run an AMP server on a port also used by a
      plain-text protocol, and easily distinguish between non-AMP clients (like
      web browsers) which issue non-NUL as the first byte, and AMP clients,
      which always issue NUL as the first byte.

@var MAX_VALUE_LENGTH: The maximum length of a message.
@type MAX_VALUE_LENGTH: L{int}

@var ASK: Marker for an Ask packet.
@type ASK: L{bytes}

@var ANSWER: Marker for an Answer packet.
@type ANSWER: L{bytes}

@var COMMAND: Marker for a Command packet.
@type COMMAND: L{bytes}

@var ERROR: Marker for an AMP box of error type.
@type ERROR: L{bytes}

@var ERROR_CODE: Marker for an AMP box containing the code of an error.
@type ERROR_CODE: L{bytes}

@var ERROR_DESCRIPTION: Marker for an AMP box containing the description of the
    error.
@type ERROR_DESCRIPTION: L{bytes}
"""


import datetime
import decimal
import warnings
from functools import partial
from io import BytesIO
from itertools import count
from struct import pack
from types import MethodType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from zope.interface import Interface, implementer

from twisted.internet.defer import Deferred, fail, maybeDeferred
from twisted.internet.error import ConnectionClosed, ConnectionLost, PeerVerifyError
from twisted.internet.interfaces import IFileDescriptorReceiver
from twisted.internet.main import CONNECTION_LOST
from twisted.internet.protocol import Protocol
from twisted.protocols.basic import Int16StringReceiver, StatefulStringProtocol
from twisted.python import filepath, log
from twisted.python._tzhelper import (
    UTC as utc,
    FixedOffsetTimeZone as _FixedOffsetTZInfo,
)
from twisted.python.compat import nativeString
from twisted.python.failure import Failure
from twisted.python.reflect import accumulateClassDict

try:
    from twisted.internet import ssl as _ssl

    if _ssl.supported:
        from twisted.internet.ssl import DN, Certificate, CertificateOptions, KeyPair
    else:
        ssl = None
except ImportError:
    ssl = None
else:
    ssl = _ssl


__all__ = [
    "AMP",
    "ANSWER",
    "ASK",
    "AmpBox",
    "AmpError",
    "AmpList",
    "Argument",
    "BadLocalReturn",
    "BinaryBoxProtocol",
    "Boolean",
    "Box",
    "BoxDispatcher",
    "COMMAND",
    "Command",
    "CommandLocator",
    "Decimal",
    "Descriptor",
    "ERROR",
    "ERROR_CODE",
    "ERROR_DESCRIPTION",
    "Float",
    "IArgumentType",
    "IBoxReceiver",
    "IBoxSender",
    "IResponderLocator",
    "IncompatibleVersions",
    "Integer",
    "InvalidSignature",
    "ListOf",
    "MAX_KEY_LENGTH",
    "MAX_VALUE_LENGTH",
    "MalformedAmpBox",
    "NoEmptyBoxes",
    "OnlyOneTLS",
    "PROTOCOL_ERRORS",
    "PYTHON_KEYWORDS",
    "Path",
    "ProtocolSwitchCommand",
    "ProtocolSwitched",
    "QuitBox",
    "RemoteAmpError",
    "SimpleStringLocator",
    "StartTLS",
    "String",
    "TooLong",
    "UNHANDLED_ERROR_CODE",
    "UNKNOWN_ERROR_CODE",
    "UnhandledCommand",
    "utc",
    "Unicode",
    "UnknownRemoteError",
    "parse",
    "parseString",
]


ASK = b"_ask"
ANSWER = b"_answer"
COMMAND = b"_command"
ERROR = b"_error"
ERROR_CODE = b"_error_code"
ERROR_DESCRIPTION = b"_error_description"
UNKNOWN_ERROR_CODE = b"UNKNOWN"
UNHANDLED_ERROR_CODE = b"UNHANDLED"

MAX_KEY_LENGTH = 0xFF
MAX_VALUE_LENGTH = 0xFFFF


class IArgumentType(Interface):
    """
    An L{IArgumentType} can serialize a Python object into an AMP box and
    deserialize information from an AMP box back into a Python object.

    @since: 9.0
    """

    def fromBox(name, strings, objects, proto):
        """
        Given an argument name and an AMP box containing serialized values,
        extract one or more Python objects and add them to the C{objects}
        dictionary.

        @param name: The name associated with this argument. Most commonly
            this is the key which can be used to find a serialized value in
            C{strings}.
        @type name: C{bytes}

        @param strings: The AMP box from which to extract one or more
            values.
        @type strings: C{dict}

        @param objects: The output dictionary to populate with the value for
            this argument. The key used will be derived from C{name}. It may
            differ; in Python 3, for example, the key will be a Unicode/native
            string. See L{_wireNameToPythonIdentifier}.
        @type objects: C{dict}

        @param proto: The protocol instance which received the AMP box being
            interpreted.  Most likely this is an instance of L{AMP}, but
            this is not guaranteed.

        @return: L{None}
        """

    def toBox(name, strings, objects, proto):
        """
        Given an argument name and a dictionary containing structured Python
        objects, serialize values into one or more strings and add them to
        the C{strings} dictionary.

        @param name: The name associated with this argument. Most commonly
            this is the key in C{strings} to associate with a C{bytes} giving
            the serialized form of that object.
        @type name: C{bytes}

        @param strings: The AMP box into which to insert one or more strings.
        @type strings: C{dict}

        @param objects: The input dictionary from which to extract Python
            objects to serialize. The key used will be derived from C{name}.
            It may differ; in Python 3, for example, the key will be a
            Unicode/native string. See L{_wireNameToPythonIdentifier}.
        @type objects: C{dict}

        @param proto: The protocol instance which will send the AMP box once
            it is fully populated.  Most likely this is an instance of
            L{AMP}, but this is not guaranteed.

        @return: L{None}
        """


class IBoxSender(Interface):
    """
    A transport which can send L{AmpBox} objects.
    """

    def sendBox(box):
        """
        Send an L{AmpBox}.

        @raise ProtocolSwitched: if the underlying protocol has been
        switched.

        @raise ConnectionLost: if the underlying connection has already been
        lost.
        """

    def unhandledError(failure):
        """
        An unhandled error occurred in response to a box.  Log it
        appropriately.

        @param failure: a L{Failure} describing the error that occurred.
        """


class IBoxReceiver(Interface):
    """
    An application object which can receive L{AmpBox} objects and dispatch them
    appropriately.
    """

    def startReceivingBoxes(boxSender):
        """
        The L{IBoxReceiver.ampBoxReceived} method will start being called;
        boxes may be responded to by responding to the given L{IBoxSender}.

        @param boxSender: an L{IBoxSender} provider.
        """

    def ampBoxReceived(box):
        """
        A box was received from the transport; dispatch it appropriately.
        """

    def stopReceivingBoxes(reason):
        """
        No further boxes will be received on this connection.

        @type reason: L{Failure}
        """


class IResponderLocator(Interface):
    """
    An application object which can look up appropriate responder methods for
    AMP commands.
    """

    def locateResponder(name):
        """
        Locate a responder method appropriate for the named command.

        @param name: the wire-level name (commandName) of the AMP command to be
        responded to.
        @type name: C{bytes}

        @return: a 1-argument callable that takes an L{AmpBox} with argument
        values for the given command, and returns an L{AmpBox} containing
        argument values for the named command, or a L{Deferred} that fires the
        same.
        """


class AmpError(Exception):
    """
    Base class of all Amp-related exceptions.
    """


class ProtocolSwitched(Exception):
    """
    Connections which have been switched to other protocols can no longer
    accept traffic at the AMP level.  This is raised when you try to send it.
    """


class OnlyOneTLS(AmpError):
    """
    This is an implementation limitation; TLS may only be started once per
    connection.
    """


class NoEmptyBoxes(AmpError):
    """
    You can't have empty boxes on the connection.  This is raised when you
    receive or attempt to send one.
    """


class InvalidSignature(AmpError):
    """
    You didn't pass all the required arguments.
    """


class TooLong(AmpError):
    """
    One of the protocol's length limitations was violated.

    @ivar isKey: true if the string being encoded in a key position, false if
    it was in a value position.

    @ivar isLocal: Was the string encoded locally, or received too long from
    the network?  (It's only physically possible to encode "too long" values on
    the network for keys.)

    @ivar value: The string that was too long.

    @ivar keyName: If the string being encoded was in a value position, what
    key was it being encoded for?
    """

    def __init__(self, isKey, isLocal, value, keyName=None):
        AmpError.__init__(self)
        self.isKey = isKey
        self.isLocal = isLocal
        self.value = value
        self.keyName = keyName

    def __repr__(self) -> str:
        hdr = self.isKey and "key" or "value"
        if not self.isKey:
            hdr += " " + repr(self.keyName)
        lcl = self.isLocal and "local" or "remote"
        return "%s %s too long: %d" % (lcl, hdr, len(self.value))


class BadLocalReturn(AmpError):
    """
    A bad value was returned from a local command; we were unable to coerce it.
    """

    def __init__(self, message: str, enclosed: Failure) -> None:
        AmpError.__init__(self)
        self.message = message
        self.enclosed = enclosed

    def __repr__(self) -> str:
        return self.message + " " + self.enclosed.getBriefTraceback()

    __str__ = __repr__


class RemoteAmpError(AmpError):
    """
    This error indicates that something went wrong on the remote end of the
    connection, and the error was serialized and transmitted to you.
    """

    def __init__(self, errorCode, description, fatal=False, local=None):
        """Create a remote error with an error code and description.

        @param errorCode: the AMP error code of this error.
        @type errorCode: C{bytes}

        @param description: some text to show to the user.
        @type description: C{str}

        @param fatal: a boolean, true if this error should terminate the
        connection.

        @param local: a local Failure, if one exists.
        """
        if local:
            localwhat = " (local)"
            othertb = local.getBriefTraceback()
        else:
            localwhat = ""
            othertb = ""

        # Backslash-escape errorCode. Python 3.5 can do this natively
        # ("backslashescape") but Python 2.7 and Python 3.4 can't.
        errorCodeForMessage = "".join(
            f"\\x{c:2x}" if c >= 0x80 else chr(c) for c in errorCode
        )

        if othertb:
            message = "Code<{}>{}: {}\n{}".format(
                errorCodeForMessage,
                localwhat,
                description,
                othertb,
            )
        else:
            message = "Code<{}>{}: {}".format(
                errorCodeForMessage, localwhat, description
            )

        super().__init__(message)
        self.local = local
        self.errorCode = errorCode
        self.description = description
        self.fatal = fatal


class UnknownRemoteError(RemoteAmpError):
    """
    This means that an error whose type we can't identify was raised from the
    other side.
    """

    def __init__(self, description):
        errorCode = UNKNOWN_ERROR_CODE
        RemoteAmpError.__init__(self, errorCode, description)


class MalformedAmpBox(AmpError):
    """
    This error indicates that the wire-level protocol was malformed.
    """


class UnhandledCommand(AmpError):
    """
    A command received via amp could not be dispatched.
    """


class IncompatibleVersions(AmpError):
    """
    It was impossible to negotiate a compatible version of the protocol with
    the other end of the connection.
    """


PROTOCOL_ERRORS = {UNHANDLED_ERROR_CODE: UnhandledCommand}


class AmpBox(dict):
    """
    I am a packet in the AMP protocol, much like a
    regular bytes:bytes dictionary.
    """

    # be like a regular dictionary don't magically
    # acquire a __dict__...
    __slots__: List[str] = []

    def __init__(self, *args, **kw):
        """
        Initialize a new L{AmpBox}.

        In Python 3, keyword arguments MUST be Unicode/native strings whereas
        in Python 2 they could be either byte strings or Unicode strings.

        However, all keys of an L{AmpBox} MUST be byte strings, or possible to
        transparently coerce into byte strings (i.e. Python 2).

        In Python 3, therefore, native string keys are coerced to byte strings
        by encoding as ASCII. This can result in C{UnicodeEncodeError} being
        raised.

        @param args: See C{dict}, but all keys and values should be C{bytes}.
            On Python 3, native strings may be used as keys provided they
            contain only ASCII characters.

        @param kw: See C{dict}, but all keys and values should be C{bytes}.
            On Python 3, native strings may be used as keys provided they
            contain only ASCII characters.

        @raise UnicodeEncodeError: When a native string key cannot be coerced
            to an ASCII byte string (Python 3 only).
        """
        super().__init__(*args, **kw)
        nonByteNames = [n for n in self if not isinstance(n, bytes)]
        for nonByteName in nonByteNames:
            byteName = nonByteName.encode("ascii")
            self[byteName] = self.pop(nonByteName)

    def copy(self):
        """
        Return another AmpBox just like me.
        """
        newBox = self.__class__()
        newBox.update(self)
        return newBox

    def serialize(self):
        """
        Convert me into a wire-encoded string.

        @return: a C{bytes} encoded according to the rules described in the
            module docstring.
        """
        i = sorted(self.items())
        L = []
        w = L.append
        for k, v in i:
            if type(k) == str:
                raise TypeError("Unicode key not allowed: %r" % k)
            if type(v) == str:
                raise TypeError(f"Unicode value for key {k!r} not allowed: {v!r}")
            if len(k) > MAX_KEY_LENGTH:
                raise TooLong(True, True, k, None)
            if len(v) > MAX_VALUE_LENGTH:
                raise TooLong(False, True, v, k)
            for kv in k, v:
                w(pack("!H", len(kv)))
                w(kv)
        w(pack("!H", 0))
        return b"".join(L)

    def _sendTo(self, proto):
        """
        Serialize and send this box to an Amp instance.  By the time it is being
        sent, several keys are required.  I must have exactly ONE of::

            _ask
            _answer
            _error

        If the '_ask' key is set, then the '_command' key must also be
        set.

        @param proto: an AMP instance.
        """
        proto.sendBox(self)

    def __repr__(self) -> str:
        return f"AmpBox({dict.__repr__(self)})"


# amp.Box => AmpBox

Box = AmpBox


class QuitBox(AmpBox):
    """
    I am an AmpBox that, upon being sent, terminates the connection.
    """

    __slots__: List[str] = []

    def __repr__(self) -> str:
        return f"QuitBox(**{super().__repr__()})"

    def _sendTo(self, proto):
        """
        Immediately call loseConnection after sending.
        """
        super()._sendTo(proto)
        proto.transport.loseConnection()


class _SwitchBox(AmpBox):
    """
    Implementation detail of ProtocolSwitchCommand: I am an AmpBox which sets
    up state for the protocol to switch.
    """

    # DON'T set __slots__ here; we do have an attribute.

    def __init__(self, innerProto, **kw):
        """
        Create a _SwitchBox with the protocol to switch to after being sent.

        @param innerProto: the protocol instance to switch to.
        @type innerProto: an IProtocol provider.
        """
        super().__init__(**kw)
        self.innerProto = innerProto

    def __repr__(self) -> str:
        return "_SwitchBox({!r}, **{})".format(
            self.innerProto,
            dict.__repr__(self),
        )

    def _sendTo(self, proto):
        """
        Send me; I am the last box on the connection.  All further traffic will be
        over the new protocol.
        """
        super()._sendTo(proto)
        proto._lockForSwitch()
        proto._switchTo(self.innerProto)


@implementer(IBoxReceiver)
class BoxDispatcher:
    """
    A L{BoxDispatcher} dispatches '_ask', '_answer', and '_error' L{AmpBox}es,
    both incoming and outgoing, to their appropriate destinations.

    Outgoing commands are converted into L{Deferred}s and outgoing boxes, and
    associated tracking state to fire those L{Deferred} when '_answer' boxes
    come back.  Incoming '_answer' and '_error' boxes are converted into
    callbacks and errbacks on those L{Deferred}s, respectively.

    Incoming '_ask' boxes are converted into method calls on a supplied method
    locator.

    @ivar _outstandingRequests: a dictionary mapping request IDs to
    L{Deferred}s which were returned for those requests.

    @ivar locator: an object with a L{CommandLocator.locateResponder} method
        that locates a responder function that takes a Box and returns a result
        (either a Box or a Deferred which fires one).

    @ivar boxSender: an object which can send boxes, via the L{_sendBoxCommand}
    method, such as an L{AMP} instance.
    @type boxSender: L{IBoxSender}
    """

    _failAllReason = None
    _outstandingRequests = None
    _counter = 0
    boxSender = None

    def __init__(self, locator):
        self._outstandingRequests = {}
        self.locator = locator

    def startReceivingBoxes(self, boxSender):
        """
        The given boxSender is going to start calling boxReceived on this
        L{BoxDispatcher}.

        @param boxSender: The L{IBoxSender} to send command responses to.
        """
        self.boxSender = boxSender

    def stopReceivingBoxes(self, reason):
        """
        No further boxes will be received here.  Terminate all currently
        outstanding command deferreds with the given reason.
        """
        self.failAllOutgoing(reason)

    def failAllOutgoing(self, reason):
        """
        Call the errback on all outstanding requests awaiting responses.

        @param reason: the Failure instance to pass to those errbacks.
        """
        self._failAllReason = reason
        OR = self._outstandingRequests.items()
        self._outstandingRequests = None  # we can never send another request
        for key, value in OR:
            value.errback(reason)

    def _nextTag(self):
        """
        Generate protocol-local serial numbers for _ask keys.

        @return: a string that has not yet been used on this connection.
        """
        self._counter += 1
        return b"%x" % (self._counter,)

    def _sendBoxCommand(self, command, box, requiresAnswer=True):
        """
        Send a command across the wire with the given C{amp.Box}.

        Mutate the given box to give it any additional keys (_command, _ask)
        required for the command and request/response machinery, then send it.

        If requiresAnswer is True, returns a C{Deferred} which fires when a
        response is received. The C{Deferred} is fired with an C{amp.Box} on
        success, or with an C{amp.RemoteAmpError} if an error is received.

        If the Deferred fails and the error is not handled by the caller of
        this method, the failure will be logged and the connection dropped.

        @param command: a C{bytes}, the name of the command to issue.

        @param box: an AmpBox with the arguments for the command.

        @param requiresAnswer: a boolean.  Defaults to True.  If True, return a
        Deferred which will fire when the other side responds to this command.
        If False, return None and do not ask the other side for acknowledgement.

        @return: a Deferred which fires the AmpBox that holds the response to
        this command, or None, as specified by requiresAnswer.

        @raise ProtocolSwitched: if the protocol has been switched.
        """
        if self._failAllReason is not None:
            if requiresAnswer:
                return fail(self._failAllReason)
            else:
                return None
        box[COMMAND] = command
        tag = self._nextTag()
        if requiresAnswer:
            box[ASK] = tag
        box._sendTo(self.boxSender)
        if requiresAnswer:
            result = self._outstandingRequests[tag] = Deferred()
        else:
            result = None
        return result

    def callRemoteString(self, command, requiresAnswer=True, **kw):
        """
        This is a low-level API, designed only for optimizing simple messages
        for which the overhead of parsing is too great.

        @param command: a C{bytes} naming the command.

        @param kw: arguments to the amp box.

        @param requiresAnswer: a boolean.  Defaults to True.  If True, return a
        Deferred which will fire when the other side responds to this command.
        If False, return None and do not ask the other side for acknowledgement.

        @return: a Deferred which fires the AmpBox that holds the response to
        this command, or None, as specified by requiresAnswer.
        """
        box = Box(kw)
        return self._sendBoxCommand(command, box, requiresAnswer)

    def callRemote(self, commandType, *a, **kw):
        """
        This is the primary high-level API for sending messages via AMP.  Invoke it
        with a command and appropriate arguments to send a message to this
        connection's peer.

        @param commandType: a subclass of Command.
        @type commandType: L{type}

        @param a: Positional (special) parameters taken by the command.
        Positional parameters will typically not be sent over the wire.  The
        only command included with AMP which uses positional parameters is
        L{ProtocolSwitchCommand}, which takes the protocol that will be
        switched to as its first argument.

        @param kw: Keyword arguments taken by the command.  These are the
        arguments declared in the command's 'arguments' attribute.  They will
        be encoded and sent to the peer as arguments for the L{commandType}.

        @return: If L{commandType} has a C{requiresAnswer} attribute set to
        L{False}, then return L{None}.  Otherwise, return a L{Deferred} which
        fires with a dictionary of objects representing the result of this
        call.  Additionally, this L{Deferred} may fail with an exception
        representing a connection failure, with L{UnknownRemoteError} if the
        other end of the connection fails for an unknown reason, or with any
        error specified as a key in L{commandType}'s C{errors} dictionary.
        """

        # XXX this takes command subclasses and not command objects on purpose.
        # There's really no reason to have all this back-and-forth between
        # command objects and the protocol, and the extra object being created
        # (the Command instance) is pointless.  Command is kind of like
        # Interface, and should be more like it.

        # In other words, the fact that commandType is instantiated here is an
        # implementation detail.  Don't rely on it.

        try:
            co = commandType(*a, **kw)
        except BaseException:
            return fail()
        return co._doCommand(self)

    def unhandledError(self, failure):
        """
        This is a terminal callback called after application code has had a
        chance to quash any errors.
        """
        return self.boxSender.unhandledError(failure)

    def _answerReceived(self, box):
        """
        An AMP box was received that answered a command previously sent with
        L{callRemote}.

        @param box: an AmpBox with a value for its L{ANSWER} key.
        """
        question = self._outstandingRequests.pop(box[ANSWER])
        question.addErrback(self.unhandledError)
        question.callback(box)

    def _errorReceived(self, box):
        """
        An AMP box was received that answered a command previously sent with
        L{callRemote}, with an error.

        @param box: an L{AmpBox} with a value for its L{ERROR}, L{ERROR_CODE},
        and L{ERROR_DESCRIPTION} keys.
        """
        question = self._outstandingRequests.pop(box[ERROR])
        question.addErrback(self.unhandledError)
        errorCode = box[ERROR_CODE]
        description = box[ERROR_DESCRIPTION]
        if isinstance(description, bytes):
            description = description.decode("utf-8", "replace")
        if errorCode in PROTOCOL_ERRORS:
            exc = PROTOCOL_ERRORS[errorCode](errorCode, description)
        else:
            exc = RemoteAmpError(errorCode, description)
        question.errback(Failure(exc))

    def _commandReceived(self, box):
        """
        @param box: an L{AmpBox} with a value for its L{COMMAND} and L{ASK}
        keys.
        """

        def formatAnswer(answerBox):
            answerBox[ANSWER] = box[ASK]
            return answerBox

        def formatError(error):
            if error.check(RemoteAmpError):
                code = error.value.errorCode
                desc = error.value.description
                if isinstance(desc, str):
                    desc = desc.encode("utf-8", "replace")
                if error.value.fatal:
                    errorBox = QuitBox()
                else:
                    errorBox = AmpBox()
            else:
                errorBox = QuitBox()
                log.err(error)  # here is where server-side logging happens
                # if the error isn't handled
                code = UNKNOWN_ERROR_CODE
                desc = b"Unknown Error"
            errorBox[ERROR] = box[ASK]
            errorBox[ERROR_DESCRIPTION] = desc
            errorBox[ERROR_CODE] = code
            return errorBox

        deferred = self.dispatchCommand(box)
        if ASK in box:
            deferred.addCallbacks(formatAnswer, formatError)
            deferred.addCallback(self._safeEmit)
        deferred.addErrback(self.unhandledError)

    def ampBoxReceived(self, box):
        """
        An AmpBox was received, representing a command, or an answer to a
        previously issued command (either successful or erroneous).  Respond to
        it according to its contents.

        @param box: an AmpBox

        @raise NoEmptyBoxes: when a box is received that does not contain an
        '_answer', '_command' / '_ask', or '_error' key; i.e. one which does not
        fit into the command / response protocol defined by AMP.
        """
        if ANSWER in box:
            self._answerReceived(box)
        elif ERROR in box:
            self._errorReceived(box)
        elif COMMAND in box:
            self._commandReceived(box)
        else:
            raise NoEmptyBoxes(box)

    def _safeEmit(self, aBox):
        """
        Emit a box, ignoring L{ProtocolSwitched} and L{ConnectionLost} errors
        which cannot be usefully handled.
        """
        try:
            aBox._sendTo(self.boxSender)
        except (ProtocolSwitched, ConnectionLost):
            pass

    def dispatchCommand(self, box):
        """
        A box with a _command key was received.

        Dispatch it to a local handler call it.

        @param box: an AmpBox to be dispatched.
        """
        cmd = box[COMMAND]
        responder = self.locator.locateResponder(cmd)
        if responder is None:
            description = f"Unhandled Command: {cmd!r}"
            return fail(
                RemoteAmpError(
                    UNHANDLED_ERROR_CODE,
                    description,
                    False,
                    local=Failure(UnhandledCommand()),
                )
            )
        return maybeDeferred(responder, box)


class _CommandLocatorMeta(type):
    """
    This metaclass keeps track of all of the Command.responder-decorated
    methods defined since the last CommandLocator subclass was defined.  It
    assumes (usually correctly, but unfortunately not necessarily so) that
    those commands responders were all declared as methods of the class
    being defined.  Note that this list can be incorrect if users use the
    Command.responder decorator outside the context of a CommandLocator
    class declaration.

    Command responders defined on subclasses are given precedence over
    those inherited from a base class.

    The Command.responder decorator explicitly cooperates with this
    metaclass.
    """

    _currentClassCommands: "List[Tuple[Command, Callable]]" = []

    def __new__(cls, name, bases, attrs):
        commands = cls._currentClassCommands[:]
        cls._currentClassCommands[:] = []
        cd = attrs["_commandDispatch"] = {}
        subcls = type.__new__(cls, name, bases, attrs)
        ancestors = list(subcls.__mro__[1:])
        ancestors.reverse()
        for ancestor in ancestors:
            cd.update(getattr(ancestor, "_commandDispatch", {}))
        for commandClass, responderFunc in commands:
            cd[commandClass.commandName] = (commandClass, responderFunc)
        if bases and (subcls.lookupFunction != CommandLocator.lookupFunction):

            def locateResponder(self, name):
                warnings.warn(
                    "Override locateResponder, not lookupFunction.",
                    category=PendingDeprecationWarning,
                    stacklevel=2,
                )
                return self.lookupFunction(name)

            subcls.locateResponder = locateResponder
        return subcls


@implementer(IResponderLocator)
class CommandLocator(metaclass=_CommandLocatorMeta):
    """
    A L{CommandLocator} is a collection of responders to AMP L{Command}s, with
    the help of the L{Command.responder} decorator.
    """

    def _wrapWithSerialization(self, aCallable, command):
        """
        Wrap aCallable with its command's argument de-serialization
        and result serialization logic.

        @param aCallable: a callable with a 'command' attribute, designed to be
        called with keyword arguments.

        @param command: the command class whose serialization to use.

        @return: a 1-arg callable which, when invoked with an AmpBox, will
        deserialize the argument list and invoke appropriate user code for the
        callable's command, returning a Deferred which fires with the result or
        fails with an error.
        """

        def doit(box):
            kw = command.parseArguments(box, self)

            def checkKnownErrors(error):
                key = error.trap(*command.allErrors)
                code = command.allErrors[key]
                desc = str(error.value)
                return Failure(
                    RemoteAmpError(code, desc, key in command.fatalErrors, local=error)
                )

            def makeResponseFor(objects):
                try:
                    return command.makeResponse(objects, self)
                except BaseException:
                    # let's helpfully log this.
                    originalFailure = Failure()
                    raise BadLocalReturn(
                        "%r returned %r and %r could not serialize it"
                        % (aCallable, objects, command),
                        originalFailure,
                    )

            return (
                maybeDeferred(aCallable, **kw)
                .addCallback(makeResponseFor)
                .addErrback(checkKnownErrors)
            )

        return doit

    def lookupFunction(self, name):
        """
        Deprecated synonym for L{CommandLocator.locateResponder}
        """
        if self.__class__.lookupFunction != CommandLocator.lookupFunction:
            return CommandLocator.locateResponder(self, name)
        else:
            warnings.warn(
                "Call locateResponder, not lookupFunction.",
                category=PendingDeprecationWarning,
                stacklevel=2,
            )
        return self.locateResponder(name)

    def locateResponder(self, name):
        """
        Locate a callable to invoke when executing the named command.

        @param name: the normalized name (from the wire) of the command.
        @type name: C{bytes}

        @return: a 1-argument function that takes a Box and returns a box or a
        Deferred which fires a Box, for handling the command identified by the
        given name, or None, if no appropriate responder can be found.
        """
        # Try to find a high-level method to invoke, and if we can't find one,
        # fall back to a low-level one.
        cd = self._commandDispatch
        if name in cd:
            commandClass, responderFunc = cd[name]
            responderMethod = MethodType(responderFunc, self)
            return self._wrapWithSerialization(responderMethod, commandClass)


@implementer(IResponderLocator)
class SimpleStringLocator:
    """
    Implement the L{AMP.locateResponder} method to do simple, string-based
    dispatch.
    """

    baseDispatchPrefix = b"amp_"

    def locateResponder(self, name):
        """
        Locate a callable to invoke when executing the named command.

        @return: a function with the name C{"amp_" + name} on the same
            instance, or None if no such function exists.
            This function will then be called with the L{AmpBox} itself as an
            argument.

        @param name: the normalized name (from the wire) of the command.
        @type name: C{bytes}
        """
        fName = nativeString(self.baseDispatchPrefix + name.upper())
        return getattr(self, fName, None)


PYTHON_KEYWORDS = [
    "and",
    "del",
    "for",
    "is",
    "raise",
    "assert",
    "elif",
    "from",
    "lambda",
    "return",
    "break",
    "else",
    "global",
    "not",
    "try",
    "class",
    "except",
    "if",
    "or",
    "while",
    "continue",
    "exec",
    "import",
    "pass",
    "yield",
    "def",
    "finally",
    "in",
    "print",
]


def _wireNameToPythonIdentifier(key):
    """
    (Private) Normalize an argument name from the wire for use with Python
    code.  If the return value is going to be a python keyword it will be
    capitalized.  If it contains any dashes they will be replaced with
    underscores.

    The rationale behind this method is that AMP should be an inherently
    multi-language protocol, so message keys may contain all manner of bizarre
    bytes.  This is not a complete solution; there are still forms of arguments
    that this implementation will be unable to parse.  However, Python
    identifiers share a huge raft of properties with identifiers from many
    other languages, so this is a 'good enough' effort for now.  We deal
    explicitly with dashes because that is the most likely departure: Lisps
    commonly use dashes to separate method names, so protocols initially
    implemented in a lisp amp dialect may use dashes in argument or command
    names.

    @param key: a C{bytes}, looking something like 'foo-bar-baz' or 'from'
    @type key: C{bytes}

    @return: a native string which is a valid python identifier, looking
    something like 'foo_bar_baz' or 'From'.
    """
    lkey = nativeString(key.replace(b"-", b"_"))
    if lkey in PYTHON_KEYWORDS:
        return lkey.title()
    return lkey


@implementer(IArgumentType)
class Argument:
    """
    Base-class of all objects that take values from Amp packets and convert
    them into objects for Python functions.

    This implementation of L{IArgumentType} provides several higher-level
    hooks for subclasses to override.  See L{toString} and L{fromString}
    which will be used to define the behavior of L{IArgumentType.toBox} and
    L{IArgumentType.fromBox}, respectively.
    """

    optional = False

    def __init__(self, optional=False):
        """
        Create an Argument.

        @param optional: a boolean indicating whether this argument can be
        omitted in the protocol.
        """
        self.optional = optional

    def retrieve(self, d, name, proto):
        """
        Retrieve the given key from the given dictionary, removing it if found.

        @param d: a dictionary.

        @param name: a key in I{d}.

        @param proto: an instance of an AMP.

        @raise KeyError: if I am not optional and no value was found.

        @return: d[name].
        """
        if self.optional:
            value = d.get(name)
            if value is not None:
                del d[name]
        else:
            value = d.pop(name)
        return value

    def fromBox(self, name, strings, objects, proto):
        """
        Populate an 'out' dictionary with mapping names to Python values
        decoded from an 'in' AmpBox mapping strings to string values.

        @param name: the argument name to retrieve
        @type name: C{bytes}

        @param strings: The AmpBox to read string(s) from, a mapping of
        argument names to string values.
        @type strings: AmpBox

        @param objects: The dictionary to write object(s) to, a mapping of
        names to Python objects. Keys will be native strings.
        @type objects: dict

        @param proto: an AMP instance.
        """
        st = self.retrieve(strings, name, proto)
        nk = _wireNameToPythonIdentifier(name)
        if self.optional and st is None:
            objects[nk] = None
        else:
            objects[nk] = self.fromStringProto(st, proto)

    def toBox(self, name, strings, objects, proto):
        """
        Populate an 'out' AmpBox with strings encoded from an 'in' dictionary
        mapping names to Python values.

        @param name: the argument name to retrieve
        @type name: C{bytes}

        @param strings: The AmpBox to write string(s) to, a mapping of
        argument names to string values.
        @type strings: AmpBox

        @param objects: The dictionary to read object(s) from, a mapping of
        names to Python objects. Keys should be native strings.

        @type objects: dict

        @param proto: the protocol we are converting for.
        @type proto: AMP
        """
        obj = self.retrieve(objects, _wireNameToPythonIdentifier(name), proto)
        if self.optional and obj is None:
            # strings[name] = None
            pass
        else:
            strings[name] = self.toStringProto(obj, proto)

    def fromStringProto(self, inString, proto):
        """
        Convert a string to a Python value.

        @param inString: the string to convert.
        @type inString: C{bytes}

        @param proto: the protocol we are converting for.
        @type proto: AMP

        @return: a Python object.
        """
        return self.fromString(inString)

    def toStringProto(self, inObject, proto):
        """
        Convert a Python object to a string.

        @param inObject: the object to convert.

        @param proto: the protocol we are converting for.
        @type proto: AMP
        """
        return self.toString(inObject)

    def fromString(self, inString):
        """
        Convert a string to a Python object.  Subclasses must implement this.

        @param inString: the string to convert.
        @type inString: C{bytes}

        @return: the decoded value from C{inString}
        """

    def toString(self, inObject):
        """
        Convert a Python object into a string for passing over the network.

        @param inObject: an object of the type that this Argument is intended
        to deal with.

        @return: the wire encoding of inObject
        @rtype: C{bytes}
        """


class Integer(Argument):
    """
    Encode any integer values of any size on the wire as the string
    representation.

    Example: C{123} becomes C{"123"}
    """

    fromString = int

    def toString(self, inObject):
        return b"%d" % (inObject,)


class String(Argument):
    """
    Don't do any conversion at all; just pass through 'str'.
    """

    def toString(self, inObject):
        return inObject

    def fromString(self, inString):
        return inString


class Float(Argument):
    """
    Encode floating-point values on the wire as their repr.
    """

    fromString = float

    def toString(self, inString):
        if not isinstance(inString, float):
            raise ValueError(f"Bad float value {inString!r}")
        return str(inString).encode("ascii")


class Boolean(Argument):
    """
    Encode True or False as "True" or "False" on the wire.
    """

    def fromString(self, inString):
        if inString == b"True":
            return True
        elif inString == b"False":
            return False
        else:
            raise TypeError(f"Bad boolean value: {inString!r}")

    def toString(self, inObject):
        if inObject:
            return b"True"
        else:
            return b"False"


class Unicode(String):
    """
    Encode a unicode string on the wire as UTF-8.
    """

    def toString(self, inObject):
        return String.toString(self, inObject.encode("utf-8"))

    def fromString(self, inString):
        return String.fromString(self, inString).decode("utf-8")


class Path(Unicode):
    """
    Encode and decode L{filepath.FilePath} instances as paths on the wire.

    This is really intended for use with subprocess communication tools:
    exchanging pathnames on different machines over a network is not generally
    meaningful, but neither is it disallowed; you can use this to communicate
    about NFS paths, for example.
    """

    def fromString(self, inString):
        return filepath.FilePath(Unicode.fromString(self, inString))

    def toString(self, inObject):
        return Unicode.toString(self, inObject.asTextMode().path)


class ListOf(Argument):
    """
    Encode and decode lists of instances of a single other argument type.

    For example, if you want to pass::

        [3, 7, 9, 15]

    You can create an argument like this::

        ListOf(Integer())

    The serialized form of the entire list is subject to the limit imposed by
    L{MAX_VALUE_LENGTH}.  List elements are represented as 16-bit length
    prefixed strings.  The argument type passed to the L{ListOf} initializer is
    responsible for producing the serialized form of each element.

    @ivar elementType: The L{Argument} instance used to encode and decode list
        elements (note, not an arbitrary L{IArgumentType} implementation:
        arguments must be implemented using only the C{fromString} and
        C{toString} methods, not the C{fromBox} and C{toBox} methods).

    @param optional: a boolean indicating whether this argument can be
        omitted in the protocol.

    @since: 10.0
    """

    def __init__(self, elementType, optional=False):
        self.elementType = elementType
        Argument.__init__(self, optional)

    def fromString(self, inString):
        """
        Convert the serialized form of a list of instances of some type back
        into that list.
        """
        strings = []
        parser = Int16StringReceiver()
        parser.stringReceived = strings.append
        parser.dataReceived(inString)
        elementFromString = self.elementType.fromString
        return [elementFromString(string) for string in strings]

    def toString(self, inObject):
        """
        Serialize the given list of objects to a single string.
        """
        strings = []
        for obj in inObject:
            serialized = self.elementType.toString(obj)
            strings.append(pack("!H", len(serialized)))
            strings.append(serialized)
        return b"".join(strings)


class AmpList(Argument):
    """
    Convert a list of dictionaries into a list of AMP boxes on the wire.

    For example, if you want to pass::

        [{'a': 7, 'b': u'hello'}, {'a': 9, 'b': u'goodbye'}]

    You might use an AmpList like this in your arguments or response list::

        AmpList([('a', Integer()),
                 ('b', Unicode())])
    """

    def __init__(self, subargs, optional=False):
        """
        Create an AmpList.

        @param subargs: a list of 2-tuples of ('name', argument) describing the
        schema of the dictionaries in the sequence of amp boxes.
        @type subargs: A C{list} of (C{bytes}, L{Argument}) tuples.

        @param optional: a boolean indicating whether this argument can be
        omitted in the protocol.
        """
        assert all(isinstance(name, bytes) for name, _ in subargs), (
            "AmpList should be defined with a list of (name, argument) "
            "tuples where `name' is a byte string, got: %r" % (subargs,)
        )
        self.subargs = subargs
        Argument.__init__(self, optional)

    def fromStringProto(self, inString, proto):
        boxes = parseString(inString)
        values = [_stringsToObjects(box, self.subargs, proto) for box in boxes]
        return values

    def toStringProto(self, inObject, proto):
        return b"".join(
            [
                _objectsToStrings(objects, self.subargs, Box(), proto).serialize()
                for objects in inObject
            ]
        )


class Descriptor(Integer):
    """
    Encode and decode file descriptors for exchange over a UNIX domain socket.

    This argument type requires an AMP connection set up over an
    L{IUNIXTransport<twisted.internet.interfaces.IUNIXTransport>} provider (for
    example, the kind of connection created by
    L{IReactorUNIX.connectUNIX<twisted.internet.interfaces.IReactorUNIX.connectUNIX>}
    and L{UNIXClientEndpoint<twisted.internet.endpoints.UNIXClientEndpoint>}).

    There is no correspondence between the integer value of the file descriptor
    on the sending and receiving sides, therefore an alternate approach is taken
    to matching up received descriptors with particular L{Descriptor}
    parameters.  The argument is encoded to an ordinal (unique per connection)
    for inclusion in the AMP command or response box.  The descriptor itself is
    sent using
    L{IUNIXTransport.sendFileDescriptor<twisted.internet.interfaces.IUNIXTransport.sendFileDescriptor>}.
    The receiver uses the order in which file descriptors are received and the
    ordinal value to come up with the received copy of the descriptor.
    """

    def fromStringProto(self, inString, proto):
        """
        Take a unique identifier associated with a file descriptor which must
        have been received by now and use it to look up that descriptor in a
        dictionary where they are kept.

        @param inString: The base representation (as a byte string) of an
            ordinal indicating which file descriptor corresponds to this usage
            of this argument.
        @type inString: C{str}

        @param proto: The protocol used to receive this descriptor.  This
            protocol must be connected via a transport providing
            L{IUNIXTransport<twisted.internet.interfaces.IUNIXTransport>}.
        @type proto: L{BinaryBoxProtocol}

        @return: The file descriptor represented by C{inString}.
        @rtype: C{int}
        """
        return proto._getDescriptor(int(inString))

    def toStringProto(self, inObject, proto):
        """
        Send C{inObject}, an integer file descriptor, over C{proto}'s connection
        and return a unique identifier which will allow the receiver to
        associate the file descriptor with this argument.

        @param inObject: A file descriptor to duplicate over an AMP connection
            as the value for this argument.
        @type inObject: C{int}

        @param proto: The protocol which will be used to send this descriptor.
            This protocol must be connected via a transport providing
            L{IUNIXTransport<twisted.internet.interfaces.IUNIXTransport>}.

        @return: A byte string which can be used by the receiver to reconstruct
            the file descriptor.
        @rtype: C{bytes}
        """
        identifier = proto._sendFileDescriptor(inObject)
        outString = Integer.toStringProto(self, identifier, proto)
        return outString


class _CommandMeta(type):
    """
    Metaclass hack to establish reverse-mappings for 'errors' and
    'fatalErrors' as class vars.
    """

    def __new__(cls, name, bases, attrs):
        reverseErrors = attrs["reverseErrors"] = {}
        er = attrs["allErrors"] = {}
        if "commandName" not in attrs:
            attrs["commandName"] = name.encode("ascii")
        newtype = type.__new__(cls, name, bases, attrs)

        if not isinstance(newtype.commandName, bytes):
            raise TypeError(
                "Command names must be byte strings, got: {!r}".format(
                    newtype.commandName
                )
            )
        for name, _ in newtype.arguments:
            if not isinstance(name, bytes):
                raise TypeError(f"Argument names must be byte strings, got: {name!r}")
        for name, _ in newtype.response:
            if not isinstance(name, bytes):
                raise TypeError(f"Response names must be byte strings, got: {name!r}")

        errors: Dict[Type[Exception], bytes] = {}
        fatalErrors: Dict[Type[Exception], bytes] = {}
        accumulateClassDict(newtype, "errors", errors)
        accumulateClassDict(newtype, "fatalErrors", fatalErrors)

        if not isinstance(newtype.errors, dict):
            newtype.errors = dict(newtype.errors)
        if not isinstance(newtype.fatalErrors, dict):
            newtype.fatalErrors = dict(newtype.fatalErrors)

        for v, k in errors.items():
            reverseErrors[k] = v
            er[v] = k
        for v, k in fatalErrors.items():
            reverseErrors[k] = v
            er[v] = k

        for _, name in newtype.errors.items():
            if not isinstance(name, bytes):
                raise TypeError(f"Error names must be byte strings, got: {name!r}")
        for _, name in newtype.fatalErrors.items():
            if not isinstance(name, bytes):
                raise TypeError(
                    f"Fatal error names must be byte strings, got: {name!r}"
                )

        return newtype


class Command(metaclass=_CommandMeta):
    """
    Subclass me to specify an AMP Command.

    @cvar arguments: A list of 2-tuples of (name, Argument-subclass-instance),
    specifying the names and values of the parameters which are required for
    this command.

    @cvar response: A list like L{arguments}, but instead used for the return
    value.

    @cvar errors: A mapping of subclasses of L{Exception} to wire-protocol tags
        for errors represented as L{str}s.  Responders which raise keys from
        this dictionary will have the error translated to the corresponding tag
        on the wire.
        Invokers which receive Deferreds from invoking this command with
        L{BoxDispatcher.callRemote} will potentially receive Failures with keys
        from this mapping as their value.
        This mapping is inherited; if you declare a command which handles
        C{FooError} as 'FOO_ERROR', then subclass it and specify C{BarError} as
        'BAR_ERROR', responders to the subclass may raise either C{FooError} or
        C{BarError}, and invokers must be able to deal with either of those
        exceptions.

    @cvar fatalErrors: like 'errors', but errors in this list will always
    terminate the connection, despite being of a recognizable error type.

    @cvar commandType: The type of Box used to issue commands; useful only for
    protocol-modifying behavior like startTLS or protocol switching.  Defaults
    to a plain vanilla L{Box}.

    @cvar responseType: The type of Box used to respond to this command; only
    useful for protocol-modifying behavior like startTLS or protocol switching.
    Defaults to a plain vanilla L{Box}.

    @ivar requiresAnswer: a boolean; defaults to True.  Set it to False on your
    subclass if you want callRemote to return None.  Note: this is a hint only
    to the client side of the protocol.  The return-type of a command responder
    method must always be a dictionary adhering to the contract specified by
    L{response}, because clients are always free to request a response if they
    want one.
    """

    arguments: List[Tuple[bytes, Argument]] = []
    response: List[Tuple[bytes, Argument]] = []
    extra: List[Any] = []
    errors: Dict[Type[Exception], bytes] = {}
    fatalErrors: Dict[Type[Exception], bytes] = {}

    commandType: "Union[Type[Command], Type[Box]]" = Box
    responseType: Type[AmpBox] = Box

    requiresAnswer = True

    def __init__(self, **kw):
        """
        Create an instance of this command with specified values for its
        parameters.

        In Python 3, keyword arguments MUST be Unicode/native strings whereas
        in Python 2 they could be either byte strings or Unicode strings.

        A L{Command}'s arguments are defined in its schema using C{bytes}
        names. The values for those arguments are plucked from the keyword
        arguments using the name returned from L{_wireNameToPythonIdentifier}.
        In other words, keyword arguments should be named using the
        Python-side equivalent of the on-wire (C{bytes}) name.

        @param kw: a dict containing an appropriate value for each name
        specified in the L{arguments} attribute of my class.

        @raise InvalidSignature: if you forgot any required arguments.
        """
        self.structured = kw
        forgotten = []
        for name, arg in self.arguments:
            pythonName = _wireNameToPythonIdentifier(name)
            if pythonName not in self.structured and not arg.optional:
                forgotten.append(pythonName)
        if forgotten:
            raise InvalidSignature(
                "forgot {} for {}".format(", ".join(forgotten), self.commandName)
            )
        forgotten = []

    @classmethod
    def makeResponse(cls, objects, proto):
        """
        Serialize a mapping of arguments using this L{Command}'s
        response schema.

        @param objects: a dict with keys matching the names specified in
        self.response, having values of the types that the Argument objects in
        self.response can format.

        @param proto: an L{AMP}.

        @return: an L{AmpBox}.
        """
        try:
            responseType = cls.responseType()
        except BaseException:
            return fail()
        return _objectsToStrings(objects, cls.response, responseType, proto)

    @classmethod
    def makeArguments(cls, objects, proto):
        """
        Serialize a mapping of arguments using this L{Command}'s
        argument schema.

        @param objects: a dict with keys similar to the names specified in
        self.arguments, having values of the types that the Argument objects in
        self.arguments can parse.

        @param proto: an L{AMP}.

        @return: An instance of this L{Command}'s C{commandType}.
        """
        allowedNames = set()
        for (argName, ignored) in cls.arguments:
            allowedNames.add(_wireNameToPythonIdentifier(argName))

        for intendedArg in objects:
            if intendedArg not in allowedNames:
                raise InvalidSignature(f"{intendedArg} is not a valid argument")
        return _objectsToStrings(objects, cls.arguments, cls.commandType(), proto)

    @classmethod
    def parseResponse(cls, box, protocol):
        """
        Parse a mapping of serialized arguments using this
        L{Command}'s response schema.

        @param box: A mapping of response-argument names to the
        serialized forms of those arguments.
        @param protocol: The L{AMP} protocol.

        @return: A mapping of response-argument names to the parsed
        forms.
        """
        return _stringsToObjects(box, cls.response, protocol)

    @classmethod
    def parseArguments(cls, box, protocol):
        """
        Parse a mapping of serialized arguments using this
        L{Command}'s argument schema.

        @param box: A mapping of argument names to the seralized forms
        of those arguments.
        @param protocol: The L{AMP} protocol.

        @return: A mapping of argument names to the parsed forms.
        """
        return _stringsToObjects(box, cls.arguments, protocol)

    @classmethod
    def responder(cls, methodfunc):
        """
        Declare a method to be a responder for a particular command.

        This is a decorator.

        Use like so::

            class MyCommand(Command):
                arguments = [('a', ...), ('b', ...)]

            class MyProto(AMP):
                def myFunMethod(self, a, b):
                    ...
                MyCommand.responder(myFunMethod)

        Notes: Although decorator syntax is not used within Twisted, this
        function returns its argument and is therefore safe to use with
        decorator syntax.

        This is not thread safe.  Don't declare AMP subclasses in other
        threads.  Don't declare responders outside the scope of AMP subclasses;
        the behavior is undefined.

        @param methodfunc: A function which will later become a method, which
        has a keyword signature compatible with this command's L{arguments} list
        and returns a dictionary with a set of keys compatible with this
        command's L{response} list.

        @return: the methodfunc parameter.
        """
        CommandLocator._currentClassCommands.append((cls, methodfunc))
        return methodfunc

    # Our only instance method
    def _doCommand(self, proto):
        """
        Encode and send this Command to the given protocol.

        @param proto: an AMP, representing the connection to send to.

        @return: a Deferred which will fire or error appropriately when the
        other side responds to the command (or error if the connection is lost
        before it is responded to).
        """

        def _massageError(error):
            error.trap(RemoteAmpError)
            rje = error.value
            errorType = self.reverseErrors.get(rje.errorCode, UnknownRemoteError)
            return Failure(errorType(rje.description))

        d = proto._sendBoxCommand(
            self.commandName,
            self.makeArguments(self.structured, proto),
            self.requiresAnswer,
        )

        if self.requiresAnswer:
            d.addCallback(self.parseResponse, proto)
            d.addErrback(_massageError)

        return d


class _NoCertificate:
    """
    This is for peers which don't want to use a local certificate.  Used by
    AMP because AMP's internal language is all about certificates and this
    duck-types in the appropriate place; this API isn't really stable though,
    so it's not exposed anywhere public.

    For clients, it will use ephemeral DH keys, or whatever the default is for
    certificate-less clients in OpenSSL.  For servers, it will generate a
    temporary self-signed certificate with garbage values in the DN and use
    that.
    """

    def __init__(self, client):
        """
        Create a _NoCertificate which either is or isn't for the client side of
        the connection.

        @param client: True if we are a client and should truly have no
        certificate and be anonymous, False if we are a server and actually
        have to generate a temporary certificate.

        @type client: bool
        """
        self.client = client

    def options(self, *authorities):
        """
        Behaves like L{twisted.internet.ssl.PrivateCertificate.options}().
        """
        if not self.client:
            # do some crud with sslverify to generate a temporary self-signed
            # certificate.  This is SLOOOWWWWW so it is only in the absolute
            # worst, most naive case.

            # We have to do this because OpenSSL will not let both the server
            # and client be anonymous.
            sharedDN = DN(CN="TEMPORARY CERTIFICATE")
            key = KeyPair.generate()
            cr = key.certificateRequest(sharedDN)
            sscrd = key.signCertificateRequest(sharedDN, cr, lambda dn: True, 1)
            cert = key.newCertificate(sscrd)
            return cert.options(*authorities)
        options = dict()
        if authorities:
            options.update(
                dict(
                    verify=True,
                    requireCertificate=True,
                    caCerts=[auth.original for auth in authorities],
                )
            )
        occo = CertificateOptions(**options)
        return occo


class _TLSBox(AmpBox):
    """
    I am an AmpBox that, upon being sent, initiates a TLS connection.
    """

    __slots__: List[str] = []

    def __init__(self):
        if ssl is None:
            raise RemoteAmpError(b"TLS_ERROR", "TLS not available")
        AmpBox.__init__(self)

    @property
    def certificate(self):
        return self.get(b"tls_localCertificate", _NoCertificate(False))

    @property
    def verify(self):
        return self.get(b"tls_verifyAuthorities", None)

    def _sendTo(self, proto):
        """
        Send my encoded value to the protocol, then initiate TLS.
        """
        ab = AmpBox(self)
        for k in [b"tls_localCertificate", b"tls_verifyAuthorities"]:
            ab.pop(k, None)
        ab._sendTo(proto)
        proto._startTLS(self.certificate, self.verify)


class _LocalArgument(String):
    """
    Local arguments are never actually relayed across the wire.  This is just a
    shim so that StartTLS can pretend to have some arguments: if arguments
    acquire documentation properties, replace this with something nicer later.
    """

    def fromBox(self, name, strings, objects, proto):
        pass


class StartTLS(Command):
    """
    Use, or subclass, me to implement a command that starts TLS.

    Callers of StartTLS may pass several special arguments, which affect the
    TLS negotiation:

        - tls_localCertificate: This is a
        twisted.internet.ssl.PrivateCertificate which will be used to secure
        the side of the connection it is returned on.

        - tls_verifyAuthorities: This is a list of
        twisted.internet.ssl.Certificate objects that will be used as the
        certificate authorities to verify our peer's certificate.

    Each of those special parameters may also be present as a key in the
    response dictionary.
    """

    arguments = [
        (b"tls_localCertificate", _LocalArgument(optional=True)),
        (b"tls_verifyAuthorities", _LocalArgument(optional=True)),
    ]

    response = [
        (b"tls_localCertificate", _LocalArgument(optional=True)),
        (b"tls_verifyAuthorities", _LocalArgument(optional=True)),
    ]

    responseType = _TLSBox

    def __init__(self, *, tls_localCertificate=None, tls_verifyAuthorities=None, **kw):
        """
        Create a StartTLS command.  (This is private.  Use AMP.callRemote.)

        @param tls_localCertificate: the PrivateCertificate object to use to
        secure the connection.  If it's L{None}, or unspecified, an ephemeral DH
        key is used instead.

        @param tls_verifyAuthorities: a list of Certificate objects which
        represent root certificates to verify our peer with.
        """
        if ssl is None:
            raise RuntimeError("TLS not available.")
        self.certificate = (
            _NoCertificate(True)
            if tls_localCertificate is None
            else tls_localCertificate
        )
        self.authorities = tls_verifyAuthorities
        Command.__init__(self, **kw)

    def _doCommand(self, proto):
        """
        When a StartTLS command is sent, prepare to start TLS, but don't actually
        do it; wait for the acknowledgement, then initiate the TLS handshake.
        """
        d = Command._doCommand(self, proto)
        proto._prepareTLS(self.certificate, self.authorities)
        # XXX before we get back to user code we are going to start TLS...

        def actuallystart(response):
            proto._startTLS(self.certificate, self.authorities)
            return response

        d.addCallback(actuallystart)
        return d


class ProtocolSwitchCommand(Command):
    """
    Use this command to switch from something Amp-derived to a different
    protocol mid-connection.  This can be useful to use amp as the
    connection-startup negotiation phase.  Since TLS is a different layer
    entirely, you can use Amp to negotiate the security parameters of your
    connection, then switch to a different protocol, and the connection will
    remain secured.
    """

    def __init__(self, _protoToSwitchToFactory, **kw):
        """
        Create a ProtocolSwitchCommand.

        @param _protoToSwitchToFactory: a ProtocolFactory which will generate
        the Protocol to switch to.

        @param kw: Keyword arguments, encoded and handled normally as
        L{Command} would.
        """

        self.protoToSwitchToFactory = _protoToSwitchToFactory
        super().__init__(**kw)

    @classmethod
    def makeResponse(cls, innerProto, proto):
        return _SwitchBox(innerProto)

    def _doCommand(self, proto):
        """
        When we emit a ProtocolSwitchCommand, lock the protocol, but don't actually
        switch to the new protocol unless an acknowledgement is received.  If
        an error is received, switch back.
        """
        d = super()._doCommand(proto)
        proto._lockForSwitch()

        def switchNow(ign):
            innerProto = self.protoToSwitchToFactory.buildProtocol(
                proto.transport.getPeer()
            )
            proto._switchTo(innerProto, self.protoToSwitchToFactory)
            return ign

        def handle(ign):
            proto._unlockFromSwitch()
            self.protoToSwitchToFactory.clientConnectionFailed(
                None, Failure(CONNECTION_LOST)
            )
            return ign

        return d.addCallbacks(switchNow, handle)


@implementer(IFileDescriptorReceiver)
class _DescriptorExchanger:
    """
    L{_DescriptorExchanger} is a mixin for L{BinaryBoxProtocol} which adds
    support for receiving file descriptors, a feature offered by
    L{IUNIXTransport<twisted.internet.interfaces.IUNIXTransport>}.

    @ivar _descriptors: Temporary storage for all file descriptors received.
        Values in this dictionary are the file descriptors (as integers).  Keys
        in this dictionary are ordinals giving the order in which each
        descriptor was received.  The ordering information is used to allow
        L{Descriptor} to determine which is the correct descriptor for any
        particular usage of that argument type.
    @type _descriptors: C{dict}

    @ivar _sendingDescriptorCounter: A no-argument callable which returns the
        ordinals, starting from 0.  This is used to construct values for
        C{_sendFileDescriptor}.

    @ivar _receivingDescriptorCounter: A no-argument callable which returns the
        ordinals, starting from 0.  This is used to construct values for
        C{fileDescriptorReceived}.
    """

    def __init__(self):
        self._descriptors = {}
        self._getDescriptor = self._descriptors.pop
        self._sendingDescriptorCounter = partial(next, count())
        self._receivingDescriptorCounter = partial(next, count())

    def _sendFileDescriptor(self, descriptor):
        """
        Assign and return the next ordinal to the given descriptor after sending
        the descriptor over this protocol's transport.
        """
        self.transport.sendFileDescriptor(descriptor)
        return self._sendingDescriptorCounter()

    def fileDescriptorReceived(self, descriptor):
        """
        Collect received file descriptors to be claimed later by L{Descriptor}.

        @param descriptor: The received file descriptor.
        @type descriptor: C{int}
        """
        self._descriptors[self._receivingDescriptorCounter()] = descriptor


@implementer(IBoxSender)
class BinaryBoxProtocol(
    StatefulStringProtocol, Int16StringReceiver, _DescriptorExchanger
):
    """
    A protocol for receiving L{AmpBox}es - key/value pairs - via length-prefixed
    strings.  A box is composed of:

        - any number of key-value pairs, described by:
            - a 2-byte network-endian packed key length (of which the first
              byte must be null, and the second must be non-null: i.e. the
              value of the length must be 1-255)
            - a key, comprised of that many bytes
            - a 2-byte network-endian unsigned value length (up to the maximum
              of 65535)
            - a value, comprised of that many bytes
        - 2 null bytes

    In other words, an even number of strings prefixed with packed unsigned
    16-bit integers, and then a 0-length string to indicate the end of the box.

    This protocol also implements 2 extra private bits of functionality related
    to the byte boundaries between messages; it can start TLS between two given
    boxes or switch to an entirely different protocol.  However, due to some
    tricky elements of the implementation, the public interface to this
    functionality is L{ProtocolSwitchCommand} and L{StartTLS}.

    @ivar _keyLengthLimitExceeded: A flag which is only true when the
        connection is being closed because a key length prefix which was longer
        than allowed by the protocol was received.

    @ivar boxReceiver: an L{IBoxReceiver} provider, whose
        L{IBoxReceiver.ampBoxReceived} method will be invoked for each
        L{AmpBox} that is received.
    """

    _justStartedTLS = False
    _startingTLSBuffer = None
    _locked = False
    _currentKey = None
    _currentBox = None

    _keyLengthLimitExceeded = False

    hostCertificate = None
    noPeerCertificate = False  # for tests
    innerProtocol: Optional[Protocol] = None
    innerProtocolClientFactory = None

    def __init__(self, boxReceiver):
        _DescriptorExchanger.__init__(self)
        self.boxReceiver = boxReceiver

    def _switchTo(self, newProto, clientFactory=None):
        """
        Switch this BinaryBoxProtocol's transport to a new protocol.  You need
        to do this 'simultaneously' on both ends of a connection; the easiest
        way to do this is to use a subclass of ProtocolSwitchCommand.

        @param newProto: the new protocol instance to switch to.

        @param clientFactory: the ClientFactory to send the
            L{twisted.internet.protocol.ClientFactory.clientConnectionLost}
            notification to.
        """
        # All the data that Int16Receiver has not yet dealt with belongs to our
        # new protocol: luckily it's keeping that in a handy (although
        # ostensibly internal) variable for us:
        newProtoData = self.recvd
        # We're quite possibly in the middle of a 'dataReceived' loop in
        # Int16StringReceiver: let's make sure that the next iteration, the
        # loop will break and not attempt to look at something that isn't a
        # length prefix.
        self.recvd = ""
        # Finally, do the actual work of setting up the protocol and delivering
        # its first chunk of data, if one is available.
        self.innerProtocol = newProto
        self.innerProtocolClientFactory = clientFactory
        newProto.makeConnection(self.transport)
        if newProtoData:
            newProto.dataReceived(newProtoData)

    def sendBox(self, box):
        """
        Send a amp.Box to my peer.

        Note: transport.write is never called outside of this method.

        @param box: an AmpBox.

        @raise ProtocolSwitched: if the protocol has previously been switched.

        @raise ConnectionLost: if the connection has previously been lost.
        """
        if self._locked:
            raise ProtocolSwitched(
                "This connection has switched: no AMP traffic allowed."
            )
        if self.transport is None:
            raise ConnectionLost()
        if self._startingTLSBuffer is not None:
            self._startingTLSBuffer.append(box)
        else:
            self.transport.write(box.serialize())

    def makeConnection(self, transport):
        """
        Notify L{boxReceiver} that it is about to receive boxes from this
        protocol by invoking L{IBoxReceiver.startReceivingBoxes}.
        """
        self.transport = transport
        self.boxReceiver.startReceivingBoxes(self)
        self.connectionMade()

    def dataReceived(self, data):
        """
        Either parse incoming data as L{AmpBox}es or relay it to our nested
        protocol.
        """
        if self._justStartedTLS:
            self._justStartedTLS = False
        # If we already have an inner protocol, then we don't deliver data to
        # the protocol parser any more; we just hand it off.
        if self.innerProtocol is not None:
            self.innerProtocol.dataReceived(data)
            return
        return Int16StringReceiver.dataReceived(self, data)

    def connectionLost(self, reason):
        """
        The connection was lost; notify any nested protocol.
        """
        if self.innerProtocol is not None:
            self.innerProtocol.connectionLost(reason)
            if self.innerProtocolClientFactory is not None:
                self.innerProtocolClientFactory.clientConnectionLost(None, reason)
        if self._keyLengthLimitExceeded:
            failReason = Failure(TooLong(True, False, None, None))
        elif reason.check(ConnectionClosed) and self._justStartedTLS:
            # We just started TLS and haven't received any data.  This means
            # the other connection didn't like our cert (although they may not
            # have told us why - later Twisted should make 'reason' into a TLS
            # error.)
            failReason = PeerVerifyError(
                "Peer rejected our certificate for an unknown reason."
            )
        else:
            failReason = reason
        self.boxReceiver.stopReceivingBoxes(failReason)

    # The longest key allowed
    _MAX_KEY_LENGTH = 255

    # The longest value allowed (this is somewhat redundant, as longer values
    # cannot be encoded - ah well).
    _MAX_VALUE_LENGTH = 65535

    # The first thing received is a key.
    MAX_LENGTH = _MAX_KEY_LENGTH

    def proto_init(self, string):
        """
        String received in the 'init' state.
        """
        self._currentBox = AmpBox()
        return self.proto_key(string)

    def proto_key(self, string):
        """
        String received in the 'key' state.  If the key is empty, a complete
        box has been received.
        """
        if string:
            self._currentKey = string
            self.MAX_LENGTH = self._MAX_VALUE_LENGTH
            return "value"
        else:
            self.boxReceiver.ampBoxReceived(self._currentBox)
            self._currentBox = None
            return "init"

    def proto_value(self, string):
        """
        String received in the 'value' state.
        """
        self._currentBox[self._currentKey] = string
        self._currentKey = None
        self.MAX_LENGTH = self._MAX_KEY_LENGTH
        return "key"

    def lengthLimitExceeded(self, length):
        """
        The key length limit was exceeded.  Disconnect the transport and make
        sure a meaningful exception is reported.
        """
        self._keyLengthLimitExceeded = True
        self.transport.loseConnection()

    def _lockForSwitch(self):
        """
        Lock this binary protocol so that no further boxes may be sent.  This
        is used when sending a request to switch underlying protocols.  You
        probably want to subclass ProtocolSwitchCommand rather than calling
        this directly.
        """
        self._locked = True

    def _unlockFromSwitch(self):
        """
        Unlock this locked binary protocol so that further boxes may be sent
        again.  This is used after an attempt to switch protocols has failed
        for some reason.
        """
        if self.innerProtocol is not None:
            raise ProtocolSwitched("Protocol already switched.  Cannot unlock.")
        self._locked = False

    def _prepareTLS(self, certificate, verifyAuthorities):
        """
        Used by StartTLSCommand to put us into the state where we don't
        actually send things that get sent, instead we buffer them.  see
        L{_sendBoxCommand}.
        """
        self._startingTLSBuffer = []
        if self.hostCertificate is not None:
            raise OnlyOneTLS(
                "Previously authenticated connection between %s and %s "
                "is trying to re-establish as %s"
                % (
                    self.hostCertificate,
                    self.peerCertificate,
                    (certificate, verifyAuthorities),
                )
            )

    def _startTLS(self, certificate, verifyAuthorities):
        """
        Used by TLSBox to initiate the SSL handshake.

        @param certificate: a L{twisted.internet.ssl.PrivateCertificate} for
        use locally.

        @param verifyAuthorities: L{twisted.internet.ssl.Certificate} instances
        representing certificate authorities which will verify our peer.
        """
        self.hostCertificate = certificate
        self._justStartedTLS = True
        if verifyAuthorities is None:
            verifyAuthorities = ()
        self.transport.startTLS(certificate.options(*verifyAuthorities))
        stlsb = self._startingTLSBuffer
        if stlsb is not None:
            self._startingTLSBuffer = None
            for box in stlsb:
                self.sendBox(box)

    @property
    def peerCertificate(self):
        if self.noPeerCertificate:
            return None
        return Certificate.peerFromTransport(self.transport)

    def unhandledError(self, failure):
        """
        The buck stops here.  This error was completely unhandled, time to
        terminate the connection.
        """
        log.err(
            failure,
            "Amp server or network failure unhandled by client application.  "
            "Dropping connection!  To avoid, add errbacks to ALL remote "
            "commands!",
        )
        if self.transport is not None:
            self.transport.loseConnection()

    def _defaultStartTLSResponder(self):
        """
        The default TLS responder doesn't specify any certificate or anything.

        From a security perspective, it's little better than a plain-text
        connection - but it is still a *bit* better, so it's included for
        convenience.

        You probably want to override this by providing your own StartTLS.responder.
        """
        return {}

    StartTLS.responder(_defaultStartTLSResponder)


class AMP(BinaryBoxProtocol, BoxDispatcher, CommandLocator, SimpleStringLocator):
    """
    This protocol is an AMP connection.  See the module docstring for protocol
    details.
    """

    _ampInitialized = False

    def __init__(self, boxReceiver=None, locator=None):
        # For backwards compatibility.  When AMP did not separate parsing logic
        # (L{BinaryBoxProtocol}), request-response logic (L{BoxDispatcher}) and
        # command routing (L{CommandLocator}), it did not have a constructor.
        # Now it does, so old subclasses might have defined their own that did
        # not upcall.  If this flag isn't set, we'll call the constructor in
        # makeConnection before anything actually happens.
        self._ampInitialized = True
        if boxReceiver is None:
            boxReceiver = self
        if locator is None:
            locator = self
        BoxDispatcher.__init__(self, locator)
        BinaryBoxProtocol.__init__(self, boxReceiver)

    def locateResponder(self, name):
        """
        Unify the implementations of L{CommandLocator} and
        L{SimpleStringLocator} to perform both kinds of dispatch, preferring
        L{CommandLocator}.

        @type name: C{bytes}
        """
        firstResponder = CommandLocator.locateResponder(self, name)
        if firstResponder is not None:
            return firstResponder
        secondResponder = SimpleStringLocator.locateResponder(self, name)
        return secondResponder

    def __repr__(self) -> str:
        """
        A verbose string representation which gives us information about this
        AMP connection.
        """
        if self.innerProtocol is not None:
            innerRepr = f" inner {self.innerProtocol!r}"
        else:
            innerRepr = ""
        return f"<{self.__class__.__name__}{innerRepr} at 0x{id(self):x}>"

    def makeConnection(self, transport):
        """
        Emit a helpful log message when the connection is made.
        """
        if not self._ampInitialized:
            # See comment in the constructor re: backward compatibility.  I
            # should probably emit a deprecation warning here.
            AMP.__init__(self)
        # Save these so we can emit a similar log message in L{connectionLost}.
        self._transportPeer = transport.getPeer()
        self._transportHost = transport.getHost()
        log.msg(
            "%s connection established (HOST:%s PEER:%s)"
            % (self.__class__.__name__, self._transportHost, self._transportPeer)
        )
        BinaryBoxProtocol.makeConnection(self, transport)

    def connectionLost(self, reason):
        """
        Emit a helpful log message when the connection is lost.
        """
        log.msg(
            "%s connection lost (HOST:%s PEER:%s)"
            % (self.__class__.__name__, self._transportHost, self._transportPeer)
        )
        BinaryBoxProtocol.connectionLost(self, reason)
        self.transport = None


class _ParserHelper:
    """
    A box receiver which records all boxes received.
    """

    def __init__(self):
        self.boxes = []

    def getPeer(self):
        return "string"

    def getHost(self):
        return "string"

    disconnecting = False

    def startReceivingBoxes(self, sender):
        """
        No initialization is required.
        """

    def ampBoxReceived(self, box):
        self.boxes.append(box)

    # Synchronous helpers
    @classmethod
    def parse(cls, fileObj):
        """
        Parse some amp data stored in a file.

        @param fileObj: a file-like object.

        @return: a list of AmpBoxes encoded in the given file.
        """
        parserHelper = cls()
        bbp = BinaryBoxProtocol(boxReceiver=parserHelper)
        bbp.makeConnection(parserHelper)
        bbp.dataReceived(fileObj.read())
        return parserHelper.boxes

    @classmethod
    def parseString(cls, data):
        """
        Parse some amp data stored in a string.

        @param data: a str holding some amp-encoded data.

        @return: a list of AmpBoxes encoded in the given string.
        """
        return cls.parse(BytesIO(data))


parse = _ParserHelper.parse
parseString = _ParserHelper.parseString


def _stringsToObjects(strings, arglist, proto):
    """
    Convert an AmpBox to a dictionary of python objects, converting through a
    given arglist.

    @param strings: an AmpBox (or dict of strings)

    @param arglist: a list of 2-tuples of strings and Argument objects, as
    described in L{Command.arguments}.

    @param proto: an L{AMP} instance.

    @return: the converted dictionary mapping names to argument objects.
    """
    objects = {}
    myStrings = strings.copy()
    for argname, argparser in arglist:
        argparser.fromBox(argname, myStrings, objects, proto)
    return objects


def _objectsToStrings(objects, arglist, strings, proto):
    """
    Convert a dictionary of python objects to an AmpBox, converting through a
    given arglist.

    @param objects: a dict mapping names to python objects

    @param arglist: a list of 2-tuples of strings and Argument objects, as
    described in L{Command.arguments}.

    @param strings: [OUT PARAMETER] An object providing the L{dict}
    interface which will be populated with serialized data.

    @param proto: an L{AMP} instance.

    @return: The converted dictionary mapping names to encoded argument
    strings (identical to C{strings}).
    """
    myObjects = objects.copy()
    for argname, argparser in arglist:
        argparser.toBox(argname, strings, myObjects, proto)
    return strings


class Decimal(Argument):
    """
    Encodes C{decimal.Decimal} instances.

    There are several ways in which a decimal value might be encoded.

    Special values are encoded as special strings::

      - Positive infinity is encoded as C{"Infinity"}
      - Negative infinity is encoded as C{"-Infinity"}
      - Quiet not-a-number is encoded as either C{"NaN"} or C{"-NaN"}
      - Signalling not-a-number is encoded as either C{"sNaN"} or C{"-sNaN"}

    Normal values are encoded using the base ten string representation, using
    engineering notation to indicate magnitude without precision, and "normal"
    digits to indicate precision.  For example::

      - C{"1"} represents the value I{1} with precision to one place.
      - C{"-1"} represents the value I{-1} with precision to one place.
      - C{"1.0"} represents the value I{1} with precision to two places.
      - C{"10"} represents the value I{10} with precision to two places.
      - C{"1E+2"} represents the value I{10} with precision to one place.
      - C{"1E-1"} represents the value I{0.1} with precision to one place.
      - C{"1.5E+2"} represents the value I{15} with precision to two places.

    U{http://speleotrove.com/decimal/} should be considered the authoritative
    specification for the format.
    """

    def fromString(self, inString):
        inString = nativeString(inString)
        return decimal.Decimal(inString)

    def toString(self, inObject):
        """
        Serialize a C{decimal.Decimal} instance to the specified wire format.
        """
        if isinstance(inObject, decimal.Decimal):
            # Hopefully decimal.Decimal.__str__ actually does what we want.
            return str(inObject).encode("ascii")
        raise ValueError("amp.Decimal can only encode instances of decimal.Decimal")


class DateTime(Argument):
    """
    Encodes C{datetime.datetime} instances.

    Wire format: '%04i-%02i-%02iT%02i:%02i:%02i.%06i%s%02i:%02i'. Fields in
    order are: year, month, day, hour, minute, second, microsecond, timezone
    direction (+ or -), timezone hour, timezone minute. Encoded string is
    always exactly 32 characters long. This format is compatible with ISO 8601,
    but that does not mean all ISO 8601 dates can be accepted.

    Also, note that the datetime module's notion of a "timezone" can be
    complex, but the wire format includes only a fixed offset, so the
    conversion is not lossless. A lossless transmission of a C{datetime} instance
    is not feasible since the receiving end would require a Python interpreter.

    @ivar _positions: A sequence of slices giving the positions of various
        interesting parts of the wire format.
    """

    _positions = [
        slice(0, 4),
        slice(5, 7),
        slice(8, 10),  # year, month, day
        slice(11, 13),
        slice(14, 16),
        slice(17, 19),  # hour, minute, second
        slice(20, 26),  # microsecond
        # intentionally skip timezone direction, as it is not an integer
        slice(27, 29),
        slice(30, 32),  # timezone hour, timezone minute
    ]

    def fromString(self, s):
        """
        Parse a string containing a date and time in the wire format into a
        C{datetime.datetime} instance.
        """
        s = nativeString(s)

        if len(s) != 32:
            raise ValueError(f"invalid date format {s!r}")

        values = [int(s[p]) for p in self._positions]
        sign = s[26]
        timezone = _FixedOffsetTZInfo.fromSignHoursMinutes(sign, *values[7:])
        values[7:] = [timezone]
        return datetime.datetime(*values)

    def toString(self, i):
        """
        Serialize a C{datetime.datetime} instance to a string in the specified
        wire format.
        """
        offset = i.utcoffset()
        if offset is None:
            raise ValueError(
                "amp.DateTime cannot serialize naive datetime instances.  "
                "You may find amp.utc useful."
            )

        minutesOffset = (offset.days * 86400 + offset.seconds) // 60

        if minutesOffset > 0:
            sign = "+"
        else:
            sign = "-"

        # strftime has no way to format the microseconds, or put a ':' in the
        # timezone. Surprise!

        # Python 3.4 cannot do % interpolation on byte strings so we pack into
        # an explicitly Unicode string then encode as ASCII.
        packed = "%04i-%02i-%02iT%02i:%02i:%02i.%06i%s%02i:%02i" % (
            i.year,
            i.month,
            i.day,
            i.hour,
            i.minute,
            i.second,
            i.microsecond,
            sign,
            abs(minutesOffset) // 60,
            abs(minutesOffset) % 60,
        )

        return packed.encode("ascii")
