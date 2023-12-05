# -*- test-case-name: twisted.conch.test.test_telnet -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Telnet protocol implementation.

@author: Jean-Paul Calderone
"""


import struct

from zope.interface import implementer

from twisted.internet import defer, interfaces as iinternet, protocol
from twisted.logger import Logger
from twisted.python.compat import iterbytes


def _chr(i: int) -> bytes:
    """Create a byte sequence of length 1.

    U{RFC 854<https://tools.ietf.org/html/rfc854>} specifies codes in decimal,
    but Python can only handle L{bytes} literals in octal or hexadecimal.
    This helper function bridges that gap.

    @param i: The value of the only byte in the sequence.
    """
    return bytes((i,))


MODE = _chr(1)
EDIT = 1
TRAPSIG = 2
MODE_ACK = 4
SOFT_TAB = 8
LIT_ECHO = 16

# Characters gleaned from the various (and conflicting) RFCs. Not all of these
# are correct.

NULL = _chr(0)  # No operation.
BEL = _chr(7)  # Produces an audible or visible signal (which does NOT move the
# print head).
BS = _chr(8)  # Moves the print head one character position towards the left
# margin.
HT = _chr(9)  # Moves the printer to the next horizontal tab stop. It remains
# unspecified how either party determines or establishes where such tab stops
# are located.
LF = _chr(10)  # Moves the printer to the next print line, keeping the same
# horizontal position.
VT = _chr(11)  # Moves the printer to the next vertical tab stop. It remains
# unspecified how either party determines or establishes where such tab stops
# are located.
FF = _chr(12)  # Moves the printer to the top of the next page, keeping the same
# horizontal position.
CR = _chr(13)  # Moves the printer to the left margin of the current line.

ECHO = _chr(1)  # User-to-Server:  Asks the server to send Echos of the
# transmitted data.
SGA = _chr(3)  # Suppress Go Ahead.  Go Ahead is silly and most modern servers
# should suppress it.
NAWS = _chr(31)  # Negotiate About Window Size.  Indicate that information about
# the size of the terminal can be communicated.
LINEMODE = _chr(34)  # Allow line buffering to be negotiated about.

EOR = _chr(239)  # End of Record (RFC 885)
SE = _chr(240)  # End of subnegotiation parameters.
NOP = _chr(241)  # No operation.
DM = _chr(242)  # "Data Mark": The data stream portion of a Synch. This should
# always be accompanied by a TCP Urgent notification.
BRK = _chr(243)  # NVT character Break.
IP = _chr(244)  # The function Interrupt Process.
AO = _chr(245)  # The function Abort Output
AYT = _chr(246)  # The function Are You There.
EC = _chr(247)  # The function Erase Character.
EL = _chr(248)  # The function Erase Line
GA = _chr(249)  # The Go Ahead signal.
SB = _chr(250)  # Indicates that what follows is subnegotiation of the indicated
# option.
WILL = _chr(251)  # Indicates the desire to begin performing, or confirmation
# that you are now performing, the indicated option.
WONT = _chr(252)  # Indicates the refusal to perform, or continue performing,
# the indicated option.
DO = _chr(253)  # Indicates the request that the other party perform, or
# confirmation that you are expecting the other party to perform, the indicated
# option.
DONT = _chr(254)  # Indicates the demand that the other party stop performing,
# or confirmation that you are no longer expecting the other party to perform,
# the indicated option.
IAC = _chr(255)  # Data Byte 255. Introduces a telnet command.

LINEMODE_MODE = _chr(1)
LINEMODE_EDIT = _chr(1)
LINEMODE_TRAPSIG = _chr(2)
LINEMODE_MODE_ACK = _chr(4)
LINEMODE_SOFT_TAB = _chr(8)
LINEMODE_LIT_ECHO = _chr(16)
LINEMODE_FORWARDMASK = _chr(2)
LINEMODE_SLC = _chr(3)
LINEMODE_SLC_SYNCH = _chr(1)
LINEMODE_SLC_BRK = _chr(2)
LINEMODE_SLC_IP = _chr(3)
LINEMODE_SLC_AO = _chr(4)
LINEMODE_SLC_AYT = _chr(5)
LINEMODE_SLC_EOR = _chr(6)
LINEMODE_SLC_ABORT = _chr(7)
LINEMODE_SLC_EOF = _chr(8)
LINEMODE_SLC_SUSP = _chr(9)
LINEMODE_SLC_EC = _chr(10)
LINEMODE_SLC_EL = _chr(11)

LINEMODE_SLC_EW = _chr(12)
LINEMODE_SLC_RP = _chr(13)
LINEMODE_SLC_LNEXT = _chr(14)
LINEMODE_SLC_XON = _chr(15)
LINEMODE_SLC_XOFF = _chr(16)
LINEMODE_SLC_FORW1 = _chr(17)
LINEMODE_SLC_FORW2 = _chr(18)
LINEMODE_SLC_MCL = _chr(19)
LINEMODE_SLC_MCR = _chr(20)
LINEMODE_SLC_MCWL = _chr(21)
LINEMODE_SLC_MCWR = _chr(22)
LINEMODE_SLC_MCBOL = _chr(23)
LINEMODE_SLC_MCEOL = _chr(24)
LINEMODE_SLC_INSRT = _chr(25)
LINEMODE_SLC_OVER = _chr(26)
LINEMODE_SLC_ECR = _chr(27)
LINEMODE_SLC_EWR = _chr(28)
LINEMODE_SLC_EBOL = _chr(29)
LINEMODE_SLC_EEOL = _chr(30)

LINEMODE_SLC_DEFAULT = _chr(3)
LINEMODE_SLC_VALUE = _chr(2)
LINEMODE_SLC_CANTCHANGE = _chr(1)
LINEMODE_SLC_NOSUPPORT = _chr(0)
LINEMODE_SLC_LEVELBITS = _chr(3)

LINEMODE_SLC_ACK = _chr(128)
LINEMODE_SLC_FLUSHIN = _chr(64)
LINEMODE_SLC_FLUSHOUT = _chr(32)
LINEMODE_EOF = _chr(236)
LINEMODE_SUSP = _chr(237)
LINEMODE_ABORT = _chr(238)


class ITelnetProtocol(iinternet.IProtocol):
    def unhandledCommand(command, argument):
        """
        A command was received but not understood.

        @param command: the command received.
        @type command: L{str}, a single character.
        @param argument: the argument to the received command.
        @type argument: L{str}, a single character, or None if the command that
            was unhandled does not provide an argument.
        """

    def unhandledSubnegotiation(command, data):
        """
        A subnegotiation command was received but not understood.

        @param command: the command being subnegotiated. That is, the first
            byte after the SB command.
        @type command: L{str}, a single character.
        @param data: all other bytes of the subneogation. That is, all but the
            first bytes between SB and SE, with IAC un-escaping applied.
        @type data: L{bytes}, each a single character
        """

    def enableLocal(option):
        """
        Enable the given option locally.

        This should enable the given option on this side of the
        telnet connection and return True.  If False is returned,
        the option will be treated as still disabled and the peer
        will be notified.

        @param option: the option to be enabled.
        @type option: L{bytes}, a single character.
        """

    def enableRemote(option):
        """
        Indicate whether the peer should be allowed to enable this option.

        Returns True if the peer should be allowed to enable this option,
        False otherwise.

        @param option: the option to be enabled.
        @type option: L{bytes}, a single character.
        """

    def disableLocal(option):
        """
        Disable the given option locally.

        Unlike enableLocal, this method cannot fail.  The option must be
        disabled.

        @param option: the option to be disabled.
        @type option: L{bytes}, a single character.
        """

    def disableRemote(option):
        """
        Indicate that the peer has disabled this option.

        @param option: the option to be disabled.
        @type option: L{bytes}, a single character.
        """


class ITelnetTransport(iinternet.ITransport):
    def do(option):
        """
        Indicate a desire for the peer to begin performing the given option.

        Returns a Deferred that fires with True when the peer begins performing
        the option, or fails with L{OptionRefused} when the peer refuses to
        perform it.  If the peer is already performing the given option, the
        Deferred will fail with L{AlreadyEnabled}.  If a negotiation regarding
        this option is already in progress, the Deferred will fail with
        L{AlreadyNegotiating}.

        Note: It is currently possible that this Deferred will never fire,
        if the peer never responds, or if the peer believes the option to
        already be enabled.
        """

    def dont(option):
        """
        Indicate a desire for the peer to cease performing the given option.

        Returns a Deferred that fires with True when the peer ceases performing
        the option.  If the peer is not performing the given option, the
        Deferred will fail with L{AlreadyDisabled}.  If negotiation regarding
        this option is already in progress, the Deferred will fail with
        L{AlreadyNegotiating}.

        Note: It is currently possible that this Deferred will never fire,
        if the peer never responds, or if the peer believes the option to
        already be disabled.
        """

    def will(option):
        """
        Indicate our willingness to begin performing this option locally.

        Returns a Deferred that fires with True when the peer agrees to allow us
        to begin performing this option, or fails with L{OptionRefused} if the
        peer refuses to allow us to begin performing it.  If the option is
        already enabled locally, the Deferred will fail with L{AlreadyEnabled}.
        If negotiation regarding this option is already in progress, the
        Deferred will fail with L{AlreadyNegotiating}.

        Note: It is currently possible that this Deferred will never fire,
        if the peer never responds, or if the peer believes the option to
        already be enabled.
        """

    def wont(option):
        """
        Indicate that we will stop performing the given option.

        Returns a Deferred that fires with True when the peer acknowledges
        we have stopped performing this option.  If the option is already
        disabled locally, the Deferred will fail with L{AlreadyDisabled}.
        If negotiation regarding this option is already in progress,
        the Deferred will fail with L{AlreadyNegotiating}.

        Note: It is currently possible that this Deferred will never fire,
        if the peer never responds, or if the peer believes the option to
        already be disabled.
        """

    def requestNegotiation(about, data):
        """
        Send a subnegotiation request.

        @param about: A byte indicating the feature being negotiated.
        @param data: Any number of L{bytes} containing specific information
        about the negotiation being requested.  No values in this string
        need to be escaped, as this function will escape any value which
        requires it.
        """


class TelnetError(Exception):
    pass


class NegotiationError(TelnetError):
    def __str__(self) -> str:
        return (
            self.__class__.__module__
            + "."
            + self.__class__.__name__
            + ":"
            + repr(self.args[0])
        )


class OptionRefused(NegotiationError):
    pass


class AlreadyEnabled(NegotiationError):
    pass


class AlreadyDisabled(NegotiationError):
    pass


class AlreadyNegotiating(NegotiationError):
    pass


@implementer(ITelnetProtocol)
class TelnetProtocol(protocol.Protocol):
    _log = Logger()

    def unhandledCommand(self, command, argument):
        pass

    def unhandledSubnegotiation(self, command, data):
        pass

    def enableLocal(self, option):
        pass

    def enableRemote(self, option):
        pass

    def disableLocal(self, option):
        pass

    def disableRemote(self, option):
        pass


class Telnet(protocol.Protocol):
    """
    @ivar commandMap: A mapping of bytes to callables.  When a
    telnet command is received, the command byte (the first byte
    after IAC) is looked up in this dictionary.  If a callable is
    found, it is invoked with the argument of the command, or None
    if the command takes no argument.  Values should be added to
    this dictionary if commands wish to be handled.  By default,
    only WILL, WONT, DO, and DONT are handled.  These should not
    be overridden, as this class handles them correctly and
    provides an API for interacting with them.

    @ivar negotiationMap: A mapping of bytes to callables.  When
    a subnegotiation command is received, the command byte (the
    first byte after SB) is looked up in this dictionary.  If
    a callable is found, it is invoked with the argument of the
    subnegotiation.  Values should be added to this dictionary if
    subnegotiations are to be handled.  By default, no values are
    handled.

    @ivar options: A mapping of option bytes to their current
    state.  This state is likely of little use to user code.
    Changes should not be made to it.

    @ivar state: A string indicating the current parse state.  It
    can take on the values "data", "escaped", "command", "newline",
    "subnegotiation", and "subnegotiation-escaped".  Changes
    should not be made to it.

    @ivar transport: This protocol's transport object.
    """

    # One of a lot of things
    state = "data"

    def __init__(self):
        self.options = {}
        self.negotiationMap = {}
        self.commandMap = {
            WILL: self.telnet_WILL,
            WONT: self.telnet_WONT,
            DO: self.telnet_DO,
            DONT: self.telnet_DONT,
        }

    def _write(self, data):
        self.transport.write(data)

    class _OptionState:
        """
        Represents the state of an option on both sides of a telnet
        connection.

        @ivar us: The state of the option on this side of the connection.

        @ivar him: The state of the option on the other side of the
            connection.
        """

        class _Perspective:
            """
            Represents the state of an option on side of the telnet
            connection.  Some options can be enabled on a particular side of
            the connection (RFC 1073 for example: only the client can have
            NAWS enabled).  Other options can be enabled on either or both
            sides (such as RFC 1372: each side can have its own flow control
            state).

            @ivar state: C{'yes'} or C{'no'} indicating whether or not this
                option is enabled on one side of the connection.

            @ivar negotiating: A boolean tracking whether negotiation about
                this option is in progress.

            @ivar onResult: When negotiation about this option has been
                initiated by this side of the connection, a L{Deferred}
                which will fire with the result of the negotiation.  L{None}
                at other times.
            """

            state = "no"
            negotiating = False
            onResult = None

            def __str__(self) -> str:
                return self.state + ("*" * self.negotiating)

        def __init__(self):
            self.us = self._Perspective()
            self.him = self._Perspective()

        def __repr__(self) -> str:
            return f"<_OptionState us={self.us} him={self.him}>"

    def getOptionState(self, opt):
        return self.options.setdefault(opt, self._OptionState())

    def _do(self, option):
        self._write(IAC + DO + option)

    def _dont(self, option):
        self._write(IAC + DONT + option)

    def _will(self, option):
        self._write(IAC + WILL + option)

    def _wont(self, option):
        self._write(IAC + WONT + option)

    def will(self, option):
        """
        Indicate our willingness to enable an option.
        """
        s = self.getOptionState(option)
        if s.us.negotiating or s.him.negotiating:
            return defer.fail(AlreadyNegotiating(option))
        elif s.us.state == "yes":
            return defer.fail(AlreadyEnabled(option))
        else:
            s.us.negotiating = True
            s.us.onResult = d = defer.Deferred()
            self._will(option)
            return d

    def wont(self, option):
        """
        Indicate we are not willing to enable an option.
        """
        s = self.getOptionState(option)
        if s.us.negotiating or s.him.negotiating:
            return defer.fail(AlreadyNegotiating(option))
        elif s.us.state == "no":
            return defer.fail(AlreadyDisabled(option))
        else:
            s.us.negotiating = True
            s.us.onResult = d = defer.Deferred()
            self._wont(option)
            return d

    def do(self, option):
        s = self.getOptionState(option)
        if s.us.negotiating or s.him.negotiating:
            return defer.fail(AlreadyNegotiating(option))
        elif s.him.state == "yes":
            return defer.fail(AlreadyEnabled(option))
        else:
            s.him.negotiating = True
            s.him.onResult = d = defer.Deferred()
            self._do(option)
            return d

    def dont(self, option):
        s = self.getOptionState(option)
        if s.us.negotiating or s.him.negotiating:
            return defer.fail(AlreadyNegotiating(option))
        elif s.him.state == "no":
            return defer.fail(AlreadyDisabled(option))
        else:
            s.him.negotiating = True
            s.him.onResult = d = defer.Deferred()
            self._dont(option)
            return d

    def requestNegotiation(self, about, data):
        """
        Send a negotiation message for the option C{about} with C{data} as the
        payload.

        @param data: the payload
        @type data: L{bytes}
        @see: L{ITelnetTransport.requestNegotiation}
        """
        data = data.replace(IAC, IAC * 2)
        self._write(IAC + SB + about + data + IAC + SE)

    def dataReceived(self, data):
        appDataBuffer = []

        for b in iterbytes(data):
            if self.state == "data":
                if b == IAC:
                    self.state = "escaped"
                elif b == b"\r":
                    self.state = "newline"
                else:
                    appDataBuffer.append(b)
            elif self.state == "escaped":
                if b == IAC:
                    appDataBuffer.append(b)
                    self.state = "data"
                elif b == SB:
                    self.state = "subnegotiation"
                    self.commands = []
                elif b in (EOR, NOP, DM, BRK, IP, AO, AYT, EC, EL, GA):
                    self.state = "data"
                    if appDataBuffer:
                        self.applicationDataReceived(b"".join(appDataBuffer))
                        del appDataBuffer[:]
                    self.commandReceived(b, None)
                elif b in (WILL, WONT, DO, DONT):
                    self.state = "command"
                    self.command = b
                else:
                    raise ValueError("Stumped", b)
            elif self.state == "command":
                self.state = "data"
                command = self.command
                del self.command
                if appDataBuffer:
                    self.applicationDataReceived(b"".join(appDataBuffer))
                    del appDataBuffer[:]
                self.commandReceived(command, b)
            elif self.state == "newline":
                self.state = "data"
                if b == b"\n":
                    appDataBuffer.append(b"\n")
                elif b == b"\0":
                    appDataBuffer.append(b"\r")
                elif b == IAC:
                    # IAC isn't really allowed after \r, according to the
                    # RFC, but handling it this way is less surprising than
                    # delivering the IAC to the app as application data.
                    # The purpose of the restriction is to allow terminals
                    # to unambiguously interpret the behavior of the CR
                    # after reading only one more byte.  CR LF is supposed
                    # to mean one thing (cursor to next line, first column),
                    # CR NUL another (cursor to first column).  Absent the
                    # NUL, it still makes sense to interpret this as CR and
                    # then apply all the usual interpretation to the IAC.
                    appDataBuffer.append(b"\r")
                    self.state = "escaped"
                else:
                    appDataBuffer.append(b"\r" + b)
            elif self.state == "subnegotiation":
                if b == IAC:
                    self.state = "subnegotiation-escaped"
                else:
                    self.commands.append(b)
            elif self.state == "subnegotiation-escaped":
                if b == SE:
                    self.state = "data"
                    commands = self.commands
                    del self.commands
                    if appDataBuffer:
                        self.applicationDataReceived(b"".join(appDataBuffer))
                        del appDataBuffer[:]
                    self.negotiate(commands)
                else:
                    self.state = "subnegotiation"
                    self.commands.append(b)
            else:
                raise ValueError("How'd you do this?")

        if appDataBuffer:
            self.applicationDataReceived(b"".join(appDataBuffer))

    def connectionLost(self, reason):
        for state in self.options.values():
            if state.us.onResult is not None:
                d = state.us.onResult
                state.us.onResult = None
                d.errback(reason)
            if state.him.onResult is not None:
                d = state.him.onResult
                state.him.onResult = None
                d.errback(reason)

    def applicationDataReceived(self, data):
        """
        Called with application-level data.
        """

    def unhandledCommand(self, command, argument):
        """
        Called for commands for which no handler is installed.
        """

    def commandReceived(self, command, argument):
        cmdFunc = self.commandMap.get(command)
        if cmdFunc is None:
            self.unhandledCommand(command, argument)
        else:
            cmdFunc(argument)

    def unhandledSubnegotiation(self, command, data):
        """
        Called for subnegotiations for which no handler is installed.
        """

    def negotiate(self, data):
        command, data = data[0], data[1:]
        cmdFunc = self.negotiationMap.get(command)
        if cmdFunc is None:
            self.unhandledSubnegotiation(command, data)
        else:
            cmdFunc(data)

    def telnet_WILL(self, option):
        s = self.getOptionState(option)
        self.willMap[s.him.state, s.him.negotiating](self, s, option)

    def will_no_false(self, state, option):
        # He is unilaterally offering to enable an option.
        if self.enableRemote(option):
            state.him.state = "yes"
            self._do(option)
        else:
            self._dont(option)

    def will_no_true(self, state, option):
        # Peer agreed to enable an option in response to our request.
        state.him.state = "yes"
        state.him.negotiating = False
        d = state.him.onResult
        state.him.onResult = None
        d.callback(True)
        assert self.enableRemote(
            option
        ), "enableRemote must return True in this context (for option {!r})".format(
            option
        )

    def will_yes_false(self, state, option):
        # He is unilaterally offering to enable an already-enabled option.
        # Ignore this.
        pass

    def will_yes_true(self, state, option):
        # This is a bogus state.  It is here for completeness.  It will
        # never be entered.
        assert (
            False
        ), "will_yes_true can never be entered, but was called with {!r}, {!r}".format(
            state,
            option,
        )

    willMap = {
        ("no", False): will_no_false,
        ("no", True): will_no_true,
        ("yes", False): will_yes_false,
        ("yes", True): will_yes_true,
    }

    def telnet_WONT(self, option):
        s = self.getOptionState(option)
        self.wontMap[s.him.state, s.him.negotiating](self, s, option)

    def wont_no_false(self, state, option):
        # He is unilaterally demanding that an already-disabled option be/remain disabled.
        # Ignore this (although we could record it and refuse subsequent enable attempts
        # from our side - he can always refuse them again though, so we won't)
        pass

    def wont_no_true(self, state, option):
        # Peer refused to enable an option in response to our request.
        state.him.negotiating = False
        d = state.him.onResult
        state.him.onResult = None
        d.errback(OptionRefused(option))

    def wont_yes_false(self, state, option):
        # Peer is unilaterally demanding that an option be disabled.
        state.him.state = "no"
        self.disableRemote(option)
        self._dont(option)

    def wont_yes_true(self, state, option):
        # Peer agreed to disable an option at our request.
        state.him.state = "no"
        state.him.negotiating = False
        d = state.him.onResult
        state.him.onResult = None
        d.callback(True)
        self.disableRemote(option)

    wontMap = {
        ("no", False): wont_no_false,
        ("no", True): wont_no_true,
        ("yes", False): wont_yes_false,
        ("yes", True): wont_yes_true,
    }

    def telnet_DO(self, option):
        s = self.getOptionState(option)
        self.doMap[s.us.state, s.us.negotiating](self, s, option)

    def do_no_false(self, state, option):
        # Peer is unilaterally requesting that we enable an option.
        if self.enableLocal(option):
            state.us.state = "yes"
            self._will(option)
        else:
            self._wont(option)

    def do_no_true(self, state, option):
        # Peer agreed to allow us to enable an option at our request.
        state.us.state = "yes"
        state.us.negotiating = False
        d = state.us.onResult
        state.us.onResult = None
        d.callback(True)
        self.enableLocal(option)

    def do_yes_false(self, state, option):
        # Peer is unilaterally requesting us to enable an already-enabled option.
        # Ignore this.
        pass

    def do_yes_true(self, state, option):
        # This is a bogus state.  It is here for completeness.  It will never be
        # entered.
        assert (
            False
        ), "do_yes_true can never be entered, but was called with {!r}, {!r}".format(
            state,
            option,
        )

    doMap = {
        ("no", False): do_no_false,
        ("no", True): do_no_true,
        ("yes", False): do_yes_false,
        ("yes", True): do_yes_true,
    }

    def telnet_DONT(self, option):
        s = self.getOptionState(option)
        self.dontMap[s.us.state, s.us.negotiating](self, s, option)

    def dont_no_false(self, state, option):
        # Peer is unilaterally demanding us to disable an already-disabled option.
        # Ignore this.
        pass

    def dont_no_true(self, state, option):
        # Offered option was refused.  Fail the Deferred returned by the
        # previous will() call.
        state.us.negotiating = False
        d = state.us.onResult
        state.us.onResult = None
        d.errback(OptionRefused(option))

    def dont_yes_false(self, state, option):
        # Peer is unilaterally demanding we disable an option.
        state.us.state = "no"
        self.disableLocal(option)
        self._wont(option)

    def dont_yes_true(self, state, option):
        # Peer acknowledged our notice that we will disable an option.
        state.us.state = "no"
        state.us.negotiating = False
        d = state.us.onResult
        state.us.onResult = None
        d.callback(True)
        self.disableLocal(option)

    dontMap = {
        ("no", False): dont_no_false,
        ("no", True): dont_no_true,
        ("yes", False): dont_yes_false,
        ("yes", True): dont_yes_true,
    }

    def enableLocal(self, option):
        """
        Reject all attempts to enable options.
        """
        return False

    def enableRemote(self, option):
        """
        Reject all attempts to enable options.
        """
        return False

    def disableLocal(self, option):
        """
        Signal a programming error by raising an exception.

        L{enableLocal} must return true for the given value of C{option} in
        order for this method to be called.  If a subclass of L{Telnet}
        overrides enableLocal to allow certain options to be enabled, it must
        also override disableLocal to disable those options.

        @raise NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            f"Don't know how to disable local telnet option {option!r}"
        )

    def disableRemote(self, option):
        """
        Signal a programming error by raising an exception.

        L{enableRemote} must return true for the given value of C{option} in
        order for this method to be called.  If a subclass of L{Telnet}
        overrides enableRemote to allow certain options to be enabled, it must
        also override disableRemote tto disable those options.

        @raise NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            f"Don't know how to disable remote telnet option {option!r}"
        )


class ProtocolTransportMixin:
    def write(self, data):
        self.transport.write(data.replace(b"\n", b"\r\n"))

    def writeSequence(self, seq):
        self.transport.writeSequence(seq)

    def loseConnection(self):
        self.transport.loseConnection()

    def getHost(self):
        return self.transport.getHost()

    def getPeer(self):
        return self.transport.getPeer()


class TelnetTransport(Telnet, ProtocolTransportMixin):
    """
    @ivar protocol: An instance of the protocol to which this
    transport is connected, or None before the connection is
    established and after it is lost.

    @ivar protocolFactory: A callable which returns protocol instances
    which provide L{ITelnetProtocol}.  This will be invoked when a
    connection is established.  It is passed *protocolArgs and
    **protocolKwArgs.

    @ivar protocolArgs: A tuple of additional arguments to
    pass to protocolFactory.

    @ivar protocolKwArgs: A dictionary of additional arguments
    to pass to protocolFactory.
    """

    disconnecting = False

    protocolFactory = None
    protocol = None

    def __init__(self, protocolFactory=None, *a, **kw):
        Telnet.__init__(self)
        if protocolFactory is not None:
            self.protocolFactory = protocolFactory
            self.protocolArgs = a
            self.protocolKwArgs = kw

    def connectionMade(self):
        if self.protocolFactory is not None:
            self.protocol = self.protocolFactory(
                *self.protocolArgs, **self.protocolKwArgs
            )
            assert ITelnetProtocol.providedBy(self.protocol)
            try:
                factory = self.factory
            except AttributeError:
                pass
            else:
                self.protocol.factory = factory
            self.protocol.makeConnection(self)

    def connectionLost(self, reason):
        Telnet.connectionLost(self, reason)
        if self.protocol is not None:
            try:
                self.protocol.connectionLost(reason)
            finally:
                del self.protocol

    def enableLocal(self, option):
        return self.protocol.enableLocal(option)

    def enableRemote(self, option):
        return self.protocol.enableRemote(option)

    def disableLocal(self, option):
        return self.protocol.disableLocal(option)

    def disableRemote(self, option):
        return self.protocol.disableRemote(option)

    def unhandledSubnegotiation(self, command, data):
        self.protocol.unhandledSubnegotiation(command, data)

    def unhandledCommand(self, command, argument):
        self.protocol.unhandledCommand(command, argument)

    def applicationDataReceived(self, data):
        self.protocol.dataReceived(data)

    def write(self, data):
        ProtocolTransportMixin.write(self, data.replace(b"\xff", b"\xff\xff"))


class TelnetBootstrapProtocol(TelnetProtocol, ProtocolTransportMixin):
    protocol = None

    def __init__(self, protocolFactory, *args, **kw):
        self.protocolFactory = protocolFactory
        self.protocolArgs = args
        self.protocolKwArgs = kw

    def connectionMade(self):
        self.transport.negotiationMap[NAWS] = self.telnet_NAWS
        self.transport.negotiationMap[LINEMODE] = self.telnet_LINEMODE

        for opt in (LINEMODE, NAWS, SGA):
            self.transport.do(opt).addErrback(
                lambda f: self._log.failure("Error do {opt!r}", f, opt=opt)
            )
        for opt in (ECHO,):
            self.transport.will(opt).addErrback(
                lambda f: self._log.failure("Error setting will {opt!r}", f, opt=opt)
            )

        self.protocol = self.protocolFactory(*self.protocolArgs, **self.protocolKwArgs)

        try:
            factory = self.factory
        except AttributeError:
            pass
        else:
            self.protocol.factory = factory

        self.protocol.makeConnection(self)

    def connectionLost(self, reason):
        if self.protocol is not None:
            try:
                self.protocol.connectionLost(reason)
            finally:
                del self.protocol

    def dataReceived(self, data):
        self.protocol.dataReceived(data)

    def enableLocal(self, opt):
        if opt == ECHO:
            return True
        elif opt == SGA:
            return True
        else:
            return False

    def enableRemote(self, opt):
        if opt == LINEMODE:
            self.transport.requestNegotiation(LINEMODE, MODE + LINEMODE_TRAPSIG)
            return True
        elif opt == NAWS:
            return True
        elif opt == SGA:
            return True
        else:
            return False

    def telnet_NAWS(self, data):
        # NAWS is client -> server *only*.  self.protocol will
        # therefore be an ITerminalTransport, the `.protocol'
        # attribute of which will be an ITerminalProtocol.  Maybe.
        # You know what, XXX TODO clean this up.
        if len(data) == 4:
            width, height = struct.unpack("!HH", b"".join(data))
            self.protocol.terminalProtocol.terminalSize(width, height)
        else:
            self._log.error("Wrong number of NAWS bytes: {nbytes}", nbytes=len(data))

    linemodeSubcommands = {LINEMODE_SLC: "SLC"}

    def telnet_LINEMODE(self, data):
        # linemodeSubcommand = data[0]
        # # XXX TODO: This should be enabled to parse linemode subnegotiation.
        # getattr(self, "linemode_" + self.linemodeSubcommands[linemodeSubcommand])(
        #     data[1:]
        # )
        pass

    def linemode_SLC(self, data):
        chunks = zip(*[iter(data)] * 3)
        for slcFunction, slcValue, slcWhat in chunks:
            # Later, we should parse stuff.
            "SLC", ord(slcFunction), ord(slcValue), ord(slcWhat)


from twisted.protocols import basic


class StatefulTelnetProtocol(basic.LineReceiver, TelnetProtocol):
    delimiter = b"\n"

    state = "Discard"

    def connectionLost(self, reason):
        basic.LineReceiver.connectionLost(self, reason)
        TelnetProtocol.connectionLost(self, reason)

    def lineReceived(self, line):
        oldState = self.state
        newState = getattr(self, "telnet_" + oldState)(line)
        if newState is not None:
            if self.state == oldState:
                self.state = newState
            else:
                self._log.warn("state changed and new state returned")

    def telnet_Discard(self, line):
        pass


from twisted.cred import credentials


class AuthenticatingTelnetProtocol(StatefulTelnetProtocol):
    """
    A protocol which prompts for credentials and attempts to authenticate them.

    Username and password prompts are given (the password is obscured).  When the
    information is collected, it is passed to a portal and an avatar implementing
    L{ITelnetProtocol} is requested.  If an avatar is returned, it connected to this
    protocol's transport, and this protocol's transport is connected to it.
    Otherwise, the user is re-prompted for credentials.
    """

    state = "User"
    protocol = None

    def __init__(self, portal):
        self.portal = portal

    def connectionMade(self):
        self.transport.write(b"Username: ")

    def connectionLost(self, reason):
        StatefulTelnetProtocol.connectionLost(self, reason)
        if self.protocol is not None:
            try:
                self.protocol.connectionLost(reason)
                self.logout()
            finally:
                del self.protocol, self.logout

    def telnet_User(self, line):
        self.username = line
        self.transport.will(ECHO)
        self.transport.write(b"Password: ")
        return "Password"

    def telnet_Password(self, line):
        username, password = self.username, line
        del self.username

        def login(ignored):
            creds = credentials.UsernamePassword(username, password)
            d = self.portal.login(creds, None, ITelnetProtocol)
            d.addCallback(self._cbLogin)
            d.addErrback(self._ebLogin)

        self.transport.wont(ECHO).addCallback(login)
        return "Discard"

    def _cbLogin(self, ial):
        interface, protocol, logout = ial
        assert interface is ITelnetProtocol
        self.protocol = protocol
        self.logout = logout
        self.state = "Command"

        protocol.makeConnection(self.transport)
        self.transport.protocol = protocol

    def _ebLogin(self, failure):
        self.transport.write(b"\nAuthentication failed\n")
        self.transport.write(b"Username: ")
        self.state = "User"


__all__ = [
    # Exceptions
    "TelnetError",
    "NegotiationError",
    "OptionRefused",
    "AlreadyNegotiating",
    "AlreadyEnabled",
    "AlreadyDisabled",
    # Interfaces
    "ITelnetProtocol",
    "ITelnetTransport",
    # Other stuff, protocols, etc.
    "Telnet",
    "TelnetProtocol",
    "TelnetTransport",
    "TelnetBootstrapProtocol",
]
