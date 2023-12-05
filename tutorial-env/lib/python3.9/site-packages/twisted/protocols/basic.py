# -*- test-case-name: twisted.protocols.test.test_basic -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Basic protocols, such as line-oriented, netstring, and int prefixed strings.
"""


import math

# System imports
import re
from io import BytesIO
from struct import calcsize, pack, unpack

from zope.interface import implementer

# Twisted imports
from twisted.internet import defer, interfaces, protocol
from twisted.python import log


# Unfortunately we cannot use regular string formatting on Python 3; see
# http://bugs.python.org/issue3982 for details.
def _formatNetstring(data):
    return b"".join([str(len(data)).encode("ascii"), b":", data, b","])


_formatNetstring.__doc__ = """
Convert some C{bytes} into netstring format.

@param data: C{bytes} that will be reformatted.
"""


DEBUG = 0


class NetstringParseError(ValueError):
    """
    The incoming data is not in valid Netstring format.
    """


class IncompleteNetstring(Exception):
    """
    Not enough data to complete a netstring.
    """


class NetstringReceiver(protocol.Protocol):
    """
    A protocol that sends and receives netstrings.

    See U{http://cr.yp.to/proto/netstrings.txt} for the specification of
    netstrings. Every netstring starts with digits that specify the length
    of the data. This length specification is separated from the data by
    a colon. The data is terminated with a comma.

    Override L{stringReceived} to handle received netstrings. This
    method is called with the netstring payload as a single argument
    whenever a complete netstring is received.

    Security features:
        1. Messages are limited in size, useful if you don't want
           someone sending you a 500MB netstring (change C{self.MAX_LENGTH}
           to the maximum length you wish to accept).
        2. The connection is lost if an illegal message is received.

    @ivar MAX_LENGTH: Defines the maximum length of netstrings that can be
        received.
    @type MAX_LENGTH: C{int}

    @ivar _LENGTH: A pattern describing all strings that contain a netstring
        length specification. Examples for length specifications are C{b'0:'},
        C{b'12:'}, and C{b'179:'}. C{b'007:'} is not a valid length
        specification, since leading zeros are not allowed.
    @type _LENGTH: C{re.Match}

    @ivar _LENGTH_PREFIX: A pattern describing all strings that contain
        the first part of a netstring length specification (without the
        trailing comma). Examples are '0', '12', and '179'. '007' does not
        start a netstring length specification, since leading zeros are
        not allowed.
    @type _LENGTH_PREFIX: C{re.Match}

    @ivar _PARSING_LENGTH: Indicates that the C{NetstringReceiver} is in
        the state of parsing the length portion of a netstring.
    @type _PARSING_LENGTH: C{int}

    @ivar _PARSING_PAYLOAD: Indicates that the C{NetstringReceiver} is in
        the state of parsing the payload portion (data and trailing comma)
        of a netstring.
    @type _PARSING_PAYLOAD: C{int}

    @ivar brokenPeer: Indicates if the connection is still functional
    @type brokenPeer: C{int}

    @ivar _state: Indicates if the protocol is consuming the length portion
        (C{PARSING_LENGTH}) or the payload (C{PARSING_PAYLOAD}) of a netstring
    @type _state: C{int}

    @ivar _remainingData: Holds the chunk of data that has not yet been consumed
    @type _remainingData: C{string}

    @ivar _payload: Holds the payload portion of a netstring including the
        trailing comma
    @type _payload: C{BytesIO}

    @ivar _expectedPayloadSize: Holds the payload size plus one for the trailing
        comma.
    @type _expectedPayloadSize: C{int}
    """

    MAX_LENGTH = 99999
    _LENGTH = re.compile(br"(0|[1-9]\d*)(:)")

    _LENGTH_PREFIX = re.compile(br"(0|[1-9]\d*)$")

    # Some error information for NetstringParseError instances.
    _MISSING_LENGTH = (
        "The received netstring does not start with a " "length specification."
    )
    _OVERFLOW = (
        "The length specification of the received netstring "
        "cannot be represented in Python - it causes an "
        "OverflowError!"
    )
    _TOO_LONG = (
        "The received netstring is longer than the maximum %s "
        "specified by self.MAX_LENGTH"
    )
    _MISSING_COMMA = "The received netstring is not terminated by a comma."

    # The following constants are used for determining if the NetstringReceiver
    # is parsing the length portion of a netstring, or the payload.
    _PARSING_LENGTH, _PARSING_PAYLOAD = range(2)

    def makeConnection(self, transport):
        """
        Initializes the protocol.
        """
        protocol.Protocol.makeConnection(self, transport)
        self._remainingData = b""
        self._currentPayloadSize = 0
        self._payload = BytesIO()
        self._state = self._PARSING_LENGTH
        self._expectedPayloadSize = 0
        self.brokenPeer = 0

    def sendString(self, string):
        """
        Sends a netstring.

        Wraps up C{string} by adding length information and a
        trailing comma; writes the result to the transport.

        @param string: The string to send.  The necessary framing (length
            prefix, etc) will be added.
        @type string: C{bytes}
        """
        self.transport.write(_formatNetstring(string))

    def dataReceived(self, data):
        """
        Receives some characters of a netstring.

        Whenever a complete netstring is received, this method extracts
        its payload and calls L{stringReceived} to process it.

        @param data: A chunk of data representing a (possibly partial)
            netstring
        @type data: C{bytes}
        """
        self._remainingData += data
        while self._remainingData:
            try:
                self._consumeData()
            except IncompleteNetstring:
                break
            except NetstringParseError:
                self._handleParseError()
                break

    def stringReceived(self, string):
        """
        Override this for notification when each complete string is received.

        @param string: The complete string which was received with all
            framing (length prefix, etc) removed.
        @type string: C{bytes}

        @raise NotImplementedError: because the method has to be implemented
            by the child class.
        """
        raise NotImplementedError()

    def _maxLengthSize(self):
        """
        Calculate and return the string size of C{self.MAX_LENGTH}.

        @return: The size of the string representation for C{self.MAX_LENGTH}
        @rtype: C{float}
        """
        return math.ceil(math.log10(self.MAX_LENGTH)) + 1

    def _consumeData(self):
        """
        Consumes the content of C{self._remainingData}.

        @raise IncompleteNetstring: if C{self._remainingData} does not
            contain enough data to complete the current netstring.
        @raise NetstringParseError: if the received data do not
            form a valid netstring.
        """
        if self._state == self._PARSING_LENGTH:
            self._consumeLength()
            self._prepareForPayloadConsumption()
        if self._state == self._PARSING_PAYLOAD:
            self._consumePayload()

    def _consumeLength(self):
        """
        Consumes the length portion of C{self._remainingData}.

        @raise IncompleteNetstring: if C{self._remainingData} contains
            a partial length specification (digits without trailing
            comma).
        @raise NetstringParseError: if the received data do not form a valid
            netstring.
        """
        lengthMatch = self._LENGTH.match(self._remainingData)
        if not lengthMatch:
            self._checkPartialLengthSpecification()
            raise IncompleteNetstring()
        self._processLength(lengthMatch)

    def _checkPartialLengthSpecification(self):
        """
        Makes sure that the received data represents a valid number.

        Checks if C{self._remainingData} represents a number smaller or
        equal to C{self.MAX_LENGTH}.

        @raise NetstringParseError: if C{self._remainingData} is no
            number or is too big (checked by L{_extractLength}).
        """
        partialLengthMatch = self._LENGTH_PREFIX.match(self._remainingData)
        if not partialLengthMatch:
            raise NetstringParseError(self._MISSING_LENGTH)
        lengthSpecification = partialLengthMatch.group(1)
        self._extractLength(lengthSpecification)

    def _processLength(self, lengthMatch):
        """
        Processes the length definition of a netstring.

        Extracts and stores in C{self._expectedPayloadSize} the number
        representing the netstring size.  Removes the prefix
        representing the length specification from
        C{self._remainingData}.

        @raise NetstringParseError: if the received netstring does not
            start with a number or the number is bigger than
            C{self.MAX_LENGTH}.
        @param lengthMatch: A regular expression match object matching
            a netstring length specification
        @type lengthMatch: C{re.Match}
        """
        endOfNumber = lengthMatch.end(1)
        startOfData = lengthMatch.end(2)
        lengthString = self._remainingData[:endOfNumber]
        # Expect payload plus trailing comma:
        self._expectedPayloadSize = self._extractLength(lengthString) + 1
        self._remainingData = self._remainingData[startOfData:]

    def _extractLength(self, lengthAsString):
        """
        Attempts to extract the length information of a netstring.

        @raise NetstringParseError: if the number is bigger than
            C{self.MAX_LENGTH}.
        @param lengthAsString: A chunk of data starting with a length
            specification
        @type lengthAsString: C{bytes}
        @return: The length of the netstring
        @rtype: C{int}
        """
        self._checkStringSize(lengthAsString)
        length = int(lengthAsString)
        if length > self.MAX_LENGTH:
            raise NetstringParseError(self._TOO_LONG % (self.MAX_LENGTH,))
        return length

    def _checkStringSize(self, lengthAsString):
        """
        Checks the sanity of lengthAsString.

        Checks if the size of the length specification exceeds the
        size of the string representing self.MAX_LENGTH. If this is
        not the case, the number represented by lengthAsString is
        certainly bigger than self.MAX_LENGTH, and a
        NetstringParseError can be raised.

        This method should make sure that netstrings with extremely
        long length specifications are refused before even attempting
        to convert them to an integer (which might trigger a
        MemoryError).
        """
        if len(lengthAsString) > self._maxLengthSize():
            raise NetstringParseError(self._TOO_LONG % (self.MAX_LENGTH,))

    def _prepareForPayloadConsumption(self):
        """
        Sets up variables necessary for consuming the payload of a netstring.
        """
        self._state = self._PARSING_PAYLOAD
        self._currentPayloadSize = 0
        self._payload.seek(0)
        self._payload.truncate()

    def _consumePayload(self):
        """
        Consumes the payload portion of C{self._remainingData}.

        If the payload is complete, checks for the trailing comma and
        processes the payload. If not, raises an L{IncompleteNetstring}
        exception.

        @raise IncompleteNetstring: if the payload received so far
            contains fewer characters than expected.
        @raise NetstringParseError: if the payload does not end with a
        comma.
        """
        self._extractPayload()
        if self._currentPayloadSize < self._expectedPayloadSize:
            raise IncompleteNetstring()
        self._checkForTrailingComma()
        self._state = self._PARSING_LENGTH
        self._processPayload()

    def _extractPayload(self):
        """
        Extracts payload information from C{self._remainingData}.

        Splits C{self._remainingData} at the end of the netstring.  The
        first part becomes C{self._payload}, the second part is stored
        in C{self._remainingData}.

        If the netstring is not yet complete, the whole content of
        C{self._remainingData} is moved to C{self._payload}.
        """
        if self._payloadComplete():
            remainingPayloadSize = self._expectedPayloadSize - self._currentPayloadSize
            self._payload.write(self._remainingData[:remainingPayloadSize])
            self._remainingData = self._remainingData[remainingPayloadSize:]
            self._currentPayloadSize = self._expectedPayloadSize
        else:
            self._payload.write(self._remainingData)
            self._currentPayloadSize += len(self._remainingData)
            self._remainingData = b""

    def _payloadComplete(self):
        """
        Checks if enough data have been received to complete the netstring.

        @return: C{True} iff the received data contain at least as many
            characters as specified in the length section of the
            netstring
        @rtype: C{bool}
        """
        return (
            len(self._remainingData) + self._currentPayloadSize
            >= self._expectedPayloadSize
        )

    def _processPayload(self):
        """
        Processes the actual payload with L{stringReceived}.

        Strips C{self._payload} of the trailing comma and calls
        L{stringReceived} with the result.
        """
        self.stringReceived(self._payload.getvalue()[:-1])

    def _checkForTrailingComma(self):
        """
        Checks if the netstring has a trailing comma at the expected position.

        @raise NetstringParseError: if the last payload character is
            anything but a comma.
        """
        if self._payload.getvalue()[-1:] != b",":
            raise NetstringParseError(self._MISSING_COMMA)

    def _handleParseError(self):
        """
        Terminates the connection and sets the flag C{self.brokenPeer}.
        """
        self.transport.loseConnection()
        self.brokenPeer = 1


class LineOnlyReceiver(protocol.Protocol):
    """
    A protocol that receives only lines.

    This is purely a speed optimisation over LineReceiver, for the
    cases that raw mode is known to be unnecessary.

    @cvar delimiter: The line-ending delimiter to use. By default this is
                     C{b'\\r\\n'}.
    @cvar MAX_LENGTH: The maximum length of a line to allow (If a
                      sent line is longer than this, the connection is dropped).
                      Default is 16384.
    """

    _buffer = b""
    delimiter = b"\r\n"
    MAX_LENGTH = 16384

    def dataReceived(self, data):
        """
        Translates bytes into lines, and calls lineReceived.
        """
        lines = (self._buffer + data).split(self.delimiter)
        self._buffer = lines.pop(-1)
        for line in lines:
            if self.transport.disconnecting:
                # this is necessary because the transport may be told to lose
                # the connection by a line within a larger packet, and it is
                # important to disregard all the lines in that packet following
                # the one that told it to close.
                return
            if len(line) > self.MAX_LENGTH:
                return self.lineLengthExceeded(line)
            else:
                self.lineReceived(line)
        if len(self._buffer) > self.MAX_LENGTH:
            return self.lineLengthExceeded(self._buffer)

    def lineReceived(self, line):
        """
        Override this for when each line is received.

        @param line: The line which was received with the delimiter removed.
        @type line: C{bytes}
        """
        raise NotImplementedError

    def sendLine(self, line):
        """
        Sends a line to the other end of the connection.

        @param line: The line to send, not including the delimiter.
        @type line: C{bytes}
        """
        return self.transport.writeSequence((line, self.delimiter))

    def lineLengthExceeded(self, line):
        """
        Called when the maximum line length has been reached.
        Override if it needs to be dealt with in some special way.
        """
        return self.transport.loseConnection()


class _PauseableMixin:
    paused = False

    def pauseProducing(self):
        self.paused = True
        self.transport.pauseProducing()

    def resumeProducing(self):
        self.paused = False
        self.transport.resumeProducing()
        self.dataReceived(b"")

    def stopProducing(self):
        self.paused = True
        self.transport.stopProducing()


class LineReceiver(protocol.Protocol, _PauseableMixin):
    """
    A protocol that receives lines and/or raw data, depending on mode.

    In line mode, each line that's received becomes a callback to
    L{lineReceived}.  In raw data mode, each chunk of raw data becomes a
    callback to L{LineReceiver.rawDataReceived}.
    The L{setLineMode} and L{setRawMode} methods switch between the two modes.

    This is useful for line-oriented protocols such as IRC, HTTP, POP, etc.

    @cvar delimiter: The line-ending delimiter to use. By default this is
                     C{b'\\r\\n'}.
    @cvar MAX_LENGTH: The maximum length of a line to allow (If a
                      sent line is longer than this, the connection is dropped).
                      Default is 16384.
    """

    line_mode = 1
    _buffer = b""
    _busyReceiving = False
    delimiter = b"\r\n"
    MAX_LENGTH = 16384

    def clearLineBuffer(self):
        """
        Clear buffered data.

        @return: All of the cleared buffered data.
        @rtype: C{bytes}
        """
        b, self._buffer = self._buffer, b""
        return b

    def dataReceived(self, data):
        """
        Protocol.dataReceived.
        Translates bytes into lines, and calls lineReceived (or
        rawDataReceived, depending on mode.)
        """
        if self._busyReceiving:
            self._buffer += data
            return

        try:
            self._busyReceiving = True
            self._buffer += data
            while self._buffer and not self.paused:
                if self.line_mode:
                    try:
                        line, self._buffer = self._buffer.split(self.delimiter, 1)
                    except ValueError:
                        if len(self._buffer) >= (self.MAX_LENGTH + len(self.delimiter)):
                            line, self._buffer = self._buffer, b""
                            return self.lineLengthExceeded(line)
                        return
                    else:
                        lineLength = len(line)
                        if lineLength > self.MAX_LENGTH:
                            exceeded = line + self.delimiter + self._buffer
                            self._buffer = b""
                            return self.lineLengthExceeded(exceeded)
                        why = self.lineReceived(line)
                        if why or self.transport and self.transport.disconnecting:
                            return why
                else:
                    data = self._buffer
                    self._buffer = b""
                    why = self.rawDataReceived(data)
                    if why:
                        return why
        finally:
            self._busyReceiving = False

    def setLineMode(self, extra=b""):
        """
        Sets the line-mode of this receiver.

        If you are calling this from a rawDataReceived callback,
        you can pass in extra unhandled data, and that data will
        be parsed for lines.  Further data received will be sent
        to lineReceived rather than rawDataReceived.

        Do not pass extra data if calling this function from
        within a lineReceived callback.
        """
        self.line_mode = 1
        if extra:
            return self.dataReceived(extra)

    def setRawMode(self):
        """
        Sets the raw mode of this receiver.
        Further data received will be sent to rawDataReceived rather
        than lineReceived.
        """
        self.line_mode = 0

    def rawDataReceived(self, data):
        """
        Override this for when raw data is received.
        """
        raise NotImplementedError

    def lineReceived(self, line):
        """
        Override this for when each line is received.

        @param line: The line which was received with the delimiter removed.
        @type line: C{bytes}
        """
        raise NotImplementedError

    def sendLine(self, line):
        """
        Sends a line to the other end of the connection.

        @param line: The line to send, not including the delimiter.
        @type line: C{bytes}
        """
        return self.transport.write(line + self.delimiter)

    def lineLengthExceeded(self, line):
        """
        Called when the maximum line length has been reached.
        Override if it needs to be dealt with in some special way.

        The argument 'line' contains the remainder of the buffer, starting
        with (at least some part) of the line which is too long. This may
        be more than one line, or may be only the initial portion of the
        line.
        """
        return self.transport.loseConnection()


class StringTooLongError(AssertionError):
    """
    Raised when trying to send a string too long for a length prefixed
    protocol.
    """


class _RecvdCompatHack:
    """
    Emulates the to-be-deprecated C{IntNStringReceiver.recvd} attribute.

    The C{recvd} attribute was where the working buffer for buffering and
    parsing netstrings was kept.  It was updated each time new data arrived and
    each time some of that data was parsed and delivered to application code.
    The piecemeal updates to its string value were expensive and have been
    removed from C{IntNStringReceiver} in the normal case.  However, for
    applications directly reading this attribute, this descriptor restores that
    behavior.  It only copies the working buffer when necessary (ie, when
    accessed).  This avoids the cost for applications not using the data.

    This is a custom descriptor rather than a property, because we still need
    the default __set__ behavior in both new-style and old-style subclasses.
    """

    def __get__(self, oself, type=None):
        return oself._unprocessed[oself._compatibilityOffset :]


class IntNStringReceiver(protocol.Protocol, _PauseableMixin):
    """
    Generic class for length prefixed protocols.

    @ivar _unprocessed: bytes received, but not yet broken up into messages /
        sent to stringReceived.  _compatibilityOffset must be updated when this
        value is updated so that the C{recvd} attribute can be generated
        correctly.
    @type _unprocessed: C{bytes}

    @ivar structFormat: format used for struct packing/unpacking. Define it in
        subclass.
    @type structFormat: C{str}

    @ivar prefixLength: length of the prefix, in bytes. Define it in subclass,
        using C{struct.calcsize(structFormat)}
    @type prefixLength: C{int}

    @ivar _compatibilityOffset: the offset within C{_unprocessed} to the next
        message to be parsed. (used to generate the recvd attribute)
    @type _compatibilityOffset: C{int}
    """

    MAX_LENGTH = 99999
    _unprocessed = b""
    _compatibilityOffset = 0

    # Backwards compatibility support for applications which directly touch the
    # "internal" parse buffer.
    recvd = _RecvdCompatHack()

    def stringReceived(self, string):
        """
        Override this for notification when each complete string is received.

        @param string: The complete string which was received with all
            framing (length prefix, etc) removed.
        @type string: C{bytes}
        """
        raise NotImplementedError

    def lengthLimitExceeded(self, length):
        """
        Callback invoked when a length prefix greater than C{MAX_LENGTH} is
        received.  The default implementation disconnects the transport.
        Override this.

        @param length: The length prefix which was received.
        @type length: C{int}
        """
        self.transport.loseConnection()

    def dataReceived(self, data):
        """
        Convert int prefixed strings into calls to stringReceived.
        """
        # Try to minimize string copying (via slices) by keeping one buffer
        # containing all the data we have so far and a separate offset into that
        # buffer.
        alldata = self._unprocessed + data
        currentOffset = 0
        prefixLength = self.prefixLength
        fmt = self.structFormat
        self._unprocessed = alldata

        while len(alldata) >= (currentOffset + prefixLength) and not self.paused:
            messageStart = currentOffset + prefixLength
            (length,) = unpack(fmt, alldata[currentOffset:messageStart])
            if length > self.MAX_LENGTH:
                self._unprocessed = alldata
                self._compatibilityOffset = currentOffset
                self.lengthLimitExceeded(length)
                return
            messageEnd = messageStart + length
            if len(alldata) < messageEnd:
                break

            # Here we have to slice the working buffer so we can send just the
            # netstring into the stringReceived callback.
            packet = alldata[messageStart:messageEnd]
            currentOffset = messageEnd
            self._compatibilityOffset = currentOffset
            self.stringReceived(packet)

            # Check to see if the backwards compat "recvd" attribute got written
            # to by application code.  If so, drop the current data buffer and
            # switch to the new buffer given by that attribute's value.
            if "recvd" in self.__dict__:
                alldata = self.__dict__.pop("recvd")
                self._unprocessed = alldata
                self._compatibilityOffset = currentOffset = 0
                if alldata:
                    continue
                return

        # Slice off all the data that has been processed, avoiding holding onto
        # memory to store it, and update the compatibility attributes to reflect
        # that change.
        self._unprocessed = alldata[currentOffset:]
        self._compatibilityOffset = 0

    def sendString(self, string):
        """
        Send a prefixed string to the other end of the connection.

        @param string: The string to send.  The necessary framing (length
            prefix, etc) will be added.
        @type string: C{bytes}
        """
        if len(string) >= 2 ** (8 * self.prefixLength):
            raise StringTooLongError(
                "Try to send %s bytes whereas maximum is %s"
                % (len(string), 2 ** (8 * self.prefixLength))
            )
        self.transport.write(pack(self.structFormat, len(string)) + string)


class Int32StringReceiver(IntNStringReceiver):
    """
    A receiver for int32-prefixed strings.

    An int32 string is a string prefixed by 4 bytes, the 32-bit length of
    the string encoded in network byte order.

    This class publishes the same interface as NetstringReceiver.
    """

    structFormat = "!I"
    prefixLength = calcsize(structFormat)


class Int16StringReceiver(IntNStringReceiver):
    """
    A receiver for int16-prefixed strings.

    An int16 string is a string prefixed by 2 bytes, the 16-bit length of
    the string encoded in network byte order.

    This class publishes the same interface as NetstringReceiver.
    """

    structFormat = "!H"
    prefixLength = calcsize(structFormat)


class Int8StringReceiver(IntNStringReceiver):
    """
    A receiver for int8-prefixed strings.

    An int8 string is a string prefixed by 1 byte, the 8-bit length of
    the string.

    This class publishes the same interface as NetstringReceiver.
    """

    structFormat = "!B"
    prefixLength = calcsize(structFormat)


class StatefulStringProtocol:
    """
    A stateful string protocol.

    This is a mixin for string protocols (L{Int32StringReceiver},
    L{NetstringReceiver}) which translates L{stringReceived} into a callback
    (prefixed with C{'proto_'}) depending on state.

    The state C{'done'} is special; if a C{proto_*} method returns it, the
    connection will be closed immediately.

    @ivar state: Current state of the protocol. Defaults to C{'init'}.
    @type state: C{str}
    """

    state = "init"

    def stringReceived(self, string):
        """
        Choose a protocol phase function and call it.

        Call back to the appropriate protocol phase; this begins with
        the function C{proto_init} and moves on to C{proto_*} depending on
        what each C{proto_*} function returns.  (For example, if
        C{self.proto_init} returns 'foo', then C{self.proto_foo} will be the
        next function called when a protocol message is received.
        """
        try:
            pto = "proto_" + self.state
            statehandler = getattr(self, pto)
        except AttributeError:
            log.msg("callback", self.state, "not found")
        else:
            self.state = statehandler(string)
            if self.state == "done":
                self.transport.loseConnection()


@implementer(interfaces.IProducer)
class FileSender:
    """
    A producer that sends the contents of a file to a consumer.

    This is a helper for protocols that, at some point, will take a
    file-like object, read its contents, and write them out to the network,
    optionally performing some transformation on the bytes in between.
    """

    CHUNK_SIZE = 2 ** 14

    lastSent = ""
    deferred = None

    def beginFileTransfer(self, file, consumer, transform=None):
        """
        Begin transferring a file

        @type file: Any file-like object
        @param file: The file object to read data from

        @type consumer: Any implementor of IConsumer
        @param consumer: The object to write data to

        @param transform: A callable taking one string argument and returning
        the same.  All bytes read from the file are passed through this before
        being written to the consumer.

        @rtype: C{Deferred}
        @return: A deferred whose callback will be invoked when the file has
        been completely written to the consumer. The last byte written to the
        consumer is passed to the callback.
        """
        self.file = file
        self.consumer = consumer
        self.transform = transform

        self.deferred = deferred = defer.Deferred()
        self.consumer.registerProducer(self, False)
        return deferred

    def resumeProducing(self):
        chunk = ""
        if self.file:
            chunk = self.file.read(self.CHUNK_SIZE)
        if not chunk:
            self.file = None
            self.consumer.unregisterProducer()
            if self.deferred:
                self.deferred.callback(self.lastSent)
                self.deferred = None
            return

        if self.transform:
            chunk = self.transform(chunk)
        self.consumer.write(chunk)
        self.lastSent = chunk[-1:]

    def pauseProducing(self):
        pass

    def stopProducing(self):
        if self.deferred:
            self.deferred.errback(Exception("Consumer asked us to stop producing"))
            self.deferred = None
