# -*- test-case-name: twisted.mail.test.test_pop3 -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Post-office Protocol version 3.

@author: Glyph Lefkowitz
@author: Jp Calderone
"""

import base64
import binascii
import warnings
from hashlib import md5
from typing import Optional

from zope.interface import implementer

from twisted import cred
from twisted.internet import defer, interfaces, task
from twisted.mail import smtp
from twisted.mail._except import POP3ClientError, POP3Error, _POP3MessageDeleted
from twisted.mail.interfaces import (
    IMailboxPOP3 as IMailbox,
    IServerFactoryPOP3 as IServerFactory,
)
from twisted.protocols import basic, policies
from twisted.python import log


# Authentication
@implementer(cred.credentials.IUsernameHashedPassword)
class APOPCredentials:
    """
    Credentials for use in APOP authentication.

    @ivar magic: See L{__init__}
    @ivar username: See L{__init__}
    @ivar digest: See L{__init__}
    """

    def __init__(self, magic, username, digest):
        """
        @type magic: L{bytes}
        @param magic: The challenge string used to encrypt the password.

        @type username: L{bytes}
        @param username: The username associated with these credentials.

        @type digest: L{bytes}
        @param digest: An encrypted version of the user's password.  Should be
            generated as an MD5 hash of the challenge string concatenated with
            the plaintext password.
        """
        self.magic = magic
        self.username = username
        self.digest = digest

    def checkPassword(self, password):
        """
        Validate a plaintext password against the credentials.

        @type password: L{bytes}
        @param password: A plaintext password.

        @rtype: L{bool}
        @return: C{True} if the credentials represented by this object match
        the given password, C{False} if they do not.
        """
        seed = self.magic + password
        myDigest = md5(seed).hexdigest()
        return myDigest == self.digest


class _HeadersPlusNLines:
    """
    A utility class to retrieve the header and some lines of the body of a mail
    message.

    @ivar _file: See L{__init__}
    @ivar _extraLines: See L{__init__}

    @type linecount: L{int}
    @ivar linecount: The number of full lines of the message body scanned.

    @type headers: L{bool}
    @ivar headers: An indication of which part of the message is being scanned.
        C{True} for the header and C{False} for the body.

    @type done: L{bool}
    @ivar done: A flag indicating when the desired part of the message has been
        scanned.

    @type buf: L{bytes}
    @ivar buf: The portion of the message body that has been scanned, up to
        C{n} lines.
    """

    def __init__(self, file, extraLines):
        """
        @type file: file-like object
        @param file: A file containing a mail message.

        @type extraLines: L{int}
        @param extraLines: The number of lines of the message body to retrieve.
        """
        self._file = file
        self._extraLines = extraLines
        self.linecount = 0
        self.headers = 1
        self.done = 0
        self.buf = b""

    def read(self, bytes):
        """
        Scan bytes from the file.

        @type bytes: L{int}
        @param bytes: The number of bytes to read from the file.

        @rtype: L{bytes}
        @return: Each portion of the header as it is scanned.  Then, full lines
            of the message body as they are scanned.  When more than one line
            of the header and/or body has been scanned, the result is the
            concatenation of the lines.  When the scan results in no full
            lines, the empty string is returned.
        """
        if self.done:
            return b""
        data = self._file.read(bytes)
        if not data:
            return data
        if self.headers:
            df, sz = data.find(b"\r\n\r\n"), 4
            if df == -1:
                df, sz = data.find(b"\n\n"), 2
            if df != -1:
                df += sz
                val = data[:df]
                data = data[df:]
                self.linecount = 1
                self.headers = 0
        else:
            val = b""
        if self.linecount > 0:
            dsplit = (self.buf + data).split(b"\n")
            self.buf = dsplit[-1]
            for ln in dsplit[:-1]:
                if self.linecount > self._extraLines:
                    self.done = 1
                    return val
                val += ln + b"\n"
                self.linecount += 1
            return val
        else:
            return data


class _IteratorBuffer:
    """
    An iterator which buffers the elements of a container and periodically
    passes them as input to a writer.

    @ivar write: See L{__init__}.
    @ivar memoryBufferSize: See L{__init__}.

    @type bufSize: L{int}
    @ivar bufSize: The number of bytes currently in the buffer.

    @type lines: L{list} of L{bytes}
    @ivar lines: The buffer, which is a list of strings.

    @type iterator: iterator which yields L{bytes}
    @ivar iterator: An iterator over a container of strings.
    """

    bufSize = 0

    def __init__(self, write, iterable, memoryBufferSize=None):
        """
        @type write: callable that takes L{list} of L{bytes}
        @param write: A writer which is a callable that takes a list of
            strings.

        @type iterable: iterable which yields L{bytes}
        @param iterable: An iterable container of strings.

        @type memoryBufferSize: L{int} or L{None}
        @param memoryBufferSize: The number of bytes to buffer before flushing
            the buffer to the writer.
        """
        self.lines = []
        self.write = write
        self.iterator = iter(iterable)
        if memoryBufferSize is None:
            memoryBufferSize = 2 ** 16
        self.memoryBufferSize = memoryBufferSize

    def __iter__(self):
        """
        Return an iterator.

        @rtype: iterator which yields L{bytes}
        @return: An iterator over strings.
        """
        return self

    def __next__(self):
        """
        Get the next string from the container, buffer it, and possibly send
        the buffer to the writer.

        The contents of the buffer are written when it is full or when no
        further values are available from the container.

        @raise StopIteration: When no further values are available from the
        container.
        """
        try:
            v = next(self.iterator)
        except StopIteration:
            if self.lines:
                self.write(self.lines)
            # Drop some references, in case they're edges in a cycle.
            del self.iterator, self.lines, self.write
            raise
        else:
            if v is not None:
                self.lines.append(v)
                self.bufSize += len(v)
                if self.bufSize > self.memoryBufferSize:
                    self.write(self.lines)
                    self.lines = []
                    self.bufSize = 0

    next = __next__


def iterateLineGenerator(proto, gen):
    """
    Direct the output of an iterator to the transport of a protocol and arrange
    for iteration to take place.

    @type proto: L{POP3}
    @param proto: A POP3 server protocol.

    @type gen: iterator which yields L{bytes}
    @param gen: An iterator over strings.

    @rtype: L{Deferred <defer.Deferred>}
    @return: A deferred which fires when the iterator finishes.
    """
    coll = _IteratorBuffer(proto.transport.writeSequence, gen)
    return proto.schedule(coll)


def successResponse(response):
    """
    Format an object as a positive response.

    @type response: stringifyable L{object}
    @param response: An object with a string representation.

    @rtype: L{bytes}
    @return: A positive POP3 response string.
    """
    if not isinstance(response, bytes):
        response = str(response).encode("utf-8")
    return b"+OK " + response + b"\r\n"


def formatStatResponse(msgs):
    """
    Format a list of message sizes into a STAT response.

    This generator function is intended to be used with
    L{Cooperator <twisted.internet.task.Cooperator>}.

    @type msgs: L{list} of L{int}
    @param msgs: A list of message sizes.

    @rtype: L{None} or L{bytes}
    @return: Yields none until a result is available, then a string that is
        suitable for use in a STAT response. The string consists of the number
        of messages and the total size of the messages in octets.
    """
    i = 0
    bytes = 0
    for size in msgs:
        i += 1
        bytes += size
        yield None
    yield successResponse(b"%d %d" % (i, bytes))


def formatListLines(msgs):
    """
    Format a list of message sizes for use in a LIST response.

    @type msgs: L{list} of L{int}
    @param msgs: A list of message sizes.

    @rtype: L{bytes}
    @return: Yields a series of strings that are suitable for use as scan
        listings in a LIST response. Each string consists of a message number
        and its size in octets.
    """
    i = 0
    for size in msgs:
        i += 1
        yield b"%d %d\r\n" % (i, size)


def formatListResponse(msgs):
    """
    Format a list of message sizes into a complete LIST response.

    This generator function is intended to be used with
    L{Cooperator <twisted.internet.task.Cooperator>}.

    @type msgs: L{list} of L{int}
    @param msgs: A list of message sizes.

    @rtype: L{bytes}
    @return: Yields a series of strings which make up a complete LIST response.
    """
    yield successResponse(b"%d" % (len(msgs),))
    yield from formatListLines(msgs)
    yield b".\r\n"


def formatUIDListLines(msgs, getUidl):
    """
    Format a list of message sizes for use in a UIDL response.

    @param msgs: See L{formatUIDListResponse}
    @param getUidl: See L{formatUIDListResponse}

    @rtype: L{bytes}
    @return: Yields a series of strings that are suitable for use as unique-id
        listings in a UIDL response. Each string consists of a message number
        and its unique id.
    """
    for i, m in enumerate(msgs):
        if m is not None:
            uid = getUidl(i)
            if not isinstance(uid, bytes):
                uid = str(uid).encode("utf-8")
            yield b"%d %b\r\n" % (i + 1, uid)


def formatUIDListResponse(msgs, getUidl):
    """
    Format a list of message sizes into a complete UIDL response.

    This generator function is intended to be used with
    L{Cooperator <twisted.internet.task.Cooperator>}.

    @type msgs: L{list} of L{int}
    @param msgs: A list of message sizes.

    @type getUidl: one-argument callable returning bytes
    @param getUidl: A callable which takes a message index number and returns
        the UID of the corresponding message in the mailbox.

    @rtype: L{bytes}
    @return: Yields a series of strings which make up a complete UIDL response.
    """
    yield successResponse("")
    yield from formatUIDListLines(msgs, getUidl)
    yield b".\r\n"


@implementer(interfaces.IProducer)
class POP3(basic.LineOnlyReceiver, policies.TimeoutMixin):
    """
    A POP3 server protocol.

    @type portal: L{Portal}
    @ivar portal: A portal for authentication.

    @type factory: L{IServerFactory} provider
    @ivar factory: A server factory which provides an interface for querying
        capabilities of the server.

    @type timeOut: L{int}
    @ivar timeOut: The number of seconds to wait for a command from the client
        before disconnecting.

    @type schedule: callable that takes interator and returns
        L{Deferred <defer.Deferred>}
    @ivar schedule: A callable that arranges for an iterator to be
        cooperatively iterated over along with all other iterators which have
        been passed to it such that runtime is divided between all of them.  It
        returns a deferred which fires when the iterator finishes.

    @type magic: L{bytes} or L{None}
    @ivar magic: An APOP challenge.  If not set, an APOP challenge string
        will be generated when a connection is made.

    @type _userIs: L{bytes} or L{None}
    @ivar _userIs: The username sent with the USER command.

    @type _onLogout: no-argument callable or L{None}
    @ivar _onLogout: The function to be executed when the connection is
        lost.

    @type mbox: L{IMailbox} provider
    @ivar mbox: The mailbox for the authenticated user.

    @type state: L{bytes}
    @ivar state: The state which indicates what type of messages are expected
        from the client.  Valid states are 'COMMAND' and 'AUTH'

    @type blocked: L{None} or L{list} of 2-L{tuple} of
        (E{1}) L{bytes} (E{2}) L{tuple} of L{bytes}
    @ivar blocked: A list of blocked commands.  While a response to a command
        is being generated by the server, other commands are blocked.  When
        no command is outstanding, C{blocked} is set to none.  Otherwise, it
        contains a list of information about blocked commands.  Each list
        entry consists of the command and the arguments to the command.

    @type _highest: L{int}
    @ivar _highest: The 1-based index of the highest message retrieved.

    @type _auth: L{IUsernameHashedPassword
        <cred.credentials.IUsernameHashedPassword>} provider
    @ivar _auth: Authorization credentials.
    """

    magic: Optional[bytes] = None
    _userIs = None
    _onLogout = None

    AUTH_CMDS = [b"CAPA", b"USER", b"PASS", b"APOP", b"AUTH", b"RPOP", b"QUIT"]

    portal = None
    factory = None

    # The mailbox we're serving
    mbox = None

    # Set this pretty low -- POP3 clients are expected to log in, download
    # everything, and log out.
    timeOut = 300

    state = "COMMAND"

    # PIPELINE
    blocked = None

    # Cooperate and suchlike.
    schedule = staticmethod(task.coiterate)

    _highest = 0

    def connectionMade(self):
        """
        Send a greeting to the client after the connection has been made.
        """
        if self.magic is None:
            self.magic = self.generateMagic()
        self.successResponse(self.magic)
        self.setTimeout(self.timeOut)
        if getattr(self.factory, "noisy", True):
            log.msg("New connection from " + str(self.transport.getPeer()))

    def connectionLost(self, reason):
        """
        Clean up when the connection has been lost.

        @type reason: L{Failure}
        @param reason: The reason the connection was terminated.
        """
        if self._onLogout is not None:
            self._onLogout()
            self._onLogout = None
        self.setTimeout(None)

    def generateMagic(self):
        """
        Generate an APOP challenge.

        @rtype: L{bytes}
        @return: An RFC 822 message id format string.
        """
        return smtp.messageid()

    def successResponse(self, message=""):
        """
        Send a response indicating success.

        @type message: stringifyable L{object}
        @param message: An object whose string representation should be
            included in the response.
        """
        self.transport.write(successResponse(message))

    def failResponse(self, message=b""):
        """
        Send a response indicating failure.

        @type message: stringifyable L{object}
        @param message: An object whose string representation should be
            included in the response.
        """
        if not isinstance(message, bytes):
            message = str(message).encode("utf-8")
        self.sendLine(b"-ERR " + message)

    def lineReceived(self, line):
        """
        Pass a received line to a state machine function.

        @type line: L{bytes}
        @param line: A received line.
        """
        self.resetTimeout()
        getattr(self, "state_" + self.state)(line)

    def _unblock(self, _):
        """
        Process as many blocked commands as possible.

        If there are no more blocked commands, set up for the next command to
        be sent immediately.

        @type _: L{object}
        @param _: Ignored.
        """
        commands = self.blocked
        self.blocked = None
        while commands and self.blocked is None:
            cmd, args = commands.pop(0)
            self.processCommand(cmd, *args)
        if self.blocked is not None:
            self.blocked.extend(commands)

    def state_COMMAND(self, line):
        """
        Handle received lines for the COMMAND state in which commands from the
        client are expected.

        @type line: L{bytes}
        @param line: A received command.
        """
        try:
            return self.processCommand(*line.split(b" "))
        except (ValueError, AttributeError, POP3Error, TypeError) as e:
            log.err()
            self.failResponse(
                b": ".join(
                    [
                        b"bad protocol or server",
                        e.__class__.__name__.encode("utf-8"),
                        b"".join(e.args),
                    ]
                )
            )

    def processCommand(self, command, *args):
        """
        Dispatch a command from the client for handling.

        @type command: L{bytes}
        @param command: A POP3 command.

        @type args: L{tuple} of L{bytes}
        @param args: Arguments to the command.

        @raise POP3Error: When the command is invalid or the command requires
            prior authentication which hasn't been performed.
        """
        if self.blocked is not None:
            self.blocked.append((command, args))
            return

        command = command.upper()
        authCmd = command in self.AUTH_CMDS
        if not self.mbox and not authCmd:
            raise POP3Error(b"not authenticated yet: cannot do " + command)
        f = getattr(self, "do_" + command.decode("utf-8"), None)
        if f:
            return f(*args)
        raise POP3Error(b"Unknown protocol command: " + command)

    def listCapabilities(self):
        """
        Return a list of server capabilities suitable for use in a CAPA
        response.

        @rtype: L{list} of L{bytes}
        @return: A list of server capabilities.
        """
        baseCaps = [
            b"TOP",
            b"USER",
            b"UIDL",
            b"PIPELINE",
            b"CELERITY",
            b"AUSPEX",
            b"POTENCE",
        ]

        if IServerFactory.providedBy(self.factory):
            # Oh my god.  We can't just loop over a list of these because
            # each has spectacularly different return value semantics!
            try:
                v = self.factory.cap_IMPLEMENTATION()
                if v and not isinstance(v, bytes):
                    v = str(v).encode("utf-8")
            except NotImplementedError:
                pass
            except BaseException:
                log.err()
            else:
                baseCaps.append(b"IMPLEMENTATION " + v)

            try:
                v = self.factory.cap_EXPIRE()
                if v and not isinstance(v, bytes):
                    v = str(v).encode("utf-8")
            except NotImplementedError:
                pass
            except BaseException:
                log.err()
            else:
                if v is None:
                    v = b"NEVER"
                if self.factory.perUserExpiration():
                    if self.mbox:
                        v = str(self.mbox.messageExpiration).encode("utf-8")
                    else:
                        v = v + b" USER"
                baseCaps.append(b"EXPIRE " + v)

            try:
                v = self.factory.cap_LOGIN_DELAY()
                if v and not isinstance(v, bytes):
                    v = str(v).encode("utf-8")
            except NotImplementedError:
                pass
            except BaseException:
                log.err()
            else:
                if self.factory.perUserLoginDelay():
                    if self.mbox:
                        v = str(self.mbox.loginDelay).encode("utf-8")
                    else:
                        v = v + b" USER"
                baseCaps.append(b"LOGIN-DELAY " + v)

            try:
                v = self.factory.challengers
            except AttributeError:
                pass
            except BaseException:
                log.err()
            else:
                baseCaps.append(b"SASL " + b" ".join(v.keys()))
        return baseCaps

    def do_CAPA(self):
        """
        Handle a CAPA command.

        Respond with the server capabilities.
        """
        self.successResponse(b"I can do the following:")
        for cap in self.listCapabilities():
            self.sendLine(cap)
        self.sendLine(b".")

    def do_AUTH(self, args=None):
        """
        Handle an AUTH command.

        If the AUTH extension is not supported, send an error response.  If an
        authentication mechanism was not specified in the command, send a list
        of all supported authentication methods.  Otherwise, send an
        authentication challenge to the client and transition to the
        AUTH state.

        @type args: L{bytes} or L{None}
        @param args: The name of an authentication mechanism.
        """
        if not getattr(self.factory, "challengers", None):
            self.failResponse(b"AUTH extension unsupported")
            return

        if args is None:
            self.successResponse("Supported authentication methods:")
            for a in self.factory.challengers:
                self.sendLine(a.upper())
            self.sendLine(b".")
            return

        auth = self.factory.challengers.get(args.strip().upper())
        if not self.portal or not auth:
            self.failResponse(b"Unsupported SASL selected")
            return

        self._auth = auth()
        chal = self._auth.getChallenge()

        self.sendLine(b"+ " + base64.b64encode(chal))
        self.state = "AUTH"

    def state_AUTH(self, line):
        """
        Handle received lines for the AUTH state in which an authentication
        challenge response from the client is expected.

        Transition back to the COMMAND state.  Check the credentials and
        complete the authorization process with the L{_cbMailbox}
        callback function on success or the L{_ebMailbox} and L{_ebUnexpected}
        errback functions on failure.

        @type line: L{bytes}
        @param line: The challenge response.
        """
        self.state = "COMMAND"
        try:
            parts = base64.b64decode(line).split(None, 1)
        except binascii.Error:
            self.failResponse(b"Invalid BASE64 encoding")
        else:
            if len(parts) != 2:
                self.failResponse(b"Invalid AUTH response")
                return
            self._auth.username = parts[0]
            self._auth.response = parts[1]
            d = self.portal.login(self._auth, None, IMailbox)
            d.addCallback(self._cbMailbox, parts[0])
            d.addErrback(self._ebMailbox)
            d.addErrback(self._ebUnexpected)

    def do_APOP(self, user, digest):
        """
        Handle an APOP command.

        Perform APOP authentication and complete the authorization process with
        the L{_cbMailbox} callback function on success or the L{_ebMailbox}
        and L{_ebUnexpected} errback functions on failure.

        @type user: L{bytes}
        @param user: A username.

        @type digest: L{bytes}
        @param digest: An MD5 digest string.
        """
        d = defer.maybeDeferred(self.authenticateUserAPOP, user, digest)
        d.addCallbacks(
            self._cbMailbox, self._ebMailbox, callbackArgs=(user,)
        ).addErrback(self._ebUnexpected)

    def _cbMailbox(self, result, user):
        """
        Complete successful authentication.

        Save the mailbox and logout function for the authenticated user and
        send a successful response to the client.

        @type result: C{tuple}
        @param result: The first item of the tuple is a
            C{zope.interface.Interface} which is the interface
            supported by the avatar.  The second item of the tuple is a
            L{IMailbox} provider which is the mailbox for the
            authenticated user.  The third item of the tuple is a no-argument
            callable which is a function to be invoked when the session is
            terminated.

        @type user: L{bytes}
        @param user: The user being authenticated.
        """
        (interface, avatar, logout) = result
        if interface is not IMailbox:
            self.failResponse(b"Authentication failed")
            log.err("_cbMailbox() called with an interface other than IMailbox")
            return

        self.mbox = avatar
        self._onLogout = logout
        self.successResponse("Authentication succeeded")
        if getattr(self.factory, "noisy", True):
            log.msg(b"Authenticated login for " + user)

    def _ebMailbox(self, failure):
        """
        Handle an expected authentication failure.

        Send an appropriate error response for a L{LoginDenied} or
        L{LoginFailed} authentication failure.

        @type failure: L{Failure}
        @param failure: The authentication error.
        """
        failure = failure.trap(cred.error.LoginDenied, cred.error.LoginFailed)
        if issubclass(failure, cred.error.LoginDenied):
            self.failResponse("Access denied: " + str(failure))
        elif issubclass(failure, cred.error.LoginFailed):
            self.failResponse(b"Authentication failed")
        if getattr(self.factory, "noisy", True):
            log.msg("Denied login attempt from " + str(self.transport.getPeer()))

    def _ebUnexpected(self, failure):
        """
        Handle an unexpected authentication failure.

        Send an error response for an unexpected authentication failure.

        @type failure: L{Failure}
        @param failure: The authentication error.
        """
        self.failResponse("Server error: " + failure.getErrorMessage())
        log.err(failure)

    def do_USER(self, user):
        """
        Handle a USER command.

        Save the username and send a successful response prompting the client
        for the password.

        @type user: L{bytes}
        @param user: A username.
        """
        self._userIs = user
        self.successResponse(b"USER accepted, send PASS")

    def do_PASS(self, password, *words):
        """
        Handle a PASS command.

        If a USER command was previously received, authenticate the user and
        complete the authorization process with the L{_cbMailbox} callback
        function on success or the L{_ebMailbox} and L{_ebUnexpected} errback
        functions on failure.  If a USER command was not previously received,
        send an error response.

        @type password: L{bytes}
        @param password: A password.

        @type words: L{tuple} of L{bytes}
        @param words: Other parts of the password split by spaces.
        """
        if self._userIs is None:
            self.failResponse(b"USER required before PASS")
            return
        user = self._userIs
        self._userIs = None
        password = b" ".join((password,) + words)
        d = defer.maybeDeferred(self.authenticateUserPASS, user, password)
        d.addCallbacks(
            self._cbMailbox, self._ebMailbox, callbackArgs=(user,)
        ).addErrback(self._ebUnexpected)

    def _longOperation(self, d):
        """
        Stop timeouts and block further command processing while a long
        operation completes.

        @type d: L{Deferred <defer.Deferred>}
        @param d: A deferred which triggers at the completion of a long
            operation.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which triggers after command processing resumes and
            timeouts restart after the completion of a long operation.
        """
        timeOut = self.timeOut
        self.setTimeout(None)
        self.blocked = []
        d.addCallback(self._unblock)
        d.addCallback(lambda ign: self.setTimeout(timeOut))
        return d

    def _coiterate(self, gen):
        """
        Direct the output of an iterator to the transport and arrange for
        iteration to take place.

        @type gen: iterable which yields L{bytes}
        @param gen: An iterator over strings.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which fires when the iterator finishes.
        """
        return self.schedule(_IteratorBuffer(self.transport.writeSequence, gen))

    def do_STAT(self):
        """
        Handle a STAT command.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which triggers after the response to the STAT
            command has been issued.
        """
        d = defer.maybeDeferred(self.mbox.listMessages)

        def cbMessages(msgs):
            return self._coiterate(formatStatResponse(msgs))

        def ebMessages(err):
            self.failResponse(err.getErrorMessage())
            log.msg("Unexpected do_STAT failure:")
            log.err(err)

        return self._longOperation(d.addCallbacks(cbMessages, ebMessages))

    def do_LIST(self, i=None):
        """
        Handle a LIST command.

        @type i: L{bytes} or L{None}
        @param i: A 1-based message index.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which triggers after the response to the LIST
            command has been issued.
        """
        if i is None:
            d = defer.maybeDeferred(self.mbox.listMessages)

            def cbMessages(msgs):
                return self._coiterate(formatListResponse(msgs))

            def ebMessages(err):
                self.failResponse(err.getErrorMessage())
                log.msg("Unexpected do_LIST failure:")
                log.err(err)

            return self._longOperation(d.addCallbacks(cbMessages, ebMessages))
        else:
            try:
                i = int(i)
                if i < 1:
                    raise ValueError()
            except ValueError:
                if not isinstance(i, bytes):
                    i = str(i).encode("utf-8")
                self.failResponse(b"Invalid message-number: " + i)
            else:
                d = defer.maybeDeferred(self.mbox.listMessages, i - 1)

                def cbMessage(msg):
                    self.successResponse(b"%d %d" % (i, msg))

                def ebMessage(err):
                    errcls = err.check(ValueError, IndexError)
                    if errcls is not None:
                        if errcls is IndexError:
                            # IndexError was supported for a while, but really
                            # shouldn't be.  One error condition, one exception
                            # type.  See ticket #6669.
                            warnings.warn(
                                "twisted.mail.pop3.IMailbox.listMessages may "
                                "not raise IndexError for out-of-bounds "
                                "message numbers: raise ValueError instead.",
                                PendingDeprecationWarning,
                            )
                        invalidNum = i
                        if invalidNum and not isinstance(invalidNum, bytes):
                            invalidNum = str(invalidNum).encode("utf-8")
                        self.failResponse(b"Invalid message-number: " + invalidNum)
                    else:
                        self.failResponse(err.getErrorMessage())
                        log.msg("Unexpected do_LIST failure:")
                        log.err(err)

                d.addCallbacks(cbMessage, ebMessage)
                return self._longOperation(d)

    def do_UIDL(self, i=None):
        """
        Handle a UIDL command.

        @type i: L{bytes} or L{None}
        @param i: A 1-based message index.

        @rtype: L{Deferred <defer.Deferred>}
        @return: A deferred which triggers after the response to the UIDL
            command has been issued.
        """
        if i is None:
            d = defer.maybeDeferred(self.mbox.listMessages)

            def cbMessages(msgs):
                return self._coiterate(
                    formatUIDListResponse(msgs, self.mbox.getUidl),
                )

            def ebMessages(err):
                self.failResponse(err.getErrorMessage())
                log.msg("Unexpected do_UIDL failure:")
                log.err(err)

            return self._longOperation(d.addCallbacks(cbMessages, ebMessages))
        else:
            try:
                i = int(i)
                if i < 1:
                    raise ValueError()
            except ValueError:
                self.failResponse("Bad message number argument")
            else:
                try:
                    msg = self.mbox.getUidl(i - 1)
                except IndexError:
                    # XXX TODO See above comment regarding IndexError.
                    warnings.warn(
                        "twisted.mail.pop3.IMailbox.getUidl may not "
                        "raise IndexError for out-of-bounds message numbers: "
                        "raise ValueError instead.",
                        PendingDeprecationWarning,
                    )
                    self.failResponse("Bad message number argument")
                except ValueError:
                    self.failResponse("Bad message number argument")
                else:
                    if not isinstance(msg, bytes):
                        msg = str(msg).encode("utf-8")
                    self.successResponse(msg)

    def _getMessageFile(self, i):
        """
        Retrieve the size and contents of a message.

        @type i: L{bytes}
        @param i: A 1-based message index.

        @rtype: L{Deferred <defer.Deferred>} which successfully fires with
            2-L{tuple} of (E{1}) L{int}, (E{2}) file-like object
        @return: A deferred which successfully fires with the size of the
            message and a file containing the contents of the message.
        """
        try:
            msg = int(i) - 1
            if msg < 0:
                raise ValueError()
        except ValueError:
            self.failResponse("Bad message number argument")
            return defer.succeed(None)

        sizeDeferred = defer.maybeDeferred(self.mbox.listMessages, msg)

        def cbMessageSize(size):
            if not size:
                return defer.fail(_POP3MessageDeleted())
            fileDeferred = defer.maybeDeferred(self.mbox.getMessage, msg)
            fileDeferred.addCallback(lambda fObj: (size, fObj))
            return fileDeferred

        def ebMessageSomething(err):
            errcls = err.check(_POP3MessageDeleted, ValueError, IndexError)
            if errcls is _POP3MessageDeleted:
                self.failResponse("message deleted")
            elif errcls in (ValueError, IndexError):
                if errcls is IndexError:
                    # XXX TODO See above comment regarding IndexError.
                    warnings.warn(
                        "twisted.mail.pop3.IMailbox.listMessages may not "
                        "raise IndexError for out-of-bounds message numbers: "
                        "raise ValueError instead.",
                        PendingDeprecationWarning,
                    )
                self.failResponse("Bad message number argument")
            else:
                log.msg("Unexpected _getMessageFile failure:")
                log.err(err)
            return None

        sizeDeferred.addCallback(cbMessageSize)
        sizeDeferred.addErrback(ebMessageSomething)
        return sizeDeferred

    def _sendMessageContent(self, i, fpWrapper, successResponse):
        """
        Send the contents of a message.

        @type i: L{bytes}
        @param i: A 1-based message index.

        @type fpWrapper: callable that takes a file-like object and returns
            a file-like object
        @param fpWrapper:

        @type successResponse: callable that takes L{int} and returns
            L{bytes}
        @param successResponse:

        @rtype: L{Deferred}
        @return: A deferred which triggers after the message has been sent.
        """
        d = self._getMessageFile(i)

        def cbMessageFile(info):
            if info is None:
                # Some error occurred - a failure response has been sent
                # already, just give up.
                return

            self._highest = max(self._highest, int(i))
            resp, fp = info
            fp = fpWrapper(fp)
            self.successResponse(successResponse(resp))
            s = basic.FileSender()
            d = s.beginFileTransfer(fp, self.transport, self.transformChunk)

            def cbFileTransfer(lastsent):
                if lastsent != b"\n":
                    line = b"\r\n."
                else:
                    line = b"."
                self.sendLine(line)

            def ebFileTransfer(err):
                self.transport.loseConnection()
                log.msg("Unexpected error in _sendMessageContent:")
                log.err(err)

            d.addCallback(cbFileTransfer)
            d.addErrback(ebFileTransfer)
            return d

        return self._longOperation(d.addCallback(cbMessageFile))

    def do_TOP(self, i, size):
        """
        Handle a TOP command.

        @type i: L{bytes}
        @param i: A 1-based message index.

        @type size: L{bytes}
        @param size: The number of lines of the message to retrieve.

        @rtype: L{Deferred}
        @return: A deferred which triggers after the response to the TOP
            command has been issued.
        """
        try:
            size = int(size)
            if size < 0:
                raise ValueError
        except ValueError:
            self.failResponse("Bad line count argument")
        else:
            return self._sendMessageContent(
                i,
                lambda fp: _HeadersPlusNLines(fp, size),
                lambda size: "Top of message follows",
            )

    def do_RETR(self, i):
        """
        Handle a RETR command.

        @type i: L{bytes}
        @param i: A 1-based message index.

        @rtype: L{Deferred}
        @return: A deferred which triggers after the response to the RETR
            command has been issued.
        """
        return self._sendMessageContent(i, lambda fp: fp, lambda size: "%d" % (size,))

    def transformChunk(self, chunk):
        """
        Transform a chunk of a message to POP3 message format.

        Make sure each line ends with C{'\\r\\n'} and byte-stuff the
        termination character (C{'.'}) by adding an extra one when one appears
        at the beginning of a line.

        @type chunk: L{bytes}
        @param chunk: A string to transform.

        @rtype: L{bytes}
        @return: The transformed string.
        """
        return chunk.replace(b"\n", b"\r\n").replace(b"\r\n.", b"\r\n..")

    def finishedFileTransfer(self, lastsent):
        """
        Send the termination sequence.

        @type lastsent: L{bytes}
        @param lastsent: The last character of the file.
        """
        if lastsent != b"\n":
            line = b"\r\n."
        else:
            line = b"."
        self.sendLine(line)

    def do_DELE(self, i):
        """
        Handle a DELE command.

        Mark a message for deletion and issue a successful response.

        @type i: L{int}
        @param i: A 1-based message index.
        """
        i = int(i) - 1
        self.mbox.deleteMessage(i)
        self.successResponse()

    def do_NOOP(self):
        """
        Handle a NOOP command.

        Do nothing but issue a successful response.
        """
        self.successResponse()

    def do_RSET(self):
        """
        Handle a RSET command.

        Unmark any messages that have been flagged for deletion.
        """
        try:
            self.mbox.undeleteMessages()
        except BaseException:
            log.err()
            self.failResponse()
        else:
            self._highest = 0
            self.successResponse()

    def do_LAST(self):
        """
        Handle a LAST command.

        Respond with the 1-based index of the highest retrieved message.
        """
        self.successResponse(self._highest)

    def do_RPOP(self, user):
        """
        Handle an RPOP command.

        RPOP is not supported.  Send an error response.

        @type user: L{bytes}
        @param user: A username.

        """
        self.failResponse("permission denied, sucker")

    def do_QUIT(self):
        """
        Handle a QUIT command.

        Remove any messages marked for deletion, issue a successful response,
        and drop the connection.
        """
        if self.mbox:
            self.mbox.sync()
        self.successResponse()
        self.transport.loseConnection()

    def authenticateUserAPOP(self, user, digest):
        """
        Perform APOP authentication.

        @type user: L{bytes}
        @param user: The name of the user attempting to log in.

        @type digest: L{bytes}
        @param digest: The challenge response.

        @rtype: L{Deferred <defer.Deferred>} which successfully results in
            3-L{tuple} of (E{1}) L{IMailbox <pop3.IMailbox>}, (E{2})
            L{IMailbox <pop3.IMailbox>} provider, (E{3}) no-argument callable
        @return: A deferred which fires when authentication is complete.  If
            successful, it returns an L{IMailbox <pop3.IMailbox>} interface, a
            mailbox, and a function to be invoked with the session is
            terminated.  If authentication fails, the deferred fails with an
            L{UnathorizedLogin <cred.error.UnauthorizedLogin>} error.

        @raise cred.error.UnauthorizedLogin: When authentication fails.
        """
        if self.portal is not None:
            return self.portal.login(
                APOPCredentials(self.magic, user, digest), None, IMailbox
            )
        raise cred.error.UnauthorizedLogin()

    def authenticateUserPASS(self, user, password):
        """
        Perform authentication for a username/password login.

        @type user: L{bytes}
        @param user: The name of the user attempting to log in.

        @type password: L{bytes}
        @param password: The password to authenticate with.

        @rtype: L{Deferred <defer.Deferred>} which successfully results in
            3-L{tuple} of (E{1}) L{IMailbox <pop3.IMailbox>}, (E{2}) L{IMailbox
            <pop3.IMailbox>} provider, (E{3}) no-argument callable
        @return: A deferred which fires when authentication is complete.  If
            successful, it returns a L{pop3.IMailbox} interface, a mailbox,
            and a function to be invoked with the session is terminated.
            If authentication fails, the deferred fails with an
            L{UnathorizedLogin <cred.error.UnauthorizedLogin>} error.

        @raise cred.error.UnauthorizedLogin: When authentication fails.
        """
        if self.portal is not None:
            return self.portal.login(
                cred.credentials.UsernamePassword(user, password), None, IMailbox
            )
        raise cred.error.UnauthorizedLogin()

    def stopProducing(self):
        # IProducer.stopProducing
        raise NotImplementedError()


@implementer(IMailbox)
class Mailbox:
    """
    A base class for mailboxes.
    """

    def listMessages(self, i=None):
        """
        Retrieve the size of a message, or, if none is specified, the size of
        each message in the mailbox.

        @type i: L{int} or L{None}
        @param i: The 0-based index of the message.

        @rtype: L{int}, sequence of L{int}, or L{Deferred <defer.Deferred>}
        @return: The number of octets in the specified message, or, if an
            index is not specified, a sequence of the number of octets for
            all messages in the mailbox or a deferred which fires with
            one of those. Any value which corresponds to a deleted message
            is set to 0.

        @raise ValueError or IndexError: When the index does not correspond to
            a message in the mailbox.  The use of ValueError is preferred.
        """
        return []

    def getMessage(self, i):
        """
        Retrieve a file containing the contents of a message.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @rtype: file-like object
        @return: A file containing the message.

        @raise ValueError or IndexError: When the index does not correspond to
            a message in the mailbox.  The use of ValueError is preferred.
        """
        raise ValueError

    def getUidl(self, i):
        """
        Get a unique identifier for a message.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @rtype: L{bytes}
        @return: A string of printable characters uniquely identifying the
            message for all time.

        @raise ValueError or IndexError: When the index does not correspond to
            a message in the mailbox.  The use of ValueError is preferred.
        """
        raise ValueError

    def deleteMessage(self, i):
        """
        Mark a message for deletion.

        This must not change the number of messages in this mailbox.  Further
        requests for the size of the deleted message should return 0.  Further
        requests for the message itself may raise an exception.

        @type i: L{int}
        @param i: The 0-based index of a message.

        @raise ValueError or IndexError: When the index does not correspond to
            a message in the mailbox.  The use of ValueError is preferred.
        """
        raise ValueError

    def undeleteMessages(self):
        """
        Undelete all messages marked for deletion.

        Any message which can be undeleted should be returned to its original
        position in the message sequence and retain its original UID.
        """
        pass

    def sync(self):
        """
        Discard the contents of any message marked for deletion.
        """
        pass


NONE, SHORT, FIRST_LONG, LONG = range(4)

NEXT = {}
NEXT[NONE] = NONE
NEXT[SHORT] = NONE
NEXT[FIRST_LONG] = LONG
NEXT[LONG] = NONE


class POP3Client(basic.LineOnlyReceiver):
    """
    A POP3 client protocol.

    @type mode: L{int}
    @ivar mode: The type of response expected from the server.  Choices include
    none (0), a one line response (1), the first line of a multi-line
    response (2), and subsequent lines of a multi-line response (3).

    @type command: L{bytes}
    @ivar command: The command most recently sent to the server.

    @type welcomeRe: L{Pattern <re.Pattern.search>}
    @ivar welcomeRe: A regular expression which matches the APOP challenge in
        the server greeting.

    @type welcomeCode: L{bytes}
    @ivar welcomeCode: The APOP challenge passed in the server greeting.
    """

    mode = SHORT
    command = b"WELCOME"
    import re

    welcomeRe = re.compile(b"<(.*)>")

    def __init__(self):
        """
        Issue deprecation warning.
        """
        import warnings

        warnings.warn(
            "twisted.mail.pop3.POP3Client is deprecated, "
            "please use twisted.mail.pop3.AdvancedPOP3Client "
            "instead.",
            DeprecationWarning,
            stacklevel=3,
        )

    def sendShort(self, command, params=None):
        """
        Send a POP3 command to which a short response is expected.

        @type command: L{bytes}
        @param command: A POP3 command.

        @type params: stringifyable L{object} or L{None}
        @param params: Command arguments.
        """
        if params is not None:
            if not isinstance(params, bytes):
                params = str(params).encode("utf-8")
            self.sendLine(command + b" " + params)
        else:
            self.sendLine(command)
        self.command = command
        self.mode = SHORT

    def sendLong(self, command, params):
        """
        Send a POP3 command to which a long response is expected.

        @type command: L{bytes}
        @param command: A POP3 command.

        @type params: stringifyable L{object}
        @param params: Command arguments.
        """
        if params:
            if not isinstance(params, bytes):
                params = str(params).encode("utf-8")
            self.sendLine(command + b" " + params)
        else:
            self.sendLine(command)
        self.command = command
        self.mode = FIRST_LONG

    def handle_default(self, line):
        """
        Handle responses from the server for which no other handler exists.

        @type line: L{bytes}
        @param line: A received line.
        """
        if line[:-4] == b"-ERR":
            self.mode = NONE

    def handle_WELCOME(self, line):
        """
        Handle a server response which is expected to be a server greeting.

        @type line: L{bytes}
        @param line: A received line.
        """
        code, data = line.split(b" ", 1)
        if code != b"+OK":
            self.transport.loseConnection()
        else:
            m = self.welcomeRe.match(line)
            if m:
                self.welcomeCode = m.group(1)

    def _dispatch(self, command, default, *args):
        """
        Dispatch a response from the server for handling.

        Command X is dispatched to handle_X() if it exists.  If not, it is
        dispatched to the default handler.

        @type command: L{bytes}
        @param command: The command.

        @type default: callable that takes L{bytes} or
            L{None}
        @param default: The default handler.

        @type args: L{tuple} or L{None}
        @param args: Arguments to the handler function.
        """
        try:
            method = getattr(self, "handle_" + command.decode("utf-8"), default)
            if method is not None:
                method(*args)
        except BaseException:
            log.err()

    def lineReceived(self, line):
        """
        Dispatch a received line for processing.

        The choice of function to handle the received line is based on the
        type of response expected to the command sent to the server and how
        much of that response has been received.

        An expected one line response to command X is handled by handle_X().
        The first line of a multi-line response to command X is also handled by
        handle_X().  Subsequent lines of the multi-line response are handled by
        handle_X_continue() except for the last line which is handled by
        handle_X_end().

        @type line: L{bytes}
        @param line: A received line.
        """
        if self.mode == SHORT or self.mode == FIRST_LONG:
            self.mode = NEXT[self.mode]
            self._dispatch(self.command, self.handle_default, line)
        elif self.mode == LONG:
            if line == b".":
                self.mode = NEXT[self.mode]
                self._dispatch(self.command + b"_end", None)
                return
            if line[:1] == b".":
                line = line[1:]
            self._dispatch(self.command + b"_continue", None, line)

    def apopAuthenticate(self, user, password, magic):
        """
        Perform an authenticated login.

        @type user: L{bytes}
        @param user: The username with which to log in.

        @type password: L{bytes}
        @param password: The password with which to log in.

        @type magic: L{bytes}
        @param magic: The challenge provided by the server.
        """
        digest = md5(magic + password).hexdigest().encode("ascii")
        self.apop(user, digest)

    def apop(self, user, digest):
        """
        Send an APOP command to perform authenticated login.

        @type user: L{bytes}
        @param user: The username with which to log in.

        @type digest: L{bytes}
        @param digest: The challenge response with which to authenticate.
        """
        self.sendLong(b"APOP", b" ".join((user, digest)))

    def retr(self, i):
        """
        Send a RETR command to retrieve a message from the server.

        @type i: L{int} or L{bytes}
        @param i: A 0-based message index.
        """
        self.sendLong(b"RETR", i)

    def dele(self, i):
        """
        Send a DELE command to delete a message from the server.

        @type i: L{int} or L{bytes}
        @param i: A 0-based message index.
        """
        self.sendShort(b"DELE", i)

    def list(self, i=""):
        """
        Send a LIST command to retrieve the size of a message or, if no message
        is specified, the sizes of all messages.

        @type i: L{int} or L{bytes}
        @param i: A 0-based message index or the empty string to specify all
            messages.
        """
        self.sendLong(b"LIST", i)

    def uidl(self, i=""):
        """
        Send a UIDL command to retrieve the unique identifier of a message or,
        if no message is specified, the unique identifiers of all messages.

        @type i: L{int} or L{bytes}
        @param i: A 0-based message index or the empty string to specify all
            messages.
        """
        self.sendLong(b"UIDL", i)

    def user(self, name):
        """
        Send a USER command to perform the first half of a plaintext login.

        @type name: L{bytes}
        @param name: The username with which to log in.
        """
        self.sendShort(b"USER", name)

    def password(self, password):
        """
        Perform the second half of a plaintext login.

        @type password: L{bytes}
        @param password: The plaintext password with which to authenticate.
        """
        self.sendShort(b"PASS", password)

    pass_ = password

    def quit(self):
        """
        Send a QUIT command to disconnect from the server.
        """
        self.sendShort(b"QUIT")


from twisted.mail._except import (
    InsecureAuthenticationDisallowed,
    LineTooLong,
    ServerErrorResponse,
    TLSError,
    TLSNotSupportedError,
)
from twisted.mail._pop3client import POP3Client as AdvancedPOP3Client

__all__ = [
    # Interfaces
    "IMailbox",
    "IServerFactory",
    # Exceptions
    "POP3Error",
    "POP3ClientError",
    "InsecureAuthenticationDisallowed",
    "ServerErrorResponse",
    "LineTooLong",
    "TLSError",
    "TLSNotSupportedError",
    # Protocol classes
    "POP3",
    "POP3Client",
    "AdvancedPOP3Client",
    # Misc
    "APOPCredentials",
    "Mailbox",
]
