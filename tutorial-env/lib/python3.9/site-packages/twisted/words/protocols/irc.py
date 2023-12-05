# -*- test-case-name: twisted.words.test.test_irc -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Internet Relay Chat protocol for client and server.

Future Plans
============

The way the IRCClient class works here encourages people to implement
IRC clients by subclassing the ephemeral protocol class, and it tends
to end up with way more state than it should for an object which will
be destroyed as soon as the TCP transport drops.  Someone oughta do
something about that, ya know?

The DCC support needs to have more hooks for the client for it to be
able to ask the user things like "Do you want to accept this session?"
and "Transfer #2 is 67% done." and otherwise manage the DCC sessions.

Test coverage needs to be better.

@var MAX_COMMAND_LENGTH: The maximum length of a command, as defined by RFC
    2812 section 2.3.

@var attributes: Singleton instance of L{_CharacterAttributes}, used for
    constructing formatted text information.

@author: Kevin Turner

@see: RFC 1459: Internet Relay Chat Protocol
@see: RFC 2812: Internet Relay Chat: Client Protocol
@see: U{The Client-To-Client-Protocol
<http://www.irchelp.org/irchelp/rfc/ctcpspec.html>}
"""

import errno
import operator
import os
import random
import re
import shlex
import socket
import stat
import string
import struct
import sys
import textwrap
import time
import traceback
from functools import reduce
from os import path
from typing import Optional

from twisted.internet import protocol, reactor, task
from twisted.persisted import styles
from twisted.protocols import basic
from twisted.python import _textattributes, log, reflect

NUL = chr(0)
CR = chr(0o15)
NL = chr(0o12)
LF = NL
SPC = chr(0o40)

# This includes the CRLF terminator characters.
MAX_COMMAND_LENGTH = 512

CHANNEL_PREFIXES = "&#!+"


class IRCBadMessage(Exception):
    pass


class IRCPasswordMismatch(Exception):
    pass


class IRCBadModes(ValueError):
    """
    A malformed mode was encountered while attempting to parse a mode string.
    """


def parsemsg(s):
    """
    Breaks a message from an IRC server into its prefix, command, and
    arguments.

    @param s: The message to break.
    @type s: L{bytes}

    @return: A tuple of (prefix, command, args).
    @rtype: L{tuple}
    """
    prefix = ""
    trailing = []
    if not s:
        raise IRCBadMessage("Empty line.")
    if s[0:1] == ":":
        prefix, s = s[1:].split(" ", 1)
    if s.find(" :") != -1:
        s, trailing = s.split(" :", 1)
        args = s.split()
        args.append(trailing)
    else:
        args = s.split()
    command = args.pop(0)
    return prefix, command, args


def split(str, length=80):
    """
    Split a string into multiple lines.

    Whitespace near C{str[length]} will be preferred as a breaking point.
    C{"\\n"} will also be used as a breaking point.

    @param str: The string to split.
    @type str: C{str}

    @param length: The maximum length which will be allowed for any string in
        the result.
    @type length: C{int}

    @return: C{list} of C{str}
    """
    return [chunk for line in str.split("\n") for chunk in textwrap.wrap(line, length)]


def _intOrDefault(value, default=None):
    """
    Convert a value to an integer if possible.

    @rtype: C{int} or type of L{default}
    @return: An integer when C{value} can be converted to an integer,
        otherwise return C{default}
    """
    if value:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return default


class UnhandledCommand(RuntimeError):
    """
    A command dispatcher could not locate an appropriate command handler.
    """


class _CommandDispatcherMixin:
    """
    Dispatch commands to handlers based on their name.

    Command handler names should be of the form C{prefix_commandName},
    where C{prefix} is the value specified by L{prefix}, and must
    accept the parameters as given to L{dispatch}.

    Attempting to mix this in more than once for a single class will cause
    strange behaviour, due to L{prefix} being overwritten.

    @type prefix: C{str}
    @ivar prefix: Command handler prefix, used to locate handler attributes
    """

    prefix: Optional[str] = None

    def dispatch(self, commandName, *args):
        """
        Perform actual command dispatch.
        """

        def _getMethodName(command):
            return f"{self.prefix}_{command}"

        def _getMethod(name):
            return getattr(self, _getMethodName(name), None)

        method = _getMethod(commandName)
        if method is not None:
            return method(*args)

        method = _getMethod("unknown")
        if method is None:
            raise UnhandledCommand(
                f"No handler for {_getMethodName(commandName)!r} could be found"
            )
        return method(commandName, *args)


def parseModes(modes, params, paramModes=("", "")):
    """
    Parse an IRC mode string.

    The mode string is parsed into two lists of mode changes (added and
    removed), with each mode change represented as C{(mode, param)} where mode
    is the mode character, and param is the parameter passed for that mode, or
    L{None} if no parameter is required.

    @type modes: C{str}
    @param modes: Modes string to parse.

    @type params: C{list}
    @param params: Parameters specified along with L{modes}.

    @type paramModes: C{(str, str)}
    @param paramModes: A pair of strings (C{(add, remove)}) that indicate which modes take
        parameters when added or removed.

    @returns: Two lists of mode changes, one for modes added and the other for
        modes removed respectively, mode changes in each list are represented as
        C{(mode, param)}.
    """
    if len(modes) == 0:
        raise IRCBadModes("Empty mode string")

    if modes[0] not in "+-":
        raise IRCBadModes(f"Malformed modes string: {modes!r}")

    changes = ([], [])

    direction = None
    count = -1
    for ch in modes:
        if ch in "+-":
            if count == 0:
                raise IRCBadModes(f"Empty mode sequence: {modes!r}")
            direction = "+-".index(ch)
            count = 0
        else:
            param = None
            if ch in paramModes[direction]:
                try:
                    param = params.pop(0)
                except IndexError:
                    raise IRCBadModes(f"Not enough parameters: {ch!r}")
            changes[direction].append((ch, param))
            count += 1

    if len(params) > 0:
        raise IRCBadModes(f"Too many parameters: {modes!r} {params!r}")

    if count == 0:
        raise IRCBadModes(f"Empty mode sequence: {modes!r}")

    return changes


class IRC(protocol.Protocol):
    """
    Internet Relay Chat server protocol.
    """

    buffer = ""
    hostname = None

    encoding: Optional[str] = None

    def connectionMade(self):
        self.channels = []
        if self.hostname is None:
            self.hostname = socket.getfqdn()

    def sendLine(self, line):
        line = line + CR + LF
        if isinstance(line, str):
            useEncoding = self.encoding if self.encoding else "utf-8"
            line = line.encode(useEncoding)
        self.transport.write(line)

    def sendMessage(self, command, *parameter_list, **prefix):
        """
        Send a line formatted as an IRC message.

        First argument is the command, all subsequent arguments are parameters
        to that command.  If a prefix is desired, it may be specified with the
        keyword argument 'prefix'.

        The L{sendCommand} method is generally preferred over this one.
        Notably, this method does not support sending message tags, while the
        L{sendCommand} method does.
        """
        if not command:
            raise ValueError("IRC message requires a command.")

        if " " in command or command[0] == ":":
            # Not the ONLY way to screw up, but provides a little
            # sanity checking to catch likely dumb mistakes.
            raise ValueError(
                "Somebody screwed up, 'cuz this doesn't"
                " look like a command to me: %s" % command
            )

        line = " ".join([command] + list(parameter_list))
        if "prefix" in prefix:
            line = ":{} {}".format(prefix["prefix"], line)
        self.sendLine(line)

        if len(parameter_list) > 15:
            log.msg(
                "Message has %d parameters (RFC allows 15):\n%s"
                % (len(parameter_list), line)
            )

    def sendCommand(self, command, parameters, prefix=None, tags=None):
        """
        Send to the remote peer a line formatted as an IRC message.

        @param command: The command or numeric to send.
        @type command: L{unicode}

        @param parameters: The parameters to send with the command.
        @type parameters: A L{tuple} or L{list} of L{unicode} parameters

        @param prefix: The prefix to send with the command.  If not
            given, no prefix is sent.
        @type prefix: L{unicode}

        @param tags: A dict of message tags.  If not given, no message
            tags are sent.  The dict key should be the name of the tag
            to send as a string; the value should be the unescaped value
            to send with the tag, or either None or "" if no value is to
            be sent with the tag.
        @type tags: L{dict} of tags (L{unicode}) => values (L{unicode})
        @see: U{https://ircv3.net/specs/core/message-tags-3.2.html}
        """
        if not command:
            raise ValueError("IRC message requires a command.")

        if " " in command or command[0] == ":":
            # Not the ONLY way to screw up, but provides a little
            # sanity checking to catch likely dumb mistakes.
            raise ValueError(f'Invalid command: "{command}"')

        if tags is None:
            tags = {}

        line = " ".join([command] + list(parameters))
        if prefix:
            line = f":{prefix} {line}"
        if tags:
            tagStr = self._stringTags(tags)
            line = f"@{tagStr} {line}"
        self.sendLine(line)

        if len(parameters) > 15:
            log.msg(
                "Message has %d parameters (RFC allows 15):\n%s"
                % (len(parameters), line)
            )

    def _stringTags(self, tags):
        """
        Converts a tag dictionary to a string.

        @param tags: The tag dict passed to sendMsg.

        @rtype: L{unicode}
        @return: IRCv3-format tag string
        """
        self._validateTags(tags)
        tagStrings = []
        for tag, value in tags.items():
            if value:
                tagStrings.append(f"{tag}={self._escapeTagValue(value)}")
            else:
                tagStrings.append(tag)
        return ";".join(tagStrings)

    def _validateTags(self, tags):
        """
        Checks the tag dict for errors and raises L{ValueError} if an
        error is found.

        @param tags: The tag dict passed to sendMsg.
        """
        for tag, value in tags.items():
            if not tag:
                raise ValueError("A tag name is required.")
            for char in tag:
                if not char.isalnum() and char not in ("-", "/", "."):
                    raise ValueError("Tag contains invalid characters.")

    def _escapeTagValue(self, value):
        """
        Escape the given tag value according to U{escaping rules in IRCv3
        <https://ircv3.net/specs/core/message-tags-3.2.html>}.

        @param value: The string value to escape.
        @type value: L{str}

        @return: The escaped string for sending as a message value
        @rtype: L{str}
        """
        return (
            value.replace("\\", "\\\\")
            .replace(";", "\\:")
            .replace(" ", "\\s")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
        )

    def dataReceived(self, data):
        """
        This hack is to support mIRC, which sends LF only, even though the RFC
        says CRLF.  (Also, the flexibility of LineReceiver to turn "line mode"
        on and off was not required.)
        """
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        lines = (self.buffer + data).split(LF)
        # Put the (possibly empty) element after the last LF back in the
        # buffer
        self.buffer = lines.pop()

        for line in lines:
            if len(line) <= 2:
                # This is a blank line, at best.
                continue
            if line[-1] == CR:
                line = line[:-1]
            prefix, command, params = parsemsg(line)
            # mIRC is a big pile of doo-doo
            command = command.upper()
            # DEBUG: log.msg( "%s %s %s" % (prefix, command, params))

            self.handleCommand(command, prefix, params)

    def handleCommand(self, command, prefix, params):
        """
        Determine the function to call for the given command and call it with
        the given arguments.

        @param command: The IRC command to determine the function for.
        @type command: L{bytes}

        @param prefix: The prefix of the IRC message (as returned by
            L{parsemsg}).
        @type prefix: L{bytes}

        @param params: A list of parameters to call the function with.
        @type params: L{list}
        """
        method = getattr(self, "irc_%s" % command, None)
        try:
            if method is not None:
                method(prefix, params)
            else:
                self.irc_unknown(prefix, command, params)
        except BaseException:
            log.deferr()

    def irc_unknown(self, prefix, command, params):
        """
        Called by L{handleCommand} on a command that doesn't have a defined
        handler. Subclasses should override this method.
        """
        raise NotImplementedError(command, prefix, params)

    # Helper methods
    def privmsg(self, sender, recip, message):
        """
        Send a message to a channel or user

        @type sender: C{str} or C{unicode}
        @param sender: Who is sending this message.  Should be of the form
            username!ident@hostmask (unless you know better!).

        @type recip: C{str} or C{unicode}
        @param recip: The recipient of this message.  If a channel, it must
            start with a channel prefix.

        @type message: C{str} or C{unicode}
        @param message: The message being sent.
        """
        self.sendCommand("PRIVMSG", (recip, f":{lowQuote(message)}"), sender)

    def notice(self, sender, recip, message):
        """
        Send a "notice" to a channel or user.

        Notices differ from privmsgs in that the RFC claims they are different.
        Robots are supposed to send notices and not respond to them.  Clients
        typically display notices differently from privmsgs.

        @type sender: C{str} or C{unicode}
        @param sender: Who is sending this message.  Should be of the form
            username!ident@hostmask (unless you know better!).

        @type recip: C{str} or C{unicode}
        @param recip: The recipient of this message.  If a channel, it must
            start with a channel prefix.

        @type message: C{str} or C{unicode}
        @param message: The message being sent.
        """
        self.sendCommand("NOTICE", (recip, f":{message}"), sender)

    def action(self, sender, recip, message):
        """
        Send an action to a channel or user.

        @type sender: C{str} or C{unicode}
        @param sender: Who is sending this message.  Should be of the form
            username!ident@hostmask (unless you know better!).

        @type recip: C{str} or C{unicode}
        @param recip: The recipient of this message.  If a channel, it must
            start with a channel prefix.

        @type message: C{str} or C{unicode}
        @param message: The action being sent.
        """
        self.sendLine(f":{sender} ACTION {recip} :{message}")

    def topic(self, user, channel, topic, author=None):
        """
        Send the topic to a user.

        @type user: C{str} or C{unicode}
        @param user: The user receiving the topic.  Only their nickname, not
            the full hostmask.

        @type channel: C{str} or C{unicode}
        @param channel: The channel for which this is the topic.

        @type topic: C{str} or C{unicode} or L{None}
        @param topic: The topic string, unquoted, or None if there is no topic.

        @type author: C{str} or C{unicode}
        @param author: If the topic is being changed, the full username and
            hostmask of the person changing it.
        """
        if author is None:
            if topic is None:
                self.sendLine(
                    ":%s %s %s %s :%s"
                    % (self.hostname, RPL_NOTOPIC, user, channel, "No topic is set.")
                )
            else:
                self.sendLine(
                    ":%s %s %s %s :%s"
                    % (self.hostname, RPL_TOPIC, user, channel, lowQuote(topic))
                )
        else:
            self.sendLine(f":{author} TOPIC {channel} :{lowQuote(topic)}")

    def topicAuthor(self, user, channel, author, date):
        """
        Send the author of and time at which a topic was set for the given
        channel.

        This sends a 333 reply message, which is not part of the IRC RFC.

        @type user: C{str} or C{unicode}
        @param user: The user receiving the topic.  Only their nickname, not
            the full hostmask.

        @type channel: C{str} or C{unicode}
        @param channel: The channel for which this information is relevant.

        @type author: C{str} or C{unicode}
        @param author: The nickname (without hostmask) of the user who last set
            the topic.

        @type date: C{int}
        @param date: A POSIX timestamp (number of seconds since the epoch) at
            which the topic was last set.
        """
        self.sendLine(
            ":%s %d %s %s %s %d" % (self.hostname, 333, user, channel, author, date)
        )

    def names(self, user, channel, names):
        """
        Send the names of a channel's participants to a user.

        @type user: C{str} or C{unicode}
        @param user: The user receiving the name list.  Only their nickname,
            not the full hostmask.

        @type channel: C{str} or C{unicode}
        @param channel: The channel for which this is the namelist.

        @type names: C{list} of C{str} or C{unicode}
        @param names: The names to send.
        """
        # XXX If unicode is given, these limits are not quite correct
        prefixLength = len(channel) + len(user) + 10
        namesLength = 512 - prefixLength

        L = []
        count = 0
        for n in names:
            if count + len(n) + 1 > namesLength:
                self.sendLine(
                    ":%s %s %s = %s :%s"
                    % (self.hostname, RPL_NAMREPLY, user, channel, " ".join(L))
                )
                L = [n]
                count = len(n)
            else:
                L.append(n)
                count += len(n) + 1
        if L:
            self.sendLine(
                ":%s %s %s = %s :%s"
                % (self.hostname, RPL_NAMREPLY, user, channel, " ".join(L))
            )
        self.sendLine(
            ":%s %s %s %s :End of /NAMES list"
            % (self.hostname, RPL_ENDOFNAMES, user, channel)
        )

    def who(self, user, channel, memberInfo):
        """
        Send a list of users participating in a channel.

        @type user: C{str} or C{unicode}
        @param user: The user receiving this member information.  Only their
            nickname, not the full hostmask.

        @type channel: C{str} or C{unicode}
        @param channel: The channel for which this is the member information.

        @type memberInfo: C{list} of C{tuples}
        @param memberInfo: For each member of the given channel, a 7-tuple
            containing their username, their hostmask, the server to which they
            are connected, their nickname, the letter "H" or "G" (standing for
            "Here" or "Gone"), the hopcount from C{user} to this member, and
            this member's real name.
        """
        for info in memberInfo:
            (username, hostmask, server, nickname, flag, hops, realName) = info
            assert flag in ("H", "G")
            self.sendLine(
                ":%s %s %s %s %s %s %s %s %s :%d %s"
                % (
                    self.hostname,
                    RPL_WHOREPLY,
                    user,
                    channel,
                    username,
                    hostmask,
                    server,
                    nickname,
                    flag,
                    hops,
                    realName,
                )
            )

        self.sendLine(
            ":%s %s %s %s :End of /WHO list."
            % (self.hostname, RPL_ENDOFWHO, user, channel)
        )

    def whois(
        self,
        user,
        nick,
        username,
        hostname,
        realName,
        server,
        serverInfo,
        oper,
        idle,
        signOn,
        channels,
    ):
        """
        Send information about the state of a particular user.

        @type user: C{str} or C{unicode}
        @param user: The user receiving this information.  Only their nickname,
            not the full hostmask.

        @type nick: C{str} or C{unicode}
        @param nick: The nickname of the user this information describes.

        @type username: C{str} or C{unicode}
        @param username: The user's username (eg, ident response)

        @type hostname: C{str}
        @param hostname: The user's hostmask

        @type realName: C{str} or C{unicode}
        @param realName: The user's real name

        @type server: C{str} or C{unicode}
        @param server: The name of the server to which the user is connected

        @type serverInfo: C{str} or C{unicode}
        @param serverInfo: A descriptive string about that server

        @type oper: C{bool}
        @param oper: Indicates whether the user is an IRC operator

        @type idle: C{int}
        @param idle: The number of seconds since the user last sent a message

        @type signOn: C{int}
        @param signOn: A POSIX timestamp (number of seconds since the epoch)
            indicating the time the user signed on

        @type channels: C{list} of C{str} or C{unicode}
        @param channels: A list of the channels which the user is participating in
        """
        self.sendLine(
            ":%s %s %s %s %s %s * :%s"
            % (self.hostname, RPL_WHOISUSER, user, nick, username, hostname, realName)
        )
        self.sendLine(
            ":%s %s %s %s %s :%s"
            % (self.hostname, RPL_WHOISSERVER, user, nick, server, serverInfo)
        )
        if oper:
            self.sendLine(
                ":%s %s %s %s :is an IRC operator"
                % (self.hostname, RPL_WHOISOPERATOR, user, nick)
            )
        self.sendLine(
            ":%s %s %s %s %d %d :seconds idle, signon time"
            % (self.hostname, RPL_WHOISIDLE, user, nick, idle, signOn)
        )
        self.sendLine(
            ":%s %s %s %s :%s"
            % (self.hostname, RPL_WHOISCHANNELS, user, nick, " ".join(channels))
        )
        self.sendLine(
            ":%s %s %s %s :End of WHOIS list."
            % (self.hostname, RPL_ENDOFWHOIS, user, nick)
        )

    def join(self, who, where):
        """
        Send a join message.

        @type who: C{str} or C{unicode}
        @param who: The name of the user joining.  Should be of the form
            username!ident@hostmask (unless you know better!).

        @type where: C{str} or C{unicode}
        @param where: The channel the user is joining.
        """
        self.sendLine(f":{who} JOIN {where}")

    def part(self, who, where, reason=None):
        """
        Send a part message.

        @type who: C{str} or C{unicode}
        @param who: The name of the user joining.  Should be of the form
            username!ident@hostmask (unless you know better!).

        @type where: C{str} or C{unicode}
        @param where: The channel the user is joining.

        @type reason: C{str} or C{unicode}
        @param reason: A string describing the misery which caused this poor
            soul to depart.
        """
        if reason:
            self.sendLine(f":{who} PART {where} :{reason}")
        else:
            self.sendLine(f":{who} PART {where}")

    def channelMode(self, user, channel, mode, *args):
        """
        Send information about the mode of a channel.

        @type user: C{str} or C{unicode}
        @param user: The user receiving the name list.  Only their nickname,
            not the full hostmask.

        @type channel: C{str} or C{unicode}
        @param channel: The channel for which this is the namelist.

        @type mode: C{str}
        @param mode: A string describing this channel's modes.

        @param args: Any additional arguments required by the modes.
        """
        self.sendLine(
            ":%s %s %s %s %s %s"
            % (self.hostname, RPL_CHANNELMODEIS, user, channel, mode, " ".join(args))
        )


class ServerSupportedFeatures(_CommandDispatcherMixin):
    """
    Handle ISUPPORT messages.

    Feature names match those in the ISUPPORT RFC draft identically.

    Information regarding the specifics of ISUPPORT was gleaned from
    <http://www.irc.org/tech_docs/draft-brocklesby-irc-isupport-03.txt>.
    """

    prefix = "isupport"

    def __init__(self):
        self._features = {
            "CHANNELLEN": 200,
            "CHANTYPES": tuple("#&"),
            "MODES": 3,
            "NICKLEN": 9,
            "PREFIX": self._parsePrefixParam("(ovh)@+%"),
            # The ISUPPORT draft explicitly says that there is no default for
            # CHANMODES, but we're defaulting it here to handle the case where
            # the IRC server doesn't send us any ISUPPORT information, since
            # IRCClient.getChannelModeParams relies on this value.
            "CHANMODES": self._parseChanModesParam(["b", "", "lk", ""]),
        }

    @classmethod
    def _splitParamArgs(cls, params, valueProcessor=None):
        """
        Split ISUPPORT parameter arguments.

        Values can optionally be processed by C{valueProcessor}.

        For example::

            >>> ServerSupportedFeatures._splitParamArgs(['A:1', 'B:2'])
            (('A', '1'), ('B', '2'))

        @type params: C{iterable} of C{str}

        @type valueProcessor: C{callable} taking {str}
        @param valueProcessor: Callable to process argument values, or L{None}
            to perform no processing

        @rtype: C{list} of C{(str, object)}
        @return: Sequence of C{(name, processedValue)}
        """
        if valueProcessor is None:
            valueProcessor = lambda x: x

        def _parse():
            for param in params:
                if ":" not in param:
                    param += ":"
                a, b = param.split(":", 1)
                yield a, valueProcessor(b)

        return list(_parse())

    @classmethod
    def _unescapeParamValue(cls, value):
        """
        Unescape an ISUPPORT parameter.

        The only form of supported escape is C{\\xHH}, where HH must be a valid
        2-digit hexadecimal number.

        @rtype: C{str}
        """

        def _unescape():
            parts = value.split("\\x")
            # The first part can never be preceded by the escape.
            yield parts.pop(0)
            for s in parts:
                octet, rest = s[:2], s[2:]
                try:
                    octet = int(octet, 16)
                except ValueError:
                    raise ValueError(f"Invalid hex octet: {octet!r}")
                yield chr(octet) + rest

        if "\\x" not in value:
            return value
        return "".join(_unescape())

    @classmethod
    def _splitParam(cls, param):
        """
        Split an ISUPPORT parameter.

        @type param: C{str}

        @rtype: C{(str, list)}
        @return: C{(key, arguments)}
        """
        if "=" not in param:
            param += "="
        key, value = param.split("=", 1)
        return key, [cls._unescapeParamValue(v) for v in value.split(",")]

    @classmethod
    def _parsePrefixParam(cls, prefix):
        """
        Parse the ISUPPORT "PREFIX" parameter.

        The order in which the parameter arguments appear is significant, the
        earlier a mode appears the more privileges it gives.

        @rtype: C{dict} mapping C{str} to C{(str, int)}
        @return: A dictionary mapping a mode character to a two-tuple of
            C({symbol, priority)}, the lower a priority (the lowest being
            C{0}) the more privileges it gives
        """
        if not prefix:
            return None
        if prefix[0] != "(" and ")" not in prefix:
            raise ValueError("Malformed PREFIX parameter")
        modes, symbols = prefix.split(")", 1)
        symbols = zip(symbols, range(len(symbols)))
        modes = modes[1:]
        return dict(zip(modes, symbols))

    @classmethod
    def _parseChanModesParam(self, params):
        """
        Parse the ISUPPORT "CHANMODES" parameter.

        See L{isupport_CHANMODES} for a detailed explanation of this parameter.
        """
        names = ("addressModes", "param", "setParam", "noParam")
        if len(params) > len(names):
            raise ValueError(
                "Expecting a maximum of %d channel mode parameters, got %d"
                % (len(names), len(params))
            )
        items = map(lambda key, value: (key, value or ""), names, params)
        return dict(items)

    def getFeature(self, feature, default=None):
        """
        Get a server supported feature's value.

        A feature with the value L{None} is equivalent to the feature being
        unsupported.

        @type feature: C{str}
        @param feature: Feature name

        @type default: C{object}
        @param default: The value to default to, assuming that C{feature}
            is not supported

        @return: Feature value
        """
        return self._features.get(feature, default)

    def hasFeature(self, feature):
        """
        Determine whether a feature is supported or not.

        @rtype: C{bool}
        """
        return self.getFeature(feature) is not None

    def parse(self, params):
        """
        Parse ISUPPORT parameters.

        If an unknown parameter is encountered, it is simply added to the
        dictionary, keyed by its name, as a tuple of the parameters provided.

        @type params: C{iterable} of C{str}
        @param params: Iterable of ISUPPORT parameters to parse
        """
        for param in params:
            key, value = self._splitParam(param)
            if key.startswith("-"):
                self._features.pop(key[1:], None)
            else:
                self._features[key] = self.dispatch(key, value)

    def isupport_unknown(self, command, params):
        """
        Unknown ISUPPORT parameter.
        """
        return tuple(params)

    def isupport_CHANLIMIT(self, params):
        """
        The maximum number of each channel type a user may join.
        """
        return self._splitParamArgs(params, _intOrDefault)

    def isupport_CHANMODES(self, params):
        """
        Available channel modes.

        There are 4 categories of channel mode::

            addressModes - Modes that add or remove an address to or from a
            list, these modes always take a parameter.

            param - Modes that change a setting on a channel, these modes
            always take a parameter.

            setParam - Modes that change a setting on a channel, these modes
            only take a parameter when being set.

            noParam - Modes that change a setting on a channel, these modes
            never take a parameter.
        """
        try:
            return self._parseChanModesParam(params)
        except ValueError:
            return self.getFeature("CHANMODES")

    def isupport_CHANNELLEN(self, params):
        """
        Maximum length of a channel name a client may create.
        """
        return _intOrDefault(params[0], self.getFeature("CHANNELLEN"))

    def isupport_CHANTYPES(self, params):
        """
        Valid channel prefixes.
        """
        return tuple(params[0])

    def isupport_EXCEPTS(self, params):
        """
        Mode character for "ban exceptions".

        The presence of this parameter indicates that the server supports
        this functionality.
        """
        return params[0] or "e"

    def isupport_IDCHAN(self, params):
        """
        Safe channel identifiers.

        The presence of this parameter indicates that the server supports
        this functionality.
        """
        return self._splitParamArgs(params)

    def isupport_INVEX(self, params):
        """
        Mode character for "invite exceptions".

        The presence of this parameter indicates that the server supports
        this functionality.
        """
        return params[0] or "I"

    def isupport_KICKLEN(self, params):
        """
        Maximum length of a kick message a client may provide.
        """
        return _intOrDefault(params[0])

    def isupport_MAXLIST(self, params):
        """
        Maximum number of "list modes" a client may set on a channel at once.

        List modes are identified by the "addressModes" key in CHANMODES.
        """
        return self._splitParamArgs(params, _intOrDefault)

    def isupport_MODES(self, params):
        """
        Maximum number of modes accepting parameters that may be sent, by a
        client, in a single MODE command.
        """
        return _intOrDefault(params[0])

    def isupport_NETWORK(self, params):
        """
        IRC network name.
        """
        return params[0]

    def isupport_NICKLEN(self, params):
        """
        Maximum length of a nickname the client may use.
        """
        return _intOrDefault(params[0], self.getFeature("NICKLEN"))

    def isupport_PREFIX(self, params):
        """
        Mapping of channel modes that clients may have to status flags.
        """
        try:
            return self._parsePrefixParam(params[0])
        except ValueError:
            return self.getFeature("PREFIX")

    def isupport_SAFELIST(self, params):
        """
        Flag indicating that a client may request a LIST without being
        disconnected due to the large amount of data generated.
        """
        return True

    def isupport_STATUSMSG(self, params):
        """
        The server supports sending messages to only to clients on a channel
        with a specific status.
        """
        return params[0]

    def isupport_TARGMAX(self, params):
        """
        Maximum number of targets allowable for commands that accept multiple
        targets.
        """
        return dict(self._splitParamArgs(params, _intOrDefault))

    def isupport_TOPICLEN(self, params):
        """
        Maximum length of a topic that may be set.
        """
        return _intOrDefault(params[0])


class IRCClient(basic.LineReceiver):
    """
    Internet Relay Chat client protocol, with sprinkles.

    In addition to providing an interface for an IRC client protocol,
    this class also contains reasonable implementations of many common
    CTCP methods.

    TODO
    ====
     - Limit the length of messages sent (because the IRC server probably
       does).
     - Add flood protection/rate limiting for my CTCP replies.
     - NickServ cooperation.  (a mix-in?)

    @ivar nickname: Nickname the client will use.
    @ivar password: Password used to log on to the server.  May be L{None}.
    @ivar realname: Supplied to the server during login as the "Real name"
        or "ircname".  May be L{None}.
    @ivar username: Supplied to the server during login as the "User name".
        May be L{None}

    @ivar userinfo: Sent in reply to a C{USERINFO} CTCP query.  If L{None}, no
        USERINFO reply will be sent.
        "This is used to transmit a string which is settable by
        the user (and never should be set by the client)."
    @ivar fingerReply: Sent in reply to a C{FINGER} CTCP query.  If L{None}, no
        FINGER reply will be sent.
    @type fingerReply: Callable or String

    @ivar versionName: CTCP VERSION reply, client name.  If L{None}, no VERSION
        reply will be sent.
    @type versionName: C{str}, or None.
    @ivar versionNum: CTCP VERSION reply, client version.
    @type versionNum: C{str}, or None.
    @ivar versionEnv: CTCP VERSION reply, environment the client is running in.
    @type versionEnv: C{str}, or None.

    @ivar sourceURL: CTCP SOURCE reply, a URL where the source code of this
        client may be found.  If L{None}, no SOURCE reply will be sent.

    @ivar lineRate: Minimum delay between lines sent to the server.  If
        L{None}, no delay will be imposed.
    @type lineRate: Number of Seconds.

    @ivar motd: Either L{None} or, between receipt of I{RPL_MOTDSTART} and
        I{RPL_ENDOFMOTD}, a L{list} of L{str}, each of which is the content
        of an I{RPL_MOTD} message.

    @ivar erroneousNickFallback: Default nickname assigned when an unregistered
        client triggers an C{ERR_ERRONEUSNICKNAME} while trying to register
        with an illegal nickname.
    @type erroneousNickFallback: C{str}

    @ivar _registered: Whether or not the user is registered. It becomes True
        once a welcome has been received from the server.
    @type _registered: C{bool}

    @ivar _attemptedNick: The nickname that will try to get registered. It may
        change if it is illegal or already taken. L{nickname} becomes the
        L{_attemptedNick} that is successfully registered.
    @type _attemptedNick:  C{str}

    @type supported: L{ServerSupportedFeatures}
    @ivar supported: Available ISUPPORT features on the server

    @type hostname: C{str}
    @ivar hostname: Host name of the IRC server the client is connected to.
        Initially the host name is L{None} and later is set to the host name
        from which the I{RPL_WELCOME} message is received.

    @type _heartbeat: L{task.LoopingCall}
    @ivar _heartbeat: Looping call to perform the keepalive by calling
        L{IRCClient._sendHeartbeat} every L{heartbeatInterval} seconds, or
        L{None} if there is no heartbeat.

    @type heartbeatInterval: C{float}
    @ivar heartbeatInterval: Interval, in seconds, to send I{PING} messages to
        the server as a form of keepalive, defaults to 120 seconds. Use L{None}
        to disable the heartbeat.
    """

    hostname = None
    motd = None
    nickname = "irc"
    password = None
    realname = None
    username = None
    ### Responses to various CTCP queries.

    userinfo = None
    # fingerReply is a callable returning a string, or a str()able object.
    fingerReply = None
    versionName = None
    versionNum = None
    versionEnv = None

    sourceURL = "http://twistedmatrix.com/downloads/"

    dcc_destdir = "."
    dcc_sessions = None

    # If this is false, no attempt will be made to identify
    # ourself to the server.
    performLogin = 1

    lineRate = None
    _queue = None
    _queueEmptying = None

    delimiter = b"\n"  # b'\r\n' will also work (see dataReceived)

    __pychecker__ = "unusednames=params,prefix,channel"

    _registered = False
    _attemptedNick = ""
    erroneousNickFallback = "defaultnick"

    _heartbeat = None
    heartbeatInterval = 120

    def _reallySendLine(self, line):
        quoteLine = lowQuote(line)
        if isinstance(quoteLine, str):
            quoteLine = quoteLine.encode("utf-8")
        quoteLine += b"\r"
        return basic.LineReceiver.sendLine(self, quoteLine)

    def sendLine(self, line):
        if self.lineRate is None:
            self._reallySendLine(line)
        else:
            self._queue.append(line)
            if not self._queueEmptying:
                self._sendLine()

    def _sendLine(self):
        if self._queue:
            self._reallySendLine(self._queue.pop(0))
            self._queueEmptying = reactor.callLater(self.lineRate, self._sendLine)
        else:
            self._queueEmptying = None

    def connectionLost(self, reason):
        basic.LineReceiver.connectionLost(self, reason)
        self.stopHeartbeat()

    def _createHeartbeat(self):
        """
        Create the heartbeat L{LoopingCall}.
        """
        return task.LoopingCall(self._sendHeartbeat)

    def _sendHeartbeat(self):
        """
        Send a I{PING} message to the IRC server as a form of keepalive.
        """
        self.sendLine("PING " + self.hostname)

    def stopHeartbeat(self):
        """
        Stop sending I{PING} messages to keep the connection to the server
        alive.

        @since: 11.1
        """
        if self._heartbeat is not None:
            self._heartbeat.stop()
            self._heartbeat = None

    def startHeartbeat(self):
        """
        Start sending I{PING} messages every L{IRCClient.heartbeatInterval}
        seconds to keep the connection to the server alive during periods of no
        activity.

        @since: 11.1
        """
        self.stopHeartbeat()
        if self.heartbeatInterval is None:
            return
        self._heartbeat = self._createHeartbeat()
        self._heartbeat.start(self.heartbeatInterval, now=False)

    ### Interface level client->user output methods
    ###
    ### You'll want to override these.

    ### Methods relating to the server itself

    def created(self, when):
        """
        Called with creation date information about the server, usually at logon.

        @type when: C{str}
        @param when: A string describing when the server was created, probably.
        """

    def yourHost(self, info):
        """
        Called with daemon information about the server, usually at logon.

        @type info: C{str}
        @param info: A string describing what software the server is running, probably.
        """

    def myInfo(self, servername, version, umodes, cmodes):
        """
        Called with information about the server, usually at logon.

        @type servername: C{str}
        @param servername: The hostname of this server.

        @type version: C{str}
        @param version: A description of what software this server runs.

        @type umodes: C{str}
        @param umodes: All the available user modes.

        @type cmodes: C{str}
        @param cmodes: All the available channel modes.
        """

    def luserClient(self, info):
        """
        Called with information about the number of connections, usually at logon.

        @type info: C{str}
        @param info: A description of the number of clients and servers
        connected to the network, probably.
        """

    def bounce(self, info):
        """
        Called with information about where the client should reconnect.

        @type info: C{str}
        @param info: A plaintext description of the address that should be
        connected to.
        """

    def isupport(self, options):
        """
        Called with various information about what the server supports.

        @type options: C{list} of C{str}
        @param options: Descriptions of features or limits of the server, possibly
        in the form "NAME=VALUE".
        """

    def luserChannels(self, channels):
        """
        Called with the number of channels existent on the server.

        @type channels: C{int}
        """

    def luserOp(self, ops):
        """
        Called with the number of ops logged on to the server.

        @type ops: C{int}
        """

    def luserMe(self, info):
        """
        Called with information about the server connected to.

        @type info: C{str}
        @param info: A plaintext string describing the number of users and servers
        connected to this server.
        """

    ### Methods involving me directly

    def privmsg(self, user, channel, message):
        """
        Called when I have a message from a user to me or a channel.
        """
        pass

    def joined(self, channel):
        """
        Called when I finish joining a channel.

        channel has the starting character (C{'#'}, C{'&'}, C{'!'}, or C{'+'})
        intact.
        """

    def left(self, channel):
        """
        Called when I have left a channel.

        channel has the starting character (C{'#'}, C{'&'}, C{'!'}, or C{'+'})
        intact.
        """

    def noticed(self, user, channel, message):
        """
        Called when I have a notice from a user to me or a channel.

        If the client makes any automated replies, it must not do so in
        response to a NOTICE message, per the RFC::

            The difference between NOTICE and PRIVMSG is that
            automatic replies MUST NEVER be sent in response to a
            NOTICE message. [...] The object of this rule is to avoid
            loops between clients automatically sending something in
            response to something it received.
        """

    def modeChanged(self, user, channel, set, modes, args):
        """
        Called when users or channel's modes are changed.

        @type user: C{str}
        @param user: The user and hostmask which instigated this change.

        @type channel: C{str}
        @param channel: The channel where the modes are changed. If args is
        empty the channel for which the modes are changing. If the changes are
        at server level it could be equal to C{user}.

        @type set: C{bool} or C{int}
        @param set: True if the mode(s) is being added, False if it is being
        removed. If some modes are added and others removed at the same time
        this function will be called twice, the first time with all the added
        modes, the second with the removed ones. (To change this behaviour
        override the irc_MODE method)

        @type modes: C{str}
        @param modes: The mode or modes which are being changed.

        @type args: C{tuple}
        @param args: Any additional information required for the mode
        change.
        """

    def pong(self, user, secs):
        """
        Called with the results of a CTCP PING query.
        """
        pass

    def signedOn(self):
        """
        Called after successfully signing on to the server.
        """
        pass

    def kickedFrom(self, channel, kicker, message):
        """
        Called when I am kicked from a channel.
        """
        pass

    def nickChanged(self, nick):
        """
        Called when my nick has been changed.
        """
        self.nickname = nick

    ### Things I observe other people doing in a channel.

    def userJoined(self, user, channel):
        """
        Called when I see another user joining a channel.
        """
        pass

    def userLeft(self, user, channel):
        """
        Called when I see another user leaving a channel.
        """
        pass

    def userQuit(self, user, quitMessage):
        """
        Called when I see another user disconnect from the network.
        """
        pass

    def userKicked(self, kickee, channel, kicker, message):
        """
        Called when I observe someone else being kicked from a channel.
        """
        pass

    def action(self, user, channel, data):
        """
        Called when I see a user perform an ACTION on a channel.
        """
        pass

    def topicUpdated(self, user, channel, newTopic):
        """
        In channel, user changed the topic to newTopic.

        Also called when first joining a channel.
        """
        pass

    def userRenamed(self, oldname, newname):
        """
        A user changed their name from oldname to newname.
        """
        pass

    ### Information from the server.

    def receivedMOTD(self, motd):
        """
        I received a message-of-the-day banner from the server.

        motd is a list of strings, where each string was sent as a separate
        message from the server. To display, you might want to use::

            '\\n'.join(motd)

        to get a nicely formatted string.
        """
        pass

    ### user input commands, client->server
    ### Your client will want to invoke these.

    def join(self, channel, key=None):
        """
        Join a channel.

        @type channel: C{str}
        @param channel: The name of the channel to join. If it has no prefix,
            C{'#'} will be prepended to it.
        @type key: C{str}
        @param key: If specified, the key used to join the channel.
        """
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        if key:
            self.sendLine(f"JOIN {channel} {key}")
        else:
            self.sendLine(f"JOIN {channel}")

    def leave(self, channel, reason=None):
        """
        Leave a channel.

        @type channel: C{str}
        @param channel: The name of the channel to leave. If it has no prefix,
            C{'#'} will be prepended to it.
        @type reason: C{str}
        @param reason: If given, the reason for leaving.
        """
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        if reason:
            self.sendLine(f"PART {channel} :{reason}")
        else:
            self.sendLine(f"PART {channel}")

    def kick(self, channel, user, reason=None):
        """
        Attempt to kick a user from a channel.

        @type channel: C{str}
        @param channel: The name of the channel to kick the user from. If it has
            no prefix, C{'#'} will be prepended to it.
        @type user: C{str}
        @param user: The nick of the user to kick.
        @type reason: C{str}
        @param reason: If given, the reason for kicking the user.
        """
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        if reason:
            self.sendLine(f"KICK {channel} {user} :{reason}")
        else:
            self.sendLine(f"KICK {channel} {user}")

    part = leave

    def invite(self, user, channel):
        """
        Attempt to invite user to channel

        @type user: C{str}
        @param user: The user to invite
        @type channel: C{str}
        @param channel: The channel to invite the user too

        @since: 11.0
        """
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        self.sendLine(f"INVITE {user} {channel}")

    def topic(self, channel, topic=None):
        """
        Attempt to set the topic of the given channel, or ask what it is.

        If topic is None, then I sent a topic query instead of trying to set the
        topic. The server should respond with a TOPIC message containing the
        current topic of the given channel.

        @type channel: C{str}
        @param channel: The name of the channel to change the topic on. If it
            has no prefix, C{'#'} will be prepended to it.
        @type topic: C{str}
        @param topic: If specified, what to set the topic to.
        """
        # << TOPIC #xtestx :fff
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        if topic != None:
            self.sendLine(f"TOPIC {channel} :{topic}")
        else:
            self.sendLine(f"TOPIC {channel}")

    def mode(self, chan, set, modes, limit=None, user=None, mask=None):
        """
        Change the modes on a user or channel.

        The C{limit}, C{user}, and C{mask} parameters are mutually exclusive.

        @type chan: C{str}
        @param chan: The name of the channel to operate on.
        @type set: C{bool}
        @param set: True to give the user or channel permissions and False to
            remove them.
        @type modes: C{str}
        @param modes: The mode flags to set on the user or channel.
        @type limit: C{int}
        @param limit: In conjunction with the C{'l'} mode flag, limits the
             number of users on the channel.
        @type user: C{str}
        @param user: The user to change the mode on.
        @type mask: C{str}
        @param mask: In conjunction with the C{'b'} mode flag, sets a mask of
            users to be banned from the channel.
        """
        if set:
            line = f"MODE {chan} +{modes}"
        else:
            line = f"MODE {chan} -{modes}"
        if limit is not None:
            line = "%s %d" % (line, limit)
        elif user is not None:
            line = f"{line} {user}"
        elif mask is not None:
            line = f"{line} {mask}"
        self.sendLine(line)

    def say(self, channel, message, length=None):
        """
        Send a message to a channel

        @type channel: C{str}
        @param channel: The channel to say the message on. If it has no prefix,
            C{'#'} will be prepended to it.
        @type message: C{str}
        @param message: The message to say.
        @type length: C{int}
        @param length: The maximum number of octets to send at a time.  This has
            the effect of turning a single call to C{msg()} into multiple
            commands to the server.  This is useful when long messages may be
            sent that would otherwise cause the server to kick us off or
            silently truncate the text we are sending.  If None is passed, the
            entire message is always send in one command.
        """
        if channel[0] not in CHANNEL_PREFIXES:
            channel = "#" + channel
        self.msg(channel, message, length)

    def _safeMaximumLineLength(self, command):
        """
        Estimate a safe maximum line length for the given command.

        This is done by assuming the maximum values for nickname length,
        realname and hostname combined with the command that needs to be sent
        and some guessing. A theoretical maximum value is used because it is
        possible that our nickname, username or hostname changes (on the server
        side) while the length is still being calculated.
        """
        # :nickname!realname@hostname COMMAND ...
        theoretical = ":{}!{}@{} {}".format(
            "a" * self.supported.getFeature("NICKLEN"),
            # This value is based on observation.
            "b" * 10,
            # See <http://tools.ietf.org/html/rfc2812#section-2.3.1>.
            "c" * 63,
            command,
        )
        # Fingers crossed.
        fudge = 10
        return MAX_COMMAND_LENGTH - len(theoretical) - fudge

    def _sendMessage(self, msgType, user, message, length=None):
        """
        Send a message or notice to a user or channel.

        The message will be split into multiple commands to the server if:
         - The message contains any newline characters
         - Any span between newline characters is longer than the given
           line-length.

        @param msgType: Whether a PRIVMSG or NOTICE should be sent.
        @type msgType: C{str}

        @param user: Username or channel name to which to direct the
            message.
        @type user: C{str}

        @param message: Text to send.
        @type message: C{str}

        @param length: Maximum number of octets to send in a single
            command, including the IRC protocol framing. If L{None} is given
            then L{IRCClient._safeMaximumLineLength} is used to determine a
            value.
        @type length: C{int}
        """
        fmt = f"{msgType} {user} :"

        if length is None:
            length = self._safeMaximumLineLength(fmt)

        # Account for the line terminator.
        minimumLength = len(fmt) + 2
        if length <= minimumLength:
            raise ValueError(
                "Maximum length must exceed %d for message "
                "to %s" % (minimumLength, user)
            )
        for line in split(message, length - minimumLength):
            self.sendLine(fmt + line)

    def msg(self, user, message, length=None):
        """
        Send a message to a user or channel.

        The message will be split into multiple commands to the server if:
         - The message contains any newline characters
         - Any span between newline characters is longer than the given
           line-length.

        @param user: Username or channel name to which to direct the
            message.
        @type user: C{str}

        @param message: Text to send.
        @type message: C{str}

        @param length: Maximum number of octets to send in a single
            command, including the IRC protocol framing. If L{None} is given
            then L{IRCClient._safeMaximumLineLength} is used to determine a
            value.
        @type length: C{int}
        """
        self._sendMessage("PRIVMSG", user, message, length)

    def notice(self, user, message, length=None):
        """
        Send a notice to a user.

        Notices are like normal message, but should never get automated
        replies.

        @type user: C{str}
        @param user: The user to send a notice to.

        @type message: C{str}
        @param message: The contents of the notice to send.

        @param length: Maximum number of octets to send in a single
            command, including the IRC protocol framing. If L{None} is given
            then L{IRCClient._safeMaximumLineLength} is used to determine a
            value.
        @type length: C{int}
        """
        self._sendMessage("NOTICE", user, message, length)

    def away(self, message=""):
        """
        Mark this client as away.

        @type message: C{str}
        @param message: If specified, the away message.
        """
        self.sendLine("AWAY :%s" % message)

    def back(self):
        """
        Clear the away status.
        """
        # An empty away marks us as back
        self.away()

    def whois(self, nickname, server=None):
        """
        Retrieve user information about the given nickname.

        @type nickname: C{str}
        @param nickname: The nickname about which to retrieve information.

        @since: 8.2
        """
        if server is None:
            self.sendLine("WHOIS " + nickname)
        else:
            self.sendLine(f"WHOIS {server} {nickname}")

    def register(self, nickname, hostname="foo", servername="bar"):
        """
        Login to the server.

        @type nickname: C{str}
        @param nickname: The nickname to register.
        @type hostname: C{str}
        @param hostname: If specified, the hostname to logon as.
        @type servername: C{str}
        @param servername: If specified, the servername to logon as.
        """
        if self.password is not None:
            self.sendLine("PASS %s" % self.password)
        self.setNick(nickname)
        if self.username is None:
            self.username = nickname
        self.sendLine(
            "USER {} {} {} :{}".format(
                self.username, hostname, servername, self.realname
            )
        )

    def setNick(self, nickname):
        """
        Set this client's nickname.

        @type nickname: C{str}
        @param nickname: The nickname to change to.
        """
        self._attemptedNick = nickname
        self.sendLine("NICK %s" % nickname)

    def quit(self, message=""):
        """
        Disconnect from the server

        @type message: C{str}

        @param message: If specified, the message to give when quitting the
            server.
        """
        self.sendLine("QUIT :%s" % message)

    ### user input commands, client->client

    def describe(self, channel, action):
        """
        Strike a pose.

        @type channel: C{str}
        @param channel: The name of the channel to have an action on. If it
            has no prefix, it is sent to the user of that name.
        @type action: C{str}
        @param action: The action to preform.
        @since: 9.0
        """
        self.ctcpMakeQuery(channel, [("ACTION", action)])

    _pings = None
    _MAX_PINGRING = 12

    def ping(self, user, text=None):
        """
        Measure round-trip delay to another IRC client.
        """
        if self._pings is None:
            self._pings = {}

        if text is None:
            chars = string.ascii_letters + string.digits + string.punctuation
            key = "".join([random.choice(chars) for i in range(12)])
        else:
            key = str(text)
        self._pings[(user, key)] = time.time()
        self.ctcpMakeQuery(user, [("PING", key)])

        if len(self._pings) > self._MAX_PINGRING:
            # Remove some of the oldest entries.
            byValue = [(v, k) for (k, v) in self._pings.items()]
            byValue.sort()
            excess = len(self._pings) - self._MAX_PINGRING
            for i in range(excess):
                del self._pings[byValue[i][1]]

    def dccSend(self, user, file):
        """
        This is supposed to send a user a file directly.  This generally
        doesn't work on any client, and this method is included only for
        backwards compatibility and completeness.

        @param user: C{str} representing the user
        @param file: an open file (unknown, since this is not implemented)
        """
        raise NotImplementedError(
            "XXX!!! Help!  I need to bind a socket, have it listen, and tell me its address.  "
            "(and stop accepting once we've made a single connection.)"
        )

    def dccResume(self, user, fileName, port, resumePos):
        """
        Send a DCC RESUME request to another user.
        """
        self.ctcpMakeQuery(user, [("DCC", ["RESUME", fileName, port, resumePos])])

    def dccAcceptResume(self, user, fileName, port, resumePos):
        """
        Send a DCC ACCEPT response to clients who have requested a resume.
        """
        self.ctcpMakeQuery(user, [("DCC", ["ACCEPT", fileName, port, resumePos])])

    ### server->client messages
    ### You might want to fiddle with these,
    ### but it is safe to leave them alone.

    def irc_ERR_NICKNAMEINUSE(self, prefix, params):
        """
        Called when we try to register or change to a nickname that is already
        taken.
        """
        self._attemptedNick = self.alterCollidedNick(self._attemptedNick)
        self.setNick(self._attemptedNick)

    def alterCollidedNick(self, nickname):
        """
        Generate an altered version of a nickname that caused a collision in an
        effort to create an unused related name for subsequent registration.

        @param nickname: The nickname a user is attempting to register.
        @type nickname: C{str}

        @returns: A string that is in some way different from the nickname.
        @rtype: C{str}
        """
        return nickname + "_"

    def irc_ERR_ERRONEUSNICKNAME(self, prefix, params):
        """
        Called when we try to register or change to an illegal nickname.

        The server should send this reply when the nickname contains any
        disallowed characters.  The bot will stall, waiting for RPL_WELCOME, if
        we don't handle this during sign-on.

        @note: The method uses the spelling I{erroneus}, as it appears in
            the RFC, section 6.1.
        """
        if not self._registered:
            self.setNick(self.erroneousNickFallback)

    def irc_ERR_PASSWDMISMATCH(self, prefix, params):
        """
        Called when the login was incorrect.
        """
        raise IRCPasswordMismatch("Password Incorrect.")

    def irc_RPL_WELCOME(self, prefix, params):
        """
        Called when we have received the welcome from the server.
        """
        self.hostname = prefix
        self._registered = True
        self.nickname = self._attemptedNick
        self.signedOn()
        self.startHeartbeat()

    def irc_JOIN(self, prefix, params):
        """
        Called when a user joins a channel.
        """
        nick = prefix.split("!")[0]
        channel = params[-1]
        if nick == self.nickname:
            self.joined(channel)
        else:
            self.userJoined(nick, channel)

    def irc_PART(self, prefix, params):
        """
        Called when a user leaves a channel.
        """
        nick = prefix.split("!")[0]
        channel = params[0]
        if nick == self.nickname:
            self.left(channel)
        else:
            self.userLeft(nick, channel)

    def irc_QUIT(self, prefix, params):
        """
        Called when a user has quit.
        """
        nick = prefix.split("!")[0]
        self.userQuit(nick, params[0])

    def irc_MODE(self, user, params):
        """
        Parse a server mode change message.
        """
        channel, modes, args = params[0], params[1], params[2:]

        if modes[0] not in "-+":
            modes = "+" + modes

        if channel == self.nickname:
            # This is a mode change to our individual user, not a channel mode
            # that involves us.
            paramModes = self.getUserModeParams()
        else:
            paramModes = self.getChannelModeParams()

        try:
            added, removed = parseModes(modes, args, paramModes)
        except IRCBadModes:
            log.err(
                None,
                "An error occurred while parsing the following "
                "MODE message: MODE %s" % (" ".join(params),),
            )
        else:
            if added:
                modes, params = zip(*added)
                self.modeChanged(user, channel, True, "".join(modes), params)

            if removed:
                modes, params = zip(*removed)
                self.modeChanged(user, channel, False, "".join(modes), params)

    def irc_PING(self, prefix, params):
        """
        Called when some has pinged us.
        """
        self.sendLine("PONG %s" % params[-1])

    def irc_PRIVMSG(self, prefix, params):
        """
        Called when we get a message.
        """
        user = prefix
        channel = params[0]
        message = params[-1]

        if not message:
            # Don't raise an exception if we get blank message.
            return

        if message[0] == X_DELIM:
            m = ctcpExtract(message)
            if m["extended"]:
                self.ctcpQuery(user, channel, m["extended"])

            if not m["normal"]:
                return

            message = " ".join(m["normal"])

        self.privmsg(user, channel, message)

    def irc_NOTICE(self, prefix, params):
        """
        Called when a user gets a notice.
        """
        user = prefix
        channel = params[0]
        message = params[-1]

        if message[0] == X_DELIM:
            m = ctcpExtract(message)
            if m["extended"]:
                self.ctcpReply(user, channel, m["extended"])

            if not m["normal"]:
                return

            message = " ".join(m["normal"])

        self.noticed(user, channel, message)

    def irc_NICK(self, prefix, params):
        """
        Called when a user changes their nickname.
        """
        nick = prefix.split("!", 1)[0]
        if nick == self.nickname:
            self.nickChanged(params[0])
        else:
            self.userRenamed(nick, params[0])

    def irc_KICK(self, prefix, params):
        """
        Called when a user is kicked from a channel.
        """
        kicker = prefix.split("!")[0]
        channel = params[0]
        kicked = params[1]
        message = params[-1]
        if kicked.lower() == self.nickname.lower():
            # Yikes!
            self.kickedFrom(channel, kicker, message)
        else:
            self.userKicked(kicked, channel, kicker, message)

    def irc_TOPIC(self, prefix, params):
        """
        Someone in the channel set the topic.
        """
        user = prefix.split("!")[0]
        channel = params[0]
        newtopic = params[1]
        self.topicUpdated(user, channel, newtopic)

    def irc_RPL_TOPIC(self, prefix, params):
        """
        Called when the topic for a channel is initially reported or when it
        subsequently changes.
        """
        user = prefix.split("!")[0]
        channel = params[1]
        newtopic = params[2]
        self.topicUpdated(user, channel, newtopic)

    def irc_RPL_NOTOPIC(self, prefix, params):
        user = prefix.split("!")[0]
        channel = params[1]
        newtopic = ""
        self.topicUpdated(user, channel, newtopic)

    def irc_RPL_MOTDSTART(self, prefix, params):
        if params[-1].startswith("- "):
            params[-1] = params[-1][2:]
        self.motd = [params[-1]]

    def irc_RPL_MOTD(self, prefix, params):
        if params[-1].startswith("- "):
            params[-1] = params[-1][2:]
        if self.motd is None:
            self.motd = []
        self.motd.append(params[-1])

    def irc_RPL_ENDOFMOTD(self, prefix, params):
        """
        I{RPL_ENDOFMOTD} indicates the end of the message of the day
        messages.  Deliver the accumulated lines to C{receivedMOTD}.
        """
        motd = self.motd
        self.motd = None
        self.receivedMOTD(motd)

    def irc_RPL_CREATED(self, prefix, params):
        self.created(params[1])

    def irc_RPL_YOURHOST(self, prefix, params):
        self.yourHost(params[1])

    def irc_RPL_MYINFO(self, prefix, params):
        info = params[1].split(None, 3)
        while len(info) < 4:
            info.append(None)
        self.myInfo(*info)

    def irc_RPL_BOUNCE(self, prefix, params):
        self.bounce(params[1])

    def irc_RPL_ISUPPORT(self, prefix, params):
        args = params[1:-1]
        # Several ISUPPORT messages, in no particular order, may be sent
        # to the client at any given point in time (usually only on connect,
        # though.) For this reason, ServerSupportedFeatures.parse is intended
        # to mutate the supported feature list.
        self.supported.parse(args)
        self.isupport(args)

    def irc_RPL_LUSERCLIENT(self, prefix, params):
        self.luserClient(params[1])

    def irc_RPL_LUSEROP(self, prefix, params):
        try:
            self.luserOp(int(params[1]))
        except ValueError:
            pass

    def irc_RPL_LUSERCHANNELS(self, prefix, params):
        try:
            self.luserChannels(int(params[1]))
        except ValueError:
            pass

    def irc_RPL_LUSERME(self, prefix, params):
        self.luserMe(params[1])

    def irc_unknown(self, prefix, command, params):
        pass

    ### Receiving a CTCP query from another party
    ### It is safe to leave these alone.

    def ctcpQuery(self, user, channel, messages):
        """
        Dispatch method for any CTCP queries received.

        Duplicated CTCP queries are ignored and no dispatch is
        made. Unrecognized CTCP queries invoke L{IRCClient.ctcpUnknownQuery}.
        """
        seen = set()
        for tag, data in messages:
            method = getattr(self, "ctcpQuery_%s" % tag, None)
            if tag not in seen:
                if method is not None:
                    method(user, channel, data)
                else:
                    self.ctcpUnknownQuery(user, channel, tag, data)
            seen.add(tag)

    def ctcpUnknownQuery(self, user, channel, tag, data):
        """
        Fallback handler for unrecognized CTCP queries.

        No CTCP I{ERRMSG} reply is made to remove a potential denial of service
        avenue.
        """
        log.msg(f"Unknown CTCP query from {user!r}: {tag!r} {data!r}")

    def ctcpQuery_ACTION(self, user, channel, data):
        self.action(user, channel, data)

    def ctcpQuery_PING(self, user, channel, data):
        nick = user.split("!")[0]
        self.ctcpMakeReply(nick, [("PING", data)])

    def ctcpQuery_FINGER(self, user, channel, data):
        if data is not None:
            self.quirkyMessage(f"Why did {user} send '{data}' with a FINGER query?")
        if not self.fingerReply:
            return

        if callable(self.fingerReply):
            reply = self.fingerReply()
        else:
            reply = str(self.fingerReply)

        nick = user.split("!")[0]
        self.ctcpMakeReply(nick, [("FINGER", reply)])

    def ctcpQuery_VERSION(self, user, channel, data):
        if data is not None:
            self.quirkyMessage(f"Why did {user} send '{data}' with a VERSION query?")

        if self.versionName:
            nick = user.split("!")[0]
            self.ctcpMakeReply(
                nick,
                [
                    (
                        "VERSION",
                        "%s:%s:%s"
                        % (
                            self.versionName,
                            self.versionNum or "",
                            self.versionEnv or "",
                        ),
                    )
                ],
            )

    def ctcpQuery_SOURCE(self, user, channel, data):
        if data is not None:
            self.quirkyMessage(f"Why did {user} send '{data}' with a SOURCE query?")
        if self.sourceURL:
            nick = user.split("!")[0]
            # The CTCP document (Zeuge, Rollo, Mesander 1994) says that SOURCE
            # replies should be responded to with the location of an anonymous
            # FTP server in host:directory:file format.  I'm taking the liberty
            # of bringing it into the 21st century by sending a URL instead.
            self.ctcpMakeReply(nick, [("SOURCE", self.sourceURL), ("SOURCE", None)])

    def ctcpQuery_USERINFO(self, user, channel, data):
        if data is not None:
            self.quirkyMessage(f"Why did {user} send '{data}' with a USERINFO query?")
        if self.userinfo:
            nick = user.split("!")[0]
            self.ctcpMakeReply(nick, [("USERINFO", self.userinfo)])

    def ctcpQuery_CLIENTINFO(self, user, channel, data):
        """
        A master index of what CTCP tags this client knows.

        If no arguments are provided, respond with a list of known tags, sorted
        in alphabetical order.
        If an argument is provided, provide human-readable help on
        the usage of that tag.
        """
        nick = user.split("!")[0]
        if not data:
            # XXX: prefixedMethodNames gets methods from my *class*,
            # but it's entirely possible that this *instance* has more
            # methods.
            names = sorted(reflect.prefixedMethodNames(self.__class__, "ctcpQuery_"))

            self.ctcpMakeReply(nick, [("CLIENTINFO", " ".join(names))])
        else:
            args = data.split()
            method = getattr(self, f"ctcpQuery_{args[0]}", None)
            if not method:
                self.ctcpMakeReply(
                    nick,
                    [
                        (
                            "ERRMSG",
                            "CLIENTINFO %s :" "Unknown query '%s'" % (data, args[0]),
                        )
                    ],
                )
                return
            doc = getattr(method, "__doc__", "")
            self.ctcpMakeReply(nick, [("CLIENTINFO", doc)])

    def ctcpQuery_ERRMSG(self, user, channel, data):
        # Yeah, this seems strange, but that's what the spec says to do
        # when faced with an ERRMSG query (not a reply).
        nick = user.split("!")[0]
        self.ctcpMakeReply(nick, [("ERRMSG", "%s :No error has occurred." % data)])

    def ctcpQuery_TIME(self, user, channel, data):
        if data is not None:
            self.quirkyMessage(f"Why did {user} send '{data}' with a TIME query?")
        nick = user.split("!")[0]
        self.ctcpMakeReply(
            nick, [("TIME", ":%s" % time.asctime(time.localtime(time.time())))]
        )

    def ctcpQuery_DCC(self, user, channel, data):
        """
        Initiate a Direct Client Connection

        @param user: The hostmask of the user/client.
        @type user: L{bytes}

        @param channel: The name of the IRC channel.
        @type channel: L{bytes}

        @param data: The DCC request message.
        @type data: L{bytes}
        """

        if not data:
            return
        dcctype = data.split(None, 1)[0].upper()
        handler = getattr(self, "dcc_" + dcctype, None)
        if handler:
            if self.dcc_sessions is None:
                self.dcc_sessions = []
            data = data[len(dcctype) + 1 :]
            handler(user, channel, data)
        else:
            nick = user.split("!")[0]
            self.ctcpMakeReply(
                nick,
                [("ERRMSG", f"DCC {data} :Unknown DCC type '{dcctype}'")],
            )
            self.quirkyMessage(f"{user} offered unknown DCC type {dcctype}")

    def dcc_SEND(self, user, channel, data):
        # Use shlex.split for those who send files with spaces in the names.
        data = shlex.split(data)
        if len(data) < 3:
            raise IRCBadMessage(f"malformed DCC SEND request: {data!r}")

        (filename, address, port) = data[:3]

        address = dccParseAddress(address)
        try:
            port = int(port)
        except ValueError:
            raise IRCBadMessage(f"Indecipherable port {port!r}")

        size = -1
        if len(data) >= 4:
            try:
                size = int(data[3])
            except ValueError:
                pass

        # XXX Should we bother passing this data?
        self.dccDoSend(user, address, port, filename, size, data)

    def dcc_ACCEPT(self, user, channel, data):
        data = shlex.split(data)
        if len(data) < 3:
            raise IRCBadMessage(f"malformed DCC SEND ACCEPT request: {data!r}")
        (filename, port, resumePos) = data[:3]
        try:
            port = int(port)
            resumePos = int(resumePos)
        except ValueError:
            return

        self.dccDoAcceptResume(user, filename, port, resumePos)

    def dcc_RESUME(self, user, channel, data):
        data = shlex.split(data)
        if len(data) < 3:
            raise IRCBadMessage(f"malformed DCC SEND RESUME request: {data!r}")
        (filename, port, resumePos) = data[:3]
        try:
            port = int(port)
            resumePos = int(resumePos)
        except ValueError:
            return

        self.dccDoResume(user, filename, port, resumePos)

    def dcc_CHAT(self, user, channel, data):
        data = shlex.split(data)
        if len(data) < 3:
            raise IRCBadMessage(f"malformed DCC CHAT request: {data!r}")

        (filename, address, port) = data[:3]

        address = dccParseAddress(address)
        try:
            port = int(port)
        except ValueError:
            raise IRCBadMessage(f"Indecipherable port {port!r}")

        self.dccDoChat(user, channel, address, port, data)

    ### The dccDo methods are the slightly higher-level siblings of
    ### common dcc_ methods; the arguments have been parsed for them.

    def dccDoSend(self, user, address, port, fileName, size, data):
        """
        Called when I receive a DCC SEND offer from a client.

        By default, I do nothing here.

        @param user: The hostmask of the requesting user.
        @type user: L{bytes}

        @param address: The IP address of the requesting user.
        @type address: L{bytes}

        @param port: An integer representing the port of the requesting user.
        @type port: L{int}

        @param fileName: The name of the file to be transferred.
        @type fileName: L{bytes}

        @param size: The size of the file to be transferred, which may be C{-1}
            if the size of the file was not specified in the DCC SEND request.
        @type size: L{int}

        @param data: A 3-list of [fileName, address, port].
        @type data: L{list}
        """

    def dccDoResume(self, user, file, port, resumePos):
        """
        Called when a client is trying to resume an offered file via DCC send.
        It should be either replied to with a DCC ACCEPT or ignored (default).

        @param user: The hostmask of the user who wants to resume the transfer
            of a file previously offered via DCC send.
        @type user: L{bytes}

        @param file: The name of the file to resume the transfer of.
        @type file: L{bytes}

        @param port: An integer representing the port of the requesting user.
        @type port: L{int}

        @param resumePos: The position in the file from where the transfer
            should resume.
        @type resumePos: L{int}
        """
        pass

    def dccDoAcceptResume(self, user, file, port, resumePos):
        """
        Called when a client has verified and accepted a DCC resume request
        made by us.  By default it will do nothing.

        @param user: The hostmask of the user who has accepted the DCC resume
            request.
        @type user: L{bytes}

        @param file: The name of the file to resume the transfer of.
        @type file: L{bytes}

        @param port: An integer representing the port of the accepting user.
        @type port: L{int}

        @param resumePos: The position in the file from where the transfer
            should resume.
        @type resumePos: L{int}
        """
        pass

    def dccDoChat(self, user, channel, address, port, data):
        pass
        # factory = DccChatFactory(self, queryData=(user, channel, data))
        # reactor.connectTCP(address, port, factory)
        # self.dcc_sessions.append(factory)

    # def ctcpQuery_SED(self, user, data):
    #    """Simple Encryption Doodoo
    #
    #    Feel free to implement this, but no specification is available.
    #    """
    #    raise NotImplementedError

    def ctcpMakeReply(self, user, messages):
        """
        Send one or more C{extended messages} as a CTCP reply.

        @type messages: a list of extended messages.  An extended
        message is a (tag, data) tuple, where 'data' may be L{None}.
        """
        self.notice(user, ctcpStringify(messages))

    ### client CTCP query commands

    def ctcpMakeQuery(self, user, messages):
        """
        Send one or more C{extended messages} as a CTCP query.

        @type messages: a list of extended messages.  An extended
        message is a (tag, data) tuple, where 'data' may be L{None}.
        """
        self.msg(user, ctcpStringify(messages))

    ### Receiving a response to a CTCP query (presumably to one we made)
    ### You may want to add methods here, or override UnknownReply.

    def ctcpReply(self, user, channel, messages):
        """
        Dispatch method for any CTCP replies received.
        """
        for m in messages:
            method = getattr(self, "ctcpReply_%s" % m[0], None)
            if method:
                method(user, channel, m[1])
            else:
                self.ctcpUnknownReply(user, channel, m[0], m[1])

    def ctcpReply_PING(self, user, channel, data):
        nick = user.split("!", 1)[0]
        if (not self._pings) or ((nick, data) not in self._pings):
            raise IRCBadMessage(f"Bogus PING response from {user}: {data}")

        t0 = self._pings[(nick, data)]
        self.pong(user, time.time() - t0)

    def ctcpUnknownReply(self, user, channel, tag, data):
        """
        Called when a fitting ctcpReply_ method is not found.

        @param user: The hostmask of the user.
        @type user: L{bytes}

        @param channel: The name of the IRC channel.
        @type channel: L{bytes}

        @param tag: The CTCP request tag for which no fitting method is found.
        @type tag: L{bytes}

        @param data: The CTCP message.
        @type data: L{bytes}
        """
        # FIXME:7560:
        # Add code for handling arbitrary queries and not treat them as
        # anomalies.

        log.msg(f"Unknown CTCP reply from {user}: {tag} {data}\n")

    ### Error handlers
    ### You may override these with something more appropriate to your UI.

    def badMessage(self, line, excType, excValue, tb):
        """
        When I get a message that's so broken I can't use it.

        @param line: The indecipherable message.
        @type line: L{bytes}

        @param excType: The exception type of the exception raised by the
            message.
        @type excType: L{type}

        @param excValue: The exception parameter of excType or its associated
            value(the second argument to C{raise}).
        @type excValue: L{BaseException}

        @param tb: The Traceback as a traceback object.
        @type tb: L{traceback}
        """
        log.msg(line)
        log.msg("".join(traceback.format_exception(excType, excValue, tb)))

    def quirkyMessage(self, s):
        """
        This is called when I receive a message which is peculiar, but not
        wholly indecipherable.

        @param s: The peculiar message.
        @type s: L{bytes}
        """
        log.msg(s + "\n")

    ### Protocol methods

    def connectionMade(self):
        self.supported = ServerSupportedFeatures()
        self._queue = []
        if self.performLogin:
            self.register(self.nickname)

    def dataReceived(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        data = data.replace(b"\r", b"")
        basic.LineReceiver.dataReceived(self, data)

    def lineReceived(self, line):
        if bytes != str and isinstance(line, bytes):
            # decode bytes from transport to unicode
            line = line.decode("utf-8")

        line = lowDequote(line)
        try:
            prefix, command, params = parsemsg(line)
            if command in numeric_to_symbolic:
                command = numeric_to_symbolic[command]
            self.handleCommand(command, prefix, params)
        except IRCBadMessage:
            self.badMessage(line, *sys.exc_info())

    def getUserModeParams(self):
        """
        Get user modes that require parameters for correct parsing.

        @rtype: C{[str, str]}
        @return: C{[add, remove]}
        """
        return ["", ""]

    def getChannelModeParams(self):
        """
        Get channel modes that require parameters for correct parsing.

        @rtype: C{[str, str]}
        @return: C{[add, remove]}
        """
        # PREFIX modes are treated as "type B" CHANMODES, they always take
        # parameter.
        params = ["", ""]
        prefixes = self.supported.getFeature("PREFIX", {})
        params[0] = params[1] = "".join(prefixes.keys())

        chanmodes = self.supported.getFeature("CHANMODES")
        if chanmodes is not None:
            params[0] += chanmodes.get("addressModes", "")
            params[0] += chanmodes.get("param", "")
            params[1] = params[0]
            params[0] += chanmodes.get("setParam", "")
        return params

    def handleCommand(self, command, prefix, params):
        """
        Determine the function to call for the given command and call it with
        the given arguments.

        @param command: The IRC command to determine the function for.
        @type command: L{bytes}

        @param prefix: The prefix of the IRC message (as returned by
            L{parsemsg}).
        @type prefix: L{bytes}

        @param params: A list of parameters to call the function with.
        @type params: L{list}
        """
        method = getattr(self, "irc_%s" % command, None)
        try:
            if method is not None:
                method(prefix, params)
            else:
                self.irc_unknown(prefix, command, params)
        except BaseException:
            log.deferr()

    def __getstate__(self):
        dct = self.__dict__.copy()
        dct["dcc_sessions"] = None
        dct["_pings"] = None
        return dct


def dccParseAddress(address):
    if "." in address:
        pass
    else:
        try:
            address = int(address)
        except ValueError:
            raise IRCBadMessage(f"Indecipherable address {address!r}")
        else:
            address = (
                (address >> 24) & 0xFF,
                (address >> 16) & 0xFF,
                (address >> 8) & 0xFF,
                address & 0xFF,
            )
            address = ".".join(map(str, address))
    return address


class DccFileReceiveBasic(protocol.Protocol, styles.Ephemeral):
    """
    Bare protocol to receive a Direct Client Connection SEND stream.

    This does enough to keep the other guy talking, but you'll want to extend
    my dataReceived method to *do* something with the data I get.

    @ivar bytesReceived: An integer representing the number of bytes of data
        received.
    @type bytesReceived: L{int}
    """

    bytesReceived = 0

    def __init__(self, resumeOffset=0):
        """
        @param resumeOffset: An integer representing the amount of bytes from
            where the transfer of data should be resumed.
        @type resumeOffset: L{int}
        """
        self.bytesReceived = resumeOffset
        self.resume = resumeOffset != 0

    def dataReceived(self, data):
        """
        See: L{protocol.Protocol.dataReceived}

        Warning: This just acknowledges to the remote host that the data has
        been received; it doesn't I{do} anything with the data, so you'll want
        to override this.
        """
        self.bytesReceived = self.bytesReceived + len(data)
        self.transport.write(struct.pack("!i", self.bytesReceived))


class DccSendProtocol(protocol.Protocol, styles.Ephemeral):
    """
    Protocol for an outgoing Direct Client Connection SEND.

    @ivar blocksize: An integer representing the size of an individual block of
        data.
    @type blocksize: L{int}

    @ivar file: The file to be sent.  This can be either a file object or
        simply the name of the file.
    @type file: L{file} or L{bytes}

    @ivar bytesSent: An integer representing the number of bytes sent.
    @type bytesSent: L{int}

    @ivar completed: An integer representing whether the transfer has been
        completed or not.
    @type completed: L{int}

    @ivar connected: An integer representing whether the connection has been
        established or not.
    @type connected: L{int}
    """

    blocksize = 1024
    file = None
    bytesSent = 0
    completed = 0
    connected = 0

    def __init__(self, file):
        if type(file) is str:
            self.file = open(file)

    def connectionMade(self):
        self.connected = 1
        self.sendBlock()

    def dataReceived(self, data):
        # XXX: Do we need to check to see if len(data) != fmtsize?

        bytesShesGot = struct.unpack("!I", data)
        if bytesShesGot < self.bytesSent:
            # Wait for her.
            # XXX? Add some checks to see if we've stalled out?
            return
        elif bytesShesGot > self.bytesSent:
            # self.transport.log("DCC SEND %s: She says she has %d bytes "
            #                    "but I've only sent %d.  I'm stopping "
            #                    "this screwy transfer."
            #                    % (self.file,
            #                       bytesShesGot, self.bytesSent))
            self.transport.loseConnection()
            return

        self.sendBlock()

    def sendBlock(self):
        block = self.file.read(self.blocksize)
        if block:
            self.transport.write(block)
            self.bytesSent = self.bytesSent + len(block)
        else:
            # Nothing more to send, transfer complete.
            self.transport.loseConnection()
            self.completed = 1

    def connectionLost(self, reason):
        self.connected = 0
        if hasattr(self.file, "close"):
            self.file.close()


class DccSendFactory(protocol.Factory):
    protocol = DccSendProtocol  # type: ignore[assignment]

    def __init__(self, file):
        self.file = file

    def buildProtocol(self, connection):
        p = self.protocol(self.file)
        p.factory = self
        return p


def fileSize(file):
    """
    I'll try my damndest to determine the size of this file object.

    @param file: The file object to determine the size of.
    @type file: L{io.IOBase}

    @rtype: L{int} or L{None}
    @return: The size of the file object as an integer if it can be determined,
        otherwise return L{None}.
    """
    size = None
    if hasattr(file, "fileno"):
        fileno = file.fileno()
        try:
            stat_ = os.fstat(fileno)
            size = stat_[stat.ST_SIZE]
        except BaseException:
            pass
        else:
            return size

    if hasattr(file, "name") and path.exists(file.name):
        try:
            size = path.getsize(file.name)
        except BaseException:
            pass
        else:
            return size

    if hasattr(file, "seek") and hasattr(file, "tell"):
        try:
            try:
                file.seek(0, 2)
                size = file.tell()
            finally:
                file.seek(0, 0)
        except BaseException:
            pass
        else:
            return size

    return size


class DccChat(basic.LineReceiver, styles.Ephemeral):
    """
    Direct Client Connection protocol type CHAT.

    DCC CHAT is really just your run o' the mill basic.LineReceiver
    protocol.  This class only varies from that slightly, accepting
    either LF or CR LF for a line delimeter for incoming messages
    while always using CR LF for outgoing.

    The lineReceived method implemented here uses the DCC connection's
    'client' attribute (provided upon construction) to deliver incoming
    lines from the DCC chat via IRCClient's normal privmsg interface.
    That's something of a spoof, which you may well want to override.
    """

    queryData = None
    delimiter = CR.encode("ascii") + NL.encode("ascii")
    client = None
    remoteParty = None
    buffer = b""

    def __init__(self, client, queryData=None):
        """
        Initialize a new DCC CHAT session.

        queryData is a 3-tuple of
        (fromUser, targetUserOrChannel, data)
        as received by the CTCP query.

        (To be honest, fromUser is the only thing that's currently
        used here. targetUserOrChannel is potentially useful, while
        the 'data' argument is solely for informational purposes.)
        """
        self.client = client
        if queryData:
            self.queryData = queryData
            self.remoteParty = self.queryData[0]

    def dataReceived(self, data):
        self.buffer = self.buffer + data
        lines = self.buffer.split(LF)
        # Put the (possibly empty) element after the last LF back in the
        # buffer
        self.buffer = lines.pop()

        for line in lines:
            if line[-1] == CR:
                line = line[:-1]
            self.lineReceived(line)

    def lineReceived(self, line):
        log.msg(f"DCC CHAT<{self.remoteParty}> {line}")
        self.client.privmsg(self.remoteParty, self.client.nickname, line)


class DccChatFactory(protocol.ClientFactory):
    protocol = DccChat  # type: ignore[assignment]
    noisy = False

    def __init__(self, client, queryData):
        self.client = client
        self.queryData = queryData

    def buildProtocol(self, addr):
        p = self.protocol(client=self.client, queryData=self.queryData)
        p.factory = self
        return p

    def clientConnectionFailed(self, unused_connector, unused_reason):
        self.client.dcc_sessions.remove(self)

    def clientConnectionLost(self, unused_connector, unused_reason):
        self.client.dcc_sessions.remove(self)


def dccDescribe(data):
    """
    Given the data chunk from a DCC query, return a descriptive string.

    @param data: The data from a DCC query.
    @type data: L{bytes}

    @rtype: L{bytes}
    @return: A descriptive string.
    """

    orig_data = data
    data = data.split()
    if len(data) < 4:
        return orig_data

    (dcctype, arg, address, port) = data[:4]

    if "." in address:
        pass
    else:
        try:
            address = int(address)
        except ValueError:
            pass
        else:
            address = (
                (address >> 24) & 0xFF,
                (address >> 16) & 0xFF,
                (address >> 8) & 0xFF,
                address & 0xFF,
            )
            address = ".".join(map(str, address))

    if dcctype == "SEND":
        filename = arg

        size_txt = ""
        if len(data) >= 5:
            try:
                size = int(data[4])
                size_txt = " of size %d bytes" % (size,)
            except ValueError:
                pass

        dcc_text = "SEND for file '{}'{} at host {}, port {}".format(
            filename,
            size_txt,
            address,
            port,
        )
    elif dcctype == "CHAT":
        dcc_text = f"CHAT for host {address}, port {port}"
    else:
        dcc_text = orig_data

    return dcc_text


class DccFileReceive(DccFileReceiveBasic):
    """
    Higher-level coverage for getting a file from DCC SEND.

    I allow you to change the file's name and destination directory.  I won't
    overwrite an existing file unless I've been told it's okay to do so.  If
    passed the resumeOffset keyword argument I will attempt to resume the file
    from that amount of bytes.

    XXX: I need to let the client know when I am finished.
    XXX: I need to decide how to keep a progress indicator updated.
    XXX: Client needs a way to tell me "Do not finish until I say so."
    XXX: I need to make sure the client understands if the file cannot be written.

    @ivar filename: The name of the file to get.
    @type filename: L{bytes}

    @ivar fileSize: The size of the file to get, which has a default value of
        C{-1} if the size of the file was not specified in the DCC SEND
        request.
    @type fileSize: L{int}

    @ivar destDir: The destination directory for the file to be received.
    @type destDir: L{bytes}

    @ivar overwrite: An integer representing whether an existing file should be
        overwritten or not.  This initially is an L{int} but can be modified to
        be a L{bool} using the L{set_overwrite} method.
    @type overwrite: L{int} or L{bool}

    @ivar queryData: queryData is a 3-tuple of (user, channel, data).
    @type queryData: L{tuple}

    @ivar fromUser: This is the hostmask of the requesting user and is found at
        index 0 of L{queryData}.
    @type fromUser: L{bytes}
    """

    filename = "dcc"
    fileSize = -1
    destDir = "."
    overwrite = 0
    fromUser: Optional[bytes] = None
    queryData = None

    def __init__(
        self, filename, fileSize=-1, queryData=None, destDir=".", resumeOffset=0
    ):
        DccFileReceiveBasic.__init__(self, resumeOffset=resumeOffset)
        self.filename = filename
        self.destDir = destDir
        self.fileSize = fileSize
        self._resumeOffset = resumeOffset

        if queryData:
            self.queryData = queryData
            self.fromUser = self.queryData[0]

    def set_directory(self, directory):
        """
        Set the directory where the downloaded file will be placed.

        May raise OSError if the supplied directory path is not suitable.

        @param directory: The directory where the file to be received will be
            placed.
        @type directory: L{bytes}
        """
        if not path.exists(directory):
            raise OSError(errno.ENOENT, "You see no directory there.", directory)
        if not path.isdir(directory):
            raise OSError(
                errno.ENOTDIR,
                "You cannot put a file into " "something which is not a directory.",
                directory,
            )
        if not os.access(directory, os.X_OK | os.W_OK):
            raise OSError(
                errno.EACCES, "This directory is too hard to write in to.", directory
            )
        self.destDir = directory

    def set_filename(self, filename):
        """
        Change the name of the file being transferred.

        This replaces the file name provided by the sender.

        @param filename: The new name for the file.
        @type filename: L{bytes}
        """
        self.filename = filename

    def set_overwrite(self, boolean):
        """
        May I overwrite existing files?

        @param boolean: A boolean value representing whether existing files
            should be overwritten or not.
        @type boolean: L{bool}
        """
        self.overwrite = boolean

    # Protocol-level methods.

    def connectionMade(self):
        dst = path.abspath(path.join(self.destDir, self.filename))
        exists = path.exists(dst)
        if self.resume and exists:
            # I have been told I want to resume, and a file already
            # exists - Here we go
            self.file = open(dst, "rb+")
            self.file.seek(self._resumeOffset)
            self.file.truncate()
            log.msg(
                "Attempting to resume %s - starting from %d bytes"
                % (self.file, self.file.tell())
            )
        elif self.resume and not exists:
            raise OSError(
                errno.ENOENT,
                "You cannot resume writing to a file " "that does not exist!",
                dst,
            )
        elif self.overwrite or not exists:
            self.file = open(dst, "wb")
        else:
            raise OSError(
                errno.EEXIST,
                "There's a file in the way.  " "Perhaps that's why you cannot open it.",
                dst,
            )

    def dataReceived(self, data):
        self.file.write(data)
        DccFileReceiveBasic.dataReceived(self, data)

        # XXX: update a progress indicator here?

    def connectionLost(self, reason):
        """
        When the connection is lost, I close the file.

        @param reason: The reason why the connection was lost.
        @type reason: L{Failure}
        """
        self.connected = 0
        logmsg = f"{self} closed."
        if self.fileSize > 0:
            logmsg = "%s  %d/%d bytes received" % (
                logmsg,
                self.bytesReceived,
                self.fileSize,
            )
            if self.bytesReceived == self.fileSize:
                pass  # Hooray!
            elif self.bytesReceived < self.fileSize:
                logmsg = "%s (Warning: %d bytes short)" % (
                    logmsg,
                    self.fileSize - self.bytesReceived,
                )
            else:
                logmsg = f"{logmsg} (file larger than expected)"
        else:
            logmsg = "%s  %d bytes received" % (logmsg, self.bytesReceived)

        if hasattr(self, "file"):
            logmsg = f"{logmsg} and written to {self.file.name}.\n"
            if hasattr(self.file, "close"):
                self.file.close()

        # self.transport.log(logmsg)

    def __str__(self) -> str:
        if not self.connected:
            return f"<Unconnected DccFileReceive object at {id(self):x}>"
        transport = self.transport
        assert transport is not None
        from_ = str(transport.getPeer())
        if self.fromUser is not None:
            from_ = f"{self.fromUser!r} ({from_})"

        s = f"DCC transfer of '{self.filename}' from {from_}"
        return s

    def __repr__(self) -> str:
        s = f"<{self.__class__} at {id(self):x}: GET {self.filename}>"
        return s


_OFF = "\x0f"
_BOLD = "\x02"
_COLOR = "\x03"
_REVERSE_VIDEO = "\x16"
_UNDERLINE = "\x1f"

# Mapping of IRC color names to their color values.
_IRC_COLORS = dict(
    zip(
        [
            "white",
            "black",
            "blue",
            "green",
            "lightRed",
            "red",
            "magenta",
            "orange",
            "yellow",
            "lightGreen",
            "cyan",
            "lightCyan",
            "lightBlue",
            "lightMagenta",
            "gray",
            "lightGray",
        ],
        range(16),
    )
)

# Mapping of IRC color values to their color names.
_IRC_COLOR_NAMES = {code: name for name, code in _IRC_COLORS.items()}


class _CharacterAttributes(_textattributes.CharacterAttributesMixin):
    """
    Factory for character attributes, including foreground and background color
    and non-color attributes such as bold, reverse video and underline.

    Character attributes are applied to actual text by using object
    indexing-syntax (C{obj['abc']}) after accessing a factory attribute, for
    example::

        attributes.bold['Some text']

    These can be nested to mix attributes::

        attributes.bold[attributes.underline['Some text']]

    And multiple values can be passed::

        attributes.normal[attributes.bold['Some'], ' text']

    Non-color attributes can be accessed by attribute name, available
    attributes are:

        - bold
        - reverseVideo
        - underline

    Available colors are:

        0. white
        1. black
        2. blue
        3. green
        4. light red
        5. red
        6. magenta
        7. orange
        8. yellow
        9. light green
        10. cyan
        11. light cyan
        12. light blue
        13. light magenta
        14. gray
        15. light gray

    @ivar fg: Foreground colors accessed by attribute name, see above
        for possible names.

    @ivar bg: Background colors accessed by attribute name, see above
        for possible names.

    @since: 13.1
    """

    fg = _textattributes._ColorAttribute(
        _textattributes._ForegroundColorAttr, _IRC_COLORS
    )
    bg = _textattributes._ColorAttribute(
        _textattributes._BackgroundColorAttr, _IRC_COLORS
    )

    attrs = {"bold": _BOLD, "reverseVideo": _REVERSE_VIDEO, "underline": _UNDERLINE}


attributes = _CharacterAttributes()


class _FormattingState(_textattributes._FormattingStateMixin):
    """
    Formatting state/attributes of a single character.

    Attributes include:
        - Formatting nullifier
        - Bold
        - Underline
        - Reverse video
        - Foreground color
        - Background color

    @since: 13.1
    """

    compareAttributes = (
        "off",
        "bold",
        "underline",
        "reverseVideo",
        "foreground",
        "background",
    )

    def __init__(
        self,
        off=False,
        bold=False,
        underline=False,
        reverseVideo=False,
        foreground=None,
        background=None,
    ):
        self.off = off
        self.bold = bold
        self.underline = underline
        self.reverseVideo = reverseVideo
        self.foreground = foreground
        self.background = background

    def toMIRCControlCodes(self):
        """
        Emit a mIRC control sequence that will set up all the attributes this
        formatting state has set.

        @return: A string containing mIRC control sequences that mimic this
            formatting state.
        """
        attrs = []
        if self.bold:
            attrs.append(_BOLD)
        if self.underline:
            attrs.append(_UNDERLINE)
        if self.reverseVideo:
            attrs.append(_REVERSE_VIDEO)
        if self.foreground is not None or self.background is not None:
            c = ""
            if self.foreground is not None:
                c += "%02d" % (self.foreground,)
            if self.background is not None:
                c += ",%02d" % (self.background,)
            attrs.append(_COLOR + c)
        return _OFF + "".join(map(str, attrs))


def _foldr(f, z, xs):
    """
    Apply a function of two arguments cumulatively to the items of
    a sequence, from right to left, so as to reduce the sequence to
    a single value.

    @type f: C{callable} taking 2 arguments

    @param z: Initial value.

    @param xs: Sequence to reduce.

    @return: Single value resulting from reducing C{xs}.
    """
    return reduce(lambda x, y: f(y, x), reversed(xs), z)


class _FormattingParser(_CommandDispatcherMixin):
    """
    A finite-state machine that parses formatted IRC text.

    Currently handled formatting includes: bold, reverse, underline,
    mIRC color codes and the ability to remove all current formatting.

    @see: U{http://www.mirc.co.uk/help/color.txt}

    @type _formatCodes: C{dict} mapping C{str} to C{str}
    @cvar _formatCodes: Mapping of format code values to names.

    @type state: C{str}
    @ivar state: Current state of the finite-state machine.

    @type _buffer: C{str}
    @ivar _buffer: Buffer, containing the text content, of the formatting
        sequence currently being parsed, the buffer is used as the content for
        L{_attrs} before being added to L{_result} and emptied upon calling
        L{emit}.

    @type _attrs: C{set}
    @ivar _attrs: Set of the applicable formatting states (bold, underline,
        etc.) for the current L{_buffer}, these are applied to L{_buffer} when
        calling L{emit}.

    @type foreground: L{_ForegroundColorAttr}
    @ivar foreground: Current foreground color attribute, or L{None}.

    @type background: L{_BackgroundColorAttr}
    @ivar background: Current background color attribute, or L{None}.

    @ivar _result: Current parse result.
    """

    prefix = "state"

    _formatCodes = {
        _OFF: "off",
        _BOLD: "bold",
        _COLOR: "color",
        _REVERSE_VIDEO: "reverseVideo",
        _UNDERLINE: "underline",
    }

    def __init__(self):
        self.state = "TEXT"
        self._buffer = ""
        self._attrs = set()
        self._result = None
        self.foreground = None
        self.background = None

    def process(self, ch):
        """
        Handle input.

        @type ch: C{str}
        @param ch: A single character of input to process
        """
        self.dispatch(self.state, ch)

    def complete(self):
        """
        Flush the current buffer and return the final parsed result.

        @return: Structured text and attributes.
        """
        self.emit()
        if self._result is None:
            self._result = attributes.normal
        return self._result

    def emit(self):
        """
        Add the currently parsed input to the result.
        """
        if self._buffer:
            attrs = [getattr(attributes, name) for name in self._attrs]
            attrs.extend(filter(None, [self.foreground, self.background]))
            if not attrs:
                attrs.append(attributes.normal)
            attrs.append(self._buffer)

            attr = _foldr(operator.getitem, attrs.pop(), attrs)
            if self._result is None:
                self._result = attr
            else:
                self._result[attr]
            self._buffer = ""

    def state_TEXT(self, ch):
        """
        Handle the "text" state.

        Along with regular text, single token formatting codes are handled
        in this state too.

        @param ch: The character being processed.
        """
        formatName = self._formatCodes.get(ch)
        if formatName == "color":
            self.emit()
            self.state = "COLOR_FOREGROUND"
        else:
            if formatName is None:
                self._buffer += ch
            else:
                self.emit()
                if formatName == "off":
                    self._attrs = set()
                    self.foreground = self.background = None
                else:
                    self._attrs.symmetric_difference_update([formatName])

    def state_COLOR_FOREGROUND(self, ch):
        """
        Handle the foreground color state.

        Foreground colors can consist of up to two digits and may optionally
        end in a I{,}. Any non-digit or non-comma characters are treated as
        invalid input and result in the state being reset to "text".

        @param ch: The character being processed.
        """
        # Color codes may only be a maximum of two characters.
        if ch.isdigit() and len(self._buffer) < 2:
            self._buffer += ch
        else:
            if self._buffer:
                # Wrap around for color numbers higher than we support, like
                # most other IRC clients.
                col = int(self._buffer) % len(_IRC_COLORS)
                self.foreground = getattr(attributes.fg, _IRC_COLOR_NAMES[col])
            else:
                # If there were no digits, then this has been an empty color
                # code and we can reset the color state.
                self.foreground = self.background = None

            if ch == "," and self._buffer:
                # If there's a comma and it's not the first thing, move on to
                # the background state.
                self._buffer = ""
                self.state = "COLOR_BACKGROUND"
            else:
                # Otherwise, this is a bogus color code, fall back to text.
                self._buffer = ""
                self.state = "TEXT"
                self.emit()
                self.process(ch)

    def state_COLOR_BACKGROUND(self, ch):
        """
        Handle the background color state.

        Background colors can consist of up to two digits and must occur after
        a foreground color and must be preceded by a I{,}. Any non-digit
        character is treated as invalid input and results in the state being
        set to "text".

        @param ch: The character being processed.
        """
        # Color codes may only be a maximum of two characters.
        if ch.isdigit() and len(self._buffer) < 2:
            self._buffer += ch
        else:
            if self._buffer:
                # Wrap around for color numbers higher than we support, like
                # most other IRC clients.
                col = int(self._buffer) % len(_IRC_COLORS)
                self.background = getattr(attributes.bg, _IRC_COLOR_NAMES[col])
                self._buffer = ""

            self.emit()
            self.state = "TEXT"
            self.process(ch)


def parseFormattedText(text):
    """
    Parse text containing IRC formatting codes into structured information.

    Color codes are mapped from 0 to 15 and wrap around if greater than 15.

    @type text: C{str}
    @param text: Formatted text to parse.

    @return: Structured text and attributes.

    @since: 13.1
    """
    state = _FormattingParser()
    for ch in text:
        state.process(ch)
    return state.complete()


def assembleFormattedText(formatted):
    """
    Assemble formatted text from structured information.

    Currently handled formatting includes: bold, reverse, underline,
    mIRC color codes and the ability to remove all current formatting.

    It is worth noting that assembled text will always begin with the control
    code to disable other attributes for the sake of correctness.

    For example::

        from twisted.words.protocols.irc import attributes as A
        assembleFormattedText(
            A.normal[A.bold['Time: '], A.fg.lightRed['Now!']])

    Would produce "Time: " in bold formatting, followed by "Now!" with a
    foreground color of light red and without any additional formatting.

    Available attributes are:
        - bold
        - reverseVideo
        - underline

    Available colors are:
        0. white
        1. black
        2. blue
        3. green
        4. light red
        5. red
        6. magenta
        7. orange
        8. yellow
        9. light green
        10. cyan
        11. light cyan
        12. light blue
        13. light magenta
        14. gray
        15. light gray

    @see: U{http://www.mirc.co.uk/help/color.txt}

    @param formatted: Structured text and attributes.

    @rtype: C{str}
    @return: String containing mIRC control sequences that mimic those
        specified by I{formatted}.

    @since: 13.1
    """
    return _textattributes.flatten(formatted, _FormattingState(), "toMIRCControlCodes")


def stripFormatting(text):
    """
    Remove all formatting codes from C{text}, leaving only the text.

    @type text: C{str}
    @param text: Formatted text to parse.

    @rtype: C{str}
    @return: Plain text without any control sequences.

    @since: 13.1
    """
    formatted = parseFormattedText(text)
    return _textattributes.flatten(formatted, _textattributes.DefaultFormattingState())


# CTCP constants and helper functions

X_DELIM = chr(0o01)


def ctcpExtract(message):
    """
    Extract CTCP data from a string.

    @return: A C{dict} containing two keys:
       - C{'extended'}: A list of CTCP (tag, data) tuples.
       - C{'normal'}: A list of strings which were not inside a CTCP delimiter.
    """
    extended_messages = []
    normal_messages = []
    retval = {"extended": extended_messages, "normal": normal_messages}

    messages = message.split(X_DELIM)
    odd = 0

    # X1 extended data X2 nomal data X3 extended data X4 normal...
    while messages:
        if odd:
            extended_messages.append(messages.pop(0))
        else:
            normal_messages.append(messages.pop(0))
        odd = not odd

    extended_messages[:] = list(filter(None, extended_messages))
    normal_messages[:] = list(filter(None, normal_messages))

    extended_messages[:] = list(map(ctcpDequote, extended_messages))
    for i in range(len(extended_messages)):
        m = extended_messages[i].split(SPC, 1)
        tag = m[0]
        if len(m) > 1:
            data = m[1]
        else:
            data = None

        extended_messages[i] = (tag, data)

    return retval


# CTCP escaping

M_QUOTE = chr(0o20)

mQuoteTable = {
    NUL: M_QUOTE + "0",
    NL: M_QUOTE + "n",
    CR: M_QUOTE + "r",
    M_QUOTE: M_QUOTE + M_QUOTE,
}

mDequoteTable = {}
for k, v in mQuoteTable.items():
    mDequoteTable[v[-1]] = k
del k, v

mEscape_re = re.compile(f"{re.escape(M_QUOTE)}.", re.DOTALL)


def lowQuote(s):
    for c in (M_QUOTE, NUL, NL, CR):
        s = s.replace(c, mQuoteTable[c])
    return s


def lowDequote(s):
    def sub(matchobj, mDequoteTable=mDequoteTable):
        s = matchobj.group()[1]
        try:
            s = mDequoteTable[s]
        except KeyError:
            s = s
        return s

    return mEscape_re.sub(sub, s)


X_QUOTE = "\\"

xQuoteTable = {X_DELIM: X_QUOTE + "a", X_QUOTE: X_QUOTE + X_QUOTE}

xDequoteTable = {}

for k, v in xQuoteTable.items():
    xDequoteTable[v[-1]] = k

xEscape_re = re.compile(f"{re.escape(X_QUOTE)}.", re.DOTALL)


def ctcpQuote(s):
    for c in (X_QUOTE, X_DELIM):
        s = s.replace(c, xQuoteTable[c])
    return s


def ctcpDequote(s):
    def sub(matchobj, xDequoteTable=xDequoteTable):
        s = matchobj.group()[1]
        try:
            s = xDequoteTable[s]
        except KeyError:
            s = s
        return s

    return xEscape_re.sub(sub, s)


def ctcpStringify(messages):
    """
    @type messages: a list of extended messages.  An extended
    message is a (tag, data) tuple, where 'data' may be L{None}, a
    string, or a list of strings to be joined with whitespace.

    @returns: String
    """
    coded_messages = []
    for (tag, data) in messages:
        if data:
            if not isinstance(data, str):
                try:
                    # data as list-of-strings
                    data = " ".join(map(str, data))
                except TypeError:
                    # No?  Then use it's %s representation.
                    pass
            m = f"{tag} {data}"
        else:
            m = str(tag)
        m = ctcpQuote(m)
        m = f"{X_DELIM}{m}{X_DELIM}"
        coded_messages.append(m)

    line = "".join(coded_messages)
    return line


# Constants (from RFC 2812)
RPL_WELCOME = "001"
RPL_YOURHOST = "002"
RPL_CREATED = "003"
RPL_MYINFO = "004"
RPL_ISUPPORT = "005"
RPL_BOUNCE = "010"
RPL_USERHOST = "302"
RPL_ISON = "303"
RPL_AWAY = "301"
RPL_UNAWAY = "305"
RPL_NOWAWAY = "306"
RPL_WHOISUSER = "311"
RPL_WHOISSERVER = "312"
RPL_WHOISOPERATOR = "313"
RPL_WHOISIDLE = "317"
RPL_ENDOFWHOIS = "318"
RPL_WHOISCHANNELS = "319"
RPL_WHOWASUSER = "314"
RPL_ENDOFWHOWAS = "369"
RPL_LISTSTART = "321"
RPL_LIST = "322"
RPL_LISTEND = "323"
RPL_UNIQOPIS = "325"
RPL_CHANNELMODEIS = "324"
RPL_NOTOPIC = "331"
RPL_TOPIC = "332"
RPL_INVITING = "341"
RPL_SUMMONING = "342"
RPL_INVITELIST = "346"
RPL_ENDOFINVITELIST = "347"
RPL_EXCEPTLIST = "348"
RPL_ENDOFEXCEPTLIST = "349"
RPL_VERSION = "351"
RPL_WHOREPLY = "352"
RPL_ENDOFWHO = "315"
RPL_NAMREPLY = "353"
RPL_ENDOFNAMES = "366"
RPL_LINKS = "364"
RPL_ENDOFLINKS = "365"
RPL_BANLIST = "367"
RPL_ENDOFBANLIST = "368"
RPL_INFO = "371"
RPL_ENDOFINFO = "374"
RPL_MOTDSTART = "375"
RPL_MOTD = "372"
RPL_ENDOFMOTD = "376"
RPL_YOUREOPER = "381"
RPL_REHASHING = "382"
RPL_YOURESERVICE = "383"
RPL_TIME = "391"
RPL_USERSSTART = "392"
RPL_USERS = "393"
RPL_ENDOFUSERS = "394"
RPL_NOUSERS = "395"
RPL_TRACELINK = "200"
RPL_TRACECONNECTING = "201"
RPL_TRACEHANDSHAKE = "202"
RPL_TRACEUNKNOWN = "203"
RPL_TRACEOPERATOR = "204"
RPL_TRACEUSER = "205"
RPL_TRACESERVER = "206"
RPL_TRACESERVICE = "207"
RPL_TRACENEWTYPE = "208"
RPL_TRACECLASS = "209"
RPL_TRACERECONNECT = "210"
RPL_TRACELOG = "261"
RPL_TRACEEND = "262"
RPL_STATSLINKINFO = "211"
RPL_STATSCOMMANDS = "212"
RPL_ENDOFSTATS = "219"
RPL_STATSUPTIME = "242"
RPL_STATSOLINE = "243"
RPL_UMODEIS = "221"
RPL_SERVLIST = "234"
RPL_SERVLISTEND = "235"
RPL_LUSERCLIENT = "251"
RPL_LUSEROP = "252"
RPL_LUSERUNKNOWN = "253"
RPL_LUSERCHANNELS = "254"
RPL_LUSERME = "255"
RPL_ADMINME = "256"
RPL_ADMINLOC1 = "257"
RPL_ADMINLOC2 = "258"
RPL_ADMINEMAIL = "259"
RPL_TRYAGAIN = "263"
ERR_NOSUCHNICK = "401"
ERR_NOSUCHSERVER = "402"
ERR_NOSUCHCHANNEL = "403"
ERR_CANNOTSENDTOCHAN = "404"
ERR_TOOMANYCHANNELS = "405"
ERR_WASNOSUCHNICK = "406"
ERR_TOOMANYTARGETS = "407"
ERR_NOSUCHSERVICE = "408"
ERR_NOORIGIN = "409"
ERR_NORECIPIENT = "411"
ERR_NOTEXTTOSEND = "412"
ERR_NOTOPLEVEL = "413"
ERR_WILDTOPLEVEL = "414"
ERR_BADMASK = "415"
# Defined in errata.
# https://www.rfc-editor.org/errata_search.php?rfc=2812&eid=2822
ERR_TOOMANYMATCHES = "416"
ERR_UNKNOWNCOMMAND = "421"
ERR_NOMOTD = "422"
ERR_NOADMININFO = "423"
ERR_FILEERROR = "424"
ERR_NONICKNAMEGIVEN = "431"
ERR_ERRONEUSNICKNAME = "432"
ERR_NICKNAMEINUSE = "433"
ERR_NICKCOLLISION = "436"
ERR_UNAVAILRESOURCE = "437"
ERR_USERNOTINCHANNEL = "441"
ERR_NOTONCHANNEL = "442"
ERR_USERONCHANNEL = "443"
ERR_NOLOGIN = "444"
ERR_SUMMONDISABLED = "445"
ERR_USERSDISABLED = "446"
ERR_NOTREGISTERED = "451"
ERR_NEEDMOREPARAMS = "461"
ERR_ALREADYREGISTRED = "462"
ERR_NOPERMFORHOST = "463"
ERR_PASSWDMISMATCH = "464"
ERR_YOUREBANNEDCREEP = "465"
ERR_YOUWILLBEBANNED = "466"
ERR_KEYSET = "467"
ERR_CHANNELISFULL = "471"
ERR_UNKNOWNMODE = "472"
ERR_INVITEONLYCHAN = "473"
ERR_BANNEDFROMCHAN = "474"
ERR_BADCHANNELKEY = "475"
ERR_BADCHANMASK = "476"
ERR_NOCHANMODES = "477"
ERR_BANLISTFULL = "478"
ERR_NOPRIVILEGES = "481"
ERR_CHANOPRIVSNEEDED = "482"
ERR_CANTKILLSERVER = "483"
ERR_RESTRICTED = "484"
ERR_UNIQOPPRIVSNEEDED = "485"
ERR_NOOPERHOST = "491"
ERR_NOSERVICEHOST = "492"
ERR_UMODEUNKNOWNFLAG = "501"
ERR_USERSDONTMATCH = "502"

# And hey, as long as the strings are already intern'd...
symbolic_to_numeric = {
    "RPL_WELCOME": "001",
    "RPL_YOURHOST": "002",
    "RPL_CREATED": "003",
    "RPL_MYINFO": "004",
    "RPL_ISUPPORT": "005",
    "RPL_BOUNCE": "010",
    "RPL_USERHOST": "302",
    "RPL_ISON": "303",
    "RPL_AWAY": "301",
    "RPL_UNAWAY": "305",
    "RPL_NOWAWAY": "306",
    "RPL_WHOISUSER": "311",
    "RPL_WHOISSERVER": "312",
    "RPL_WHOISOPERATOR": "313",
    "RPL_WHOISIDLE": "317",
    "RPL_ENDOFWHOIS": "318",
    "RPL_WHOISCHANNELS": "319",
    "RPL_WHOWASUSER": "314",
    "RPL_ENDOFWHOWAS": "369",
    "RPL_LISTSTART": "321",
    "RPL_LIST": "322",
    "RPL_LISTEND": "323",
    "RPL_UNIQOPIS": "325",
    "RPL_CHANNELMODEIS": "324",
    "RPL_NOTOPIC": "331",
    "RPL_TOPIC": "332",
    "RPL_INVITING": "341",
    "RPL_SUMMONING": "342",
    "RPL_INVITELIST": "346",
    "RPL_ENDOFINVITELIST": "347",
    "RPL_EXCEPTLIST": "348",
    "RPL_ENDOFEXCEPTLIST": "349",
    "RPL_VERSION": "351",
    "RPL_WHOREPLY": "352",
    "RPL_ENDOFWHO": "315",
    "RPL_NAMREPLY": "353",
    "RPL_ENDOFNAMES": "366",
    "RPL_LINKS": "364",
    "RPL_ENDOFLINKS": "365",
    "RPL_BANLIST": "367",
    "RPL_ENDOFBANLIST": "368",
    "RPL_INFO": "371",
    "RPL_ENDOFINFO": "374",
    "RPL_MOTDSTART": "375",
    "RPL_MOTD": "372",
    "RPL_ENDOFMOTD": "376",
    "RPL_YOUREOPER": "381",
    "RPL_REHASHING": "382",
    "RPL_YOURESERVICE": "383",
    "RPL_TIME": "391",
    "RPL_USERSSTART": "392",
    "RPL_USERS": "393",
    "RPL_ENDOFUSERS": "394",
    "RPL_NOUSERS": "395",
    "RPL_TRACELINK": "200",
    "RPL_TRACECONNECTING": "201",
    "RPL_TRACEHANDSHAKE": "202",
    "RPL_TRACEUNKNOWN": "203",
    "RPL_TRACEOPERATOR": "204",
    "RPL_TRACEUSER": "205",
    "RPL_TRACESERVER": "206",
    "RPL_TRACESERVICE": "207",
    "RPL_TRACENEWTYPE": "208",
    "RPL_TRACECLASS": "209",
    "RPL_TRACERECONNECT": "210",
    "RPL_TRACELOG": "261",
    "RPL_TRACEEND": "262",
    "RPL_STATSLINKINFO": "211",
    "RPL_STATSCOMMANDS": "212",
    "RPL_ENDOFSTATS": "219",
    "RPL_STATSUPTIME": "242",
    "RPL_STATSOLINE": "243",
    "RPL_UMODEIS": "221",
    "RPL_SERVLIST": "234",
    "RPL_SERVLISTEND": "235",
    "RPL_LUSERCLIENT": "251",
    "RPL_LUSEROP": "252",
    "RPL_LUSERUNKNOWN": "253",
    "RPL_LUSERCHANNELS": "254",
    "RPL_LUSERME": "255",
    "RPL_ADMINME": "256",
    "RPL_ADMINLOC1": "257",
    "RPL_ADMINLOC2": "258",
    "RPL_ADMINEMAIL": "259",
    "RPL_TRYAGAIN": "263",
    "ERR_NOSUCHNICK": "401",
    "ERR_NOSUCHSERVER": "402",
    "ERR_NOSUCHCHANNEL": "403",
    "ERR_CANNOTSENDTOCHAN": "404",
    "ERR_TOOMANYCHANNELS": "405",
    "ERR_WASNOSUCHNICK": "406",
    "ERR_TOOMANYTARGETS": "407",
    "ERR_NOSUCHSERVICE": "408",
    "ERR_NOORIGIN": "409",
    "ERR_NORECIPIENT": "411",
    "ERR_NOTEXTTOSEND": "412",
    "ERR_NOTOPLEVEL": "413",
    "ERR_WILDTOPLEVEL": "414",
    "ERR_BADMASK": "415",
    "ERR_TOOMANYMATCHES": "416",
    "ERR_UNKNOWNCOMMAND": "421",
    "ERR_NOMOTD": "422",
    "ERR_NOADMININFO": "423",
    "ERR_FILEERROR": "424",
    "ERR_NONICKNAMEGIVEN": "431",
    "ERR_ERRONEUSNICKNAME": "432",
    "ERR_NICKNAMEINUSE": "433",
    "ERR_NICKCOLLISION": "436",
    "ERR_UNAVAILRESOURCE": "437",
    "ERR_USERNOTINCHANNEL": "441",
    "ERR_NOTONCHANNEL": "442",
    "ERR_USERONCHANNEL": "443",
    "ERR_NOLOGIN": "444",
    "ERR_SUMMONDISABLED": "445",
    "ERR_USERSDISABLED": "446",
    "ERR_NOTREGISTERED": "451",
    "ERR_NEEDMOREPARAMS": "461",
    "ERR_ALREADYREGISTRED": "462",
    "ERR_NOPERMFORHOST": "463",
    "ERR_PASSWDMISMATCH": "464",
    "ERR_YOUREBANNEDCREEP": "465",
    "ERR_YOUWILLBEBANNED": "466",
    "ERR_KEYSET": "467",
    "ERR_CHANNELISFULL": "471",
    "ERR_UNKNOWNMODE": "472",
    "ERR_INVITEONLYCHAN": "473",
    "ERR_BANNEDFROMCHAN": "474",
    "ERR_BADCHANNELKEY": "475",
    "ERR_BADCHANMASK": "476",
    "ERR_NOCHANMODES": "477",
    "ERR_BANLISTFULL": "478",
    "ERR_NOPRIVILEGES": "481",
    "ERR_CHANOPRIVSNEEDED": "482",
    "ERR_CANTKILLSERVER": "483",
    "ERR_RESTRICTED": "484",
    "ERR_UNIQOPPRIVSNEEDED": "485",
    "ERR_NOOPERHOST": "491",
    "ERR_NOSERVICEHOST": "492",
    "ERR_UMODEUNKNOWNFLAG": "501",
    "ERR_USERSDONTMATCH": "502",
}

numeric_to_symbolic = {}
for k, v in symbolic_to_numeric.items():
    numeric_to_symbolic[v] = k
