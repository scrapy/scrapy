# -*- test-case-name: twisted.mail.test.test_smtp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# pylint: disable=I0011,C0103,C9302

"""
Simple Mail Transfer Protocol implementation.
"""


import base64
import binascii
import os
import random
import re
import socket
import time
import warnings
from email.utils import parseaddr
from io import BytesIO
from typing import Type

from zope.interface import implementer

from twisted import cred
from twisted.copyright import longversion
from twisted.internet import defer, error, protocol, reactor
from twisted.internet._idna import _idnaText
from twisted.internet.interfaces import ISSLTransport, ITLSTransport
from twisted.mail._cred import (
    CramMD5ClientAuthenticator,
    LOGINAuthenticator,
    LOGINCredentials as _lcredentials,
)
from twisted.mail._except import (
    AddressError,
    AUTHDeclinedError,
    AuthenticationError,
    AUTHRequiredError,
    EHLORequiredError,
    ESMTPClientError,
    SMTPAddressError,
    SMTPBadRcpt,
    SMTPBadSender,
    SMTPClientError,
    SMTPConnectError,
    SMTPDeliveryError,
    SMTPError,
    SMTPProtocolError,
    SMTPServerError,
    SMTPTimeoutError,
    SMTPTLSError as TLSError,
    TLSRequiredError,
)
from twisted.mail.interfaces import (
    IClientAuthentication,
    IMessageDelivery,
    IMessageDeliveryFactory,
    IMessageSMTP as IMessage,
)
from twisted.protocols import basic, policies
from twisted.python import log, util
from twisted.python.compat import iterbytes, nativeString, networkString
from twisted.python.runtime import platform

__all__ = [
    "AUTHDeclinedError",
    "AUTHRequiredError",
    "AddressError",
    "AuthenticationError",
    "EHLORequiredError",
    "ESMTPClientError",
    "SMTPAddressError",
    "SMTPBadRcpt",
    "SMTPBadSender",
    "SMTPClientError",
    "SMTPConnectError",
    "SMTPDeliveryError",
    "SMTPError",
    "SMTPServerError",
    "SMTPTimeoutError",
    "TLSError",
    "TLSRequiredError",
    "SMTPProtocolError",
    "IClientAuthentication",
    "IMessage",
    "IMessageDelivery",
    "IMessageDeliveryFactory",
    "CramMD5ClientAuthenticator",
    "LOGINAuthenticator",
    "LOGINCredentials",
    "PLAINAuthenticator",
    "Address",
    "User",
    "sendmail",
    "SenderMixin",
    "ESMTP",
    "ESMTPClient",
    "ESMTPSender",
    "ESMTPSenderFactory",
    "SMTP",
    "SMTPClient",
    "SMTPFactory",
    "SMTPSender",
    "SMTPSenderFactory",
    "idGenerator",
    "messageid",
    "quoteaddr",
    "rfc822date",
    "xtextStreamReader",
    "xtextStreamWriter",
    "xtext_codec",
    "xtext_decode",
    "xtext_encode",
]


# Cache the hostname (XXX Yes - this is broken)
# Encode the DNS name into something we can send over the wire
if platform.isMacOSX():
    # On macOS, getfqdn() is ridiculously slow - use the
    # probably-identical-but-sometimes-not gethostname() there.
    DNSNAME = socket.gethostname().encode("ascii")
else:
    DNSNAME = socket.getfqdn().encode("ascii")

# Used for fast success code lookup
SUCCESS = dict.fromkeys(range(200, 300))


def rfc822date(timeinfo=None, local=1):
    """
    Format an RFC-2822 compliant date string.

    @param timeinfo: (optional) A sequence as returned by C{time.localtime()}
        or C{time.gmtime()}. Default is now.
    @param local: (optional) Indicates if the supplied time is local or
        universal time, or if no time is given, whether now should be local or
        universal time. Default is local, as suggested (SHOULD) by rfc-2822.

    @returns: A L{bytes} representing the time and date in RFC-2822 format.
    """
    if not timeinfo:
        if local:
            timeinfo = time.localtime()
        else:
            timeinfo = time.gmtime()
    if local:
        if timeinfo[8]:
            # DST
            tz = -time.altzone
        else:
            tz = -time.timezone

        (tzhr, tzmin) = divmod(abs(tz), 3600)
        if tz:
            tzhr *= int(abs(tz) // tz)
        (tzmin, tzsec) = divmod(tzmin, 60)
    else:
        (tzhr, tzmin) = (0, 0)

    return networkString(
        "%s, %02d %s %04d %02d:%02d:%02d %+03d%02d"
        % (
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][timeinfo[6]],
            timeinfo[2],
            [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ][timeinfo[1] - 1],
            timeinfo[0],
            timeinfo[3],
            timeinfo[4],
            timeinfo[5],
            tzhr,
            tzmin,
        )
    )


def idGenerator():
    i = 0
    while True:
        yield i
        i += 1


_gen = idGenerator()


def messageid(uniq=None, N=lambda: next(_gen)):
    """
    Return a globally unique random string in RFC 2822 Message-ID format

    <datetime.pid.random@host.dom.ain>

    Optional uniq string will be added to strengthen uniqueness if given.
    """
    datetime = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    pid = os.getpid()
    rand = random.randrange(2 ** 31 - 1)
    if uniq is None:
        uniq = ""
    else:
        uniq = "." + uniq

    return "<{}.{}.{}{}.{}@{}>".format(
        datetime, pid, rand, uniq, N(), DNSNAME.decode()
    ).encode()


def quoteaddr(addr):
    """
    Turn an email address, possibly with realname part etc, into
    a form suitable for and SMTP envelope.
    """

    if isinstance(addr, Address):
        return b"<" + bytes(addr) + b">"

    if isinstance(addr, bytes):
        addr = addr.decode("ascii")

    res = parseaddr(addr)

    if res == (None, None):
        # It didn't parse, use it as-is
        return b"<" + bytes(addr) + b">"
    else:
        return b"<" + res[1].encode("ascii") + b">"


COMMAND, DATA, AUTH = "COMMAND", "DATA", "AUTH"


# Character classes for parsing addresses
atom = br"[-A-Za-z0-9!\#$%&'*+/=?^_`{|}~]"


class Address:
    """Parse and hold an RFC 2821 address.

    Source routes are stipped and ignored, UUCP-style bang-paths
    and %-style routing are not parsed.

    @type domain: C{bytes}
    @ivar domain: The domain within which this address resides.

    @type local: C{bytes}
    @ivar local: The local (\"user\") portion of this address.
    """

    tstring = re.compile(
        br"""( # A string of
                           (?:"[^"]*" # quoted string
                           |\\. # backslash-escaped characted
                           |"""
        + atom
        + br""" # atom character
                           )+|.) # or any single character""",
        re.X,
    )
    atomre = re.compile(atom)  # match any one atom character

    def __init__(self, addr, defaultDomain=None):
        if isinstance(addr, User):
            addr = addr.dest
        if isinstance(addr, Address):
            self.__dict__ = addr.__dict__.copy()
            return
        elif not isinstance(addr, bytes):
            addr = str(addr).encode("ascii")

        self.addrstr = addr

        # Tokenize
        atl = list(filter(None, self.tstring.split(addr)))
        local = []
        domain = []

        while atl:
            if atl[0] == b"<":
                if atl[-1] != b">":
                    raise AddressError("Unbalanced <>")
                atl = atl[1:-1]
            elif atl[0] == b"@":
                atl = atl[1:]
                if not local:
                    # Source route
                    while atl and atl[0] != b":":
                        # remove it
                        atl = atl[1:]
                    if not atl:
                        raise AddressError("Malformed source route")
                    atl = atl[1:]  # remove :
                elif domain:
                    raise AddressError("Too many @")
                else:
                    # Now in domain
                    domain = [b""]
            elif len(atl[0]) == 1 and not self.atomre.match(atl[0]) and atl[0] != b".":
                raise AddressError(f"Parse error at {atl[0]!r} of {(addr, atl)!r}")
            else:
                if not domain:
                    local.append(atl[0])
                else:
                    domain.append(atl[0])
                atl = atl[1:]

        self.local = b"".join(local)
        self.domain = b"".join(domain)
        if self.local != b"" and self.domain == b"":
            if defaultDomain is None:
                defaultDomain = DNSNAME
            self.domain = defaultDomain

    dequotebs = re.compile(br"\\(.)")

    def dequote(self, addr):
        """
        Remove RFC-2821 quotes from address.
        """
        res = []

        if not isinstance(addr, bytes):
            addr = str(addr).encode("ascii")

        atl = filter(None, self.tstring.split(addr))

        for t in atl:
            if t[0] == b'"' and t[-1] == b'"':
                res.append(t[1:-1])
            elif "\\" in t:
                res.append(self.dequotebs.sub(br"\1", t))
            else:
                res.append(t)

        return b"".join(res)

    def __str__(self) -> str:
        return self.__bytes__().decode("ascii")

    def __bytes__(self) -> bytes:
        if self.local or self.domain:
            return b"@".join((self.local, self.domain))
        else:
            return b""

    def __repr__(self) -> str:
        return "{}.{}({})".format(
            self.__module__, self.__class__.__name__, repr(str(self))
        )


class User:
    """
    Hold information about and SMTP message recipient,
    including information on where the message came from
    """

    def __init__(self, destination, helo, protocol, orig):
        try:
            host = protocol.host
        except AttributeError:
            host = None
        self.dest = Address(destination, host)
        self.helo = helo
        self.protocol = protocol
        if isinstance(orig, Address):
            self.orig = orig
        else:
            self.orig = Address(orig, host)

    def __getstate__(self):
        """
        Helper for pickle.

        protocol isn't picklabe, but we want User to be, so skip it in
        the pickle.
        """
        return {
            "dest": self.dest,
            "helo": self.helo,
            "protocol": None,
            "orig": self.orig,
        }

    def __str__(self) -> str:
        return self.__bytes__().decode("ascii")

    def __bytes__(self) -> bytes:
        return bytes(self.dest)


class SMTP(basic.LineOnlyReceiver, policies.TimeoutMixin):
    """
    SMTP server-side protocol.

    @ivar host: The hostname of this mail server.
    @type host: L{bytes}
    """

    timeout = 600
    portal = None

    # Control whether we log SMTP events
    noisy = True

    # A factory for IMessageDelivery objects.  If an
    # avatar implementing IMessageDeliveryFactory can
    # be acquired from the portal, it will be used to
    # create a new IMessageDelivery object for each
    # message which is received.
    deliveryFactory = None

    # An IMessageDelivery object.  A new instance is
    # used for each message received if we can get an
    # IMessageDeliveryFactory from the portal.  Otherwise,
    # a single instance is used throughout the lifetime
    # of the connection.
    delivery = None

    # Cred cleanup function.
    _onLogout = None

    def __init__(self, delivery=None, deliveryFactory=None):
        self.mode = COMMAND
        self._from = None
        self._helo = None
        self._to = []
        self.delivery = delivery
        self.deliveryFactory = deliveryFactory
        self.host = DNSNAME

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, toSet):
        if not isinstance(toSet, bytes):
            toSet = str(toSet).encode("ascii")
        self._host = toSet

    def timeoutConnection(self):
        msg = self.host + b" Timeout. Try talking faster next time!"
        self.sendCode(421, msg)
        self.transport.loseConnection()

    def greeting(self):
        return self.host + b" NO UCE NO UBE NO RELAY PROBES"

    def connectionMade(self):
        # Ensure user-code always gets something sane for _helo
        peer = self.transport.getPeer()
        try:
            host = peer.host
        except AttributeError:  # not an IPv4Address
            host = str(peer)
        self._helo = (None, host)
        self.sendCode(220, self.greeting())
        self.setTimeout(self.timeout)

    def sendCode(self, code, message=b""):
        """
        Send an SMTP code with a message.
        """
        lines = message.splitlines()
        lastline = lines[-1:]
        for line in lines[:-1]:
            self.sendLine(networkString("%3.3d-" % (code,)) + line)
        self.sendLine(
            networkString("%3.3d " % (code,)) + (lastline and lastline[0] or b"")
        )

    def lineReceived(self, line):
        self.resetTimeout()
        return getattr(self, "state_" + self.mode)(line)

    def state_COMMAND(self, line):
        # Ignore leading and trailing whitespace, as well as an arbitrary
        # amount of whitespace between the command and its argument, though
        # it is not required by the protocol, for it is a nice thing to do.
        line = line.strip()

        parts = line.split(None, 1)
        if parts:
            method = self.lookupMethod(parts[0]) or self.do_UNKNOWN
            if len(parts) == 2:
                method(parts[1])
            else:
                method(b"")
        else:
            self.sendSyntaxError()

    def sendSyntaxError(self):
        self.sendCode(500, b"Error: bad syntax")

    def lookupMethod(self, command):
        """

        @param command: The command to get from this class.
        @type command: L{str}
        @return: The function which executes this command.
        """
        if not isinstance(command, str):
            command = nativeString(command)

        return getattr(self, "do_" + command.upper(), None)

    def lineLengthExceeded(self, line):
        if self.mode is DATA:
            for message in self.__messages:
                message.connectionLost()
            self.mode = COMMAND
            del self.__messages
        self.sendCode(500, b"Line too long")

    def do_UNKNOWN(self, rest):
        self.sendCode(500, b"Command not implemented")

    def do_HELO(self, rest):
        peer = self.transport.getPeer()
        try:
            host = peer.host
        except AttributeError:
            host = str(peer)

        if not isinstance(host, bytes):
            host = host.encode("idna")

        self._helo = (rest, host)
        self._from = None
        self._to = []
        self.sendCode(250, self.host + b" Hello " + host + b", nice to meet you")

    def do_QUIT(self, rest):
        self.sendCode(221, b"See you later")
        self.transport.loseConnection()

    # A string of quoted strings, backslash-escaped character or
    # atom characters + '@.,:'
    qstring = br'("[^"]*"|\\.|' + atom + br"|[@.,:])+"

    mail_re = re.compile(
        br"""\s*FROM:\s*(?P<path><> # Empty <>
                          |<"""
        + qstring
        + br"""> # <addr>
                          |"""
        + qstring
        + br""" # addr
                          )\s*(\s(?P<opts>.*))? # Optional WS + ESMTP options
                          $""",
        re.I | re.X,
    )
    rcpt_re = re.compile(
        br"\s*TO:\s*(?P<path><"
        + qstring
        + br"""> # <addr>
                          |"""
        + qstring
        + br""" # addr
                          )\s*(\s(?P<opts>.*))? # Optional WS + ESMTP options
                          $""",
        re.I | re.X,
    )

    def do_MAIL(self, rest):
        if self._from:
            self.sendCode(503, b"Only one sender per message, please")
            return
        # Clear old recipient list
        self._to = []
        m = self.mail_re.match(rest)
        if not m:
            self.sendCode(501, b"Syntax error")
            return

        try:
            addr = Address(m.group("path"), self.host)
        except AddressError as e:
            self.sendCode(553, networkString(str(e)))
            return

        validated = defer.maybeDeferred(self.validateFrom, self._helo, addr)
        validated.addCallbacks(self._cbFromValidate, self._ebFromValidate)

    def _cbFromValidate(self, fromEmail, code=250, msg=b"Sender address accepted"):
        self._from = fromEmail
        self.sendCode(code, msg)

    def _ebFromValidate(self, failure):
        if failure.check(SMTPBadSender):
            self.sendCode(
                failure.value.code,
                (
                    b"Cannot receive from specified address "
                    + quoteaddr(failure.value.addr)
                    + b": "
                    + networkString(failure.value.resp)
                ),
            )
        elif failure.check(SMTPServerError):
            self.sendCode(failure.value.code, networkString(failure.value.resp))
        else:
            log.err(failure, "SMTP sender validation failure")
            self.sendCode(451, b"Requested action aborted: local error in processing")

    def do_RCPT(self, rest):
        if not self._from:
            self.sendCode(503, b"Must have sender before recipient")
            return
        m = self.rcpt_re.match(rest)
        if not m:
            self.sendCode(501, b"Syntax error")
            return

        try:
            user = User(m.group("path"), self._helo, self, self._from)
        except AddressError as e:
            self.sendCode(553, networkString(str(e)))
            return

        d = defer.maybeDeferred(self.validateTo, user)
        d.addCallbacks(self._cbToValidate, self._ebToValidate, callbackArgs=(user,))

    def _cbToValidate(self, to, user=None, code=250, msg=b"Recipient address accepted"):
        if user is None:
            user = to
        self._to.append((user, to))
        self.sendCode(code, msg)

    def _ebToValidate(self, failure):
        if failure.check(SMTPBadRcpt, SMTPServerError):
            self.sendCode(failure.value.code, networkString(failure.value.resp))
        else:
            log.err(failure)
            self.sendCode(451, b"Requested action aborted: local error in processing")

    def _disconnect(self, msgs):
        for msg in msgs:
            try:
                msg.connectionLost()
            except BaseException:
                log.msg("msg raised exception from connectionLost")
                log.err()

    def do_DATA(self, rest):
        if self._from is None or (not self._to):
            self.sendCode(503, b"Must have valid receiver and originator")
            return
        self.mode = DATA
        helo, origin = self._helo, self._from
        recipients = self._to

        self._from = None
        self._to = []
        self.datafailed = None

        msgs = []
        for (user, msgFunc) in recipients:
            try:
                msg = msgFunc()
                rcvdhdr = self.receivedHeader(helo, origin, [user])
                if rcvdhdr:
                    msg.lineReceived(rcvdhdr)
                msgs.append(msg)
            except SMTPServerError as e:
                self.sendCode(e.code, e.resp)
                self.mode = COMMAND
                self._disconnect(msgs)
                return
            except BaseException:
                log.err()
                self.sendCode(550, b"Internal server error")
                self.mode = COMMAND
                self._disconnect(msgs)
                return
        self.__messages = msgs

        self.__inheader = self.__inbody = 0
        self.sendCode(354, b"Continue")

        if self.noisy:
            fmt = "Receiving message for delivery: from=%s to=%s"
            log.msg(fmt % (origin, [str(u) for (u, f) in recipients]))

    def connectionLost(self, reason):
        # self.sendCode(421, 'Dropping connection.') # This does nothing...
        # Ideally, if we (rather than the other side) lose the connection,
        # we should be able to tell the other side that we are going away.
        # RFC-2821 requires that we try.
        if self.mode is DATA:
            try:
                for message in self.__messages:
                    try:
                        message.connectionLost()
                    except BaseException:
                        log.err()
                del self.__messages
            except AttributeError:
                pass
        if self._onLogout:
            self._onLogout()
            self._onLogout = None
        self.setTimeout(None)

    def do_RSET(self, rest):
        self._from = None
        self._to = []
        self.sendCode(250, b"I remember nothing.")

    def dataLineReceived(self, line):
        if line[:1] == b".":
            if line == b".":
                self.mode = COMMAND
                if self.datafailed:
                    self.sendCode(self.datafailed.code, self.datafailed.resp)
                    return
                if not self.__messages:
                    self._messageHandled("thrown away")
                    return
                defer.DeferredList(
                    [m.eomReceived() for m in self.__messages], consumeErrors=True
                ).addCallback(self._messageHandled)
                del self.__messages
                return
            line = line[1:]

        if self.datafailed:
            return

        try:
            # Add a blank line between the generated Received:-header
            # and the message body if the message comes in without any
            # headers
            if not self.__inheader and not self.__inbody:
                if b":" in line:
                    self.__inheader = 1
                elif line:
                    for message in self.__messages:
                        message.lineReceived(b"")
                    self.__inbody = 1

            if not line:
                self.__inbody = 1

            for message in self.__messages:
                message.lineReceived(line)
        except SMTPServerError as e:
            self.datafailed = e
            for message in self.__messages:
                message.connectionLost()

    state_DATA = dataLineReceived

    def _messageHandled(self, resultList):
        failures = 0
        for (success, result) in resultList:
            if not success:
                failures += 1
                log.err(result)
        if failures:
            msg = "Could not send e-mail"
            resultLen = len(resultList)
            if resultLen > 1:
                msg += f" ({failures} failures out of {resultLen} recipients)"
            self.sendCode(550, networkString(msg))
        else:
            self.sendCode(250, b"Delivery in progress")

    def _cbAnonymousAuthentication(self, result):
        """
        Save the state resulting from a successful anonymous cred login.
        """
        (iface, avatar, logout) = result
        if issubclass(iface, IMessageDeliveryFactory):
            self.deliveryFactory = avatar
            self.delivery = None
        elif issubclass(iface, IMessageDelivery):
            self.deliveryFactory = None
            self.delivery = avatar
        else:
            raise RuntimeError(f"{iface.__name__} is not a supported interface")
        self._onLogout = logout
        self.challenger = None

    # overridable methods:
    def validateFrom(self, helo, origin):
        """
        Validate the address from which the message originates.

        @type helo: C{(bytes, bytes)}
        @param helo: The argument to the HELO command and the client's IP
        address.

        @type origin: C{Address}
        @param origin: The address the message is from

        @rtype: C{Deferred} or C{Address}
        @return: C{origin} or a C{Deferred} whose callback will be
        passed C{origin}.

        @raise SMTPBadSender: Raised of messages from this address are
        not to be accepted.
        """
        if self.deliveryFactory is not None:
            self.delivery = self.deliveryFactory.getMessageDelivery()

        if self.delivery is not None:
            return defer.maybeDeferred(self.delivery.validateFrom, helo, origin)

        # No login has been performed, no default delivery object has been
        # provided: try to perform an anonymous login and then invoke this
        # method again.
        if self.portal:

            result = self.portal.login(
                cred.credentials.Anonymous(),
                None,
                IMessageDeliveryFactory,
                IMessageDelivery,
            )

            def ebAuthentication(err):
                """
                Translate cred exceptions into SMTP exceptions so that the
                protocol code which invokes C{validateFrom} can properly report
                the failure.
                """
                if err.check(cred.error.UnauthorizedLogin):
                    exc = SMTPBadSender(origin)
                elif err.check(cred.error.UnhandledCredentials):
                    exc = SMTPBadSender(
                        origin, resp="Unauthenticated senders not allowed"
                    )
                else:
                    return err
                return defer.fail(exc)

            result.addCallbacks(self._cbAnonymousAuthentication, ebAuthentication)

            def continueValidation(ignored):
                """
                Re-attempt from address validation.
                """
                return self.validateFrom(helo, origin)

            result.addCallback(continueValidation)
            return result

        raise SMTPBadSender(origin)

    def validateTo(self, user):
        """
        Validate the address for which the message is destined.

        @type user: L{User}
        @param user: The address to validate.

        @rtype: no-argument callable
        @return: A C{Deferred} which becomes, or a callable which
        takes no arguments and returns an object implementing C{IMessage}.
        This will be called and the returned object used to deliver the
        message when it arrives.

        @raise SMTPBadRcpt: Raised if messages to the address are
        not to be accepted.
        """
        if self.delivery is not None:
            return self.delivery.validateTo(user)
        raise SMTPBadRcpt(user)

    def receivedHeader(self, helo, origin, recipients):
        if self.delivery is not None:
            return self.delivery.receivedHeader(helo, origin, recipients)

        heloStr = b""
        if helo[0]:
            heloStr = b" helo=" + helo[0]
        domain = networkString(self.transport.getHost().host)

        from_ = b"from " + helo[0] + b" ([" + helo[1] + b"]" + heloStr + b")"
        by = b"by %s with %s (%s)" % (domain, self.__class__.__name__, longversion)
        for_ = b"for %s; %s" % (" ".join(map(str, recipients)), rfc822date())
        return b"Received: " + from_ + b"\n\t" + by + b"\n\t" + for_


class SMTPFactory(protocol.ServerFactory):
    """
    Factory for SMTP.
    """

    # override in instances or subclasses
    domain = DNSNAME
    timeout = 600
    protocol = SMTP

    portal = None

    def __init__(self, portal=None):
        self.portal = portal

    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)
        p.portal = self.portal
        p.host = self.domain
        return p


class SMTPClient(basic.LineReceiver, policies.TimeoutMixin):
    """
    SMTP client for sending emails.

    After the client has connected to the SMTP server, it repeatedly calls
    L{SMTPClient.getMailFrom}, L{SMTPClient.getMailTo} and
    L{SMTPClient.getMailData} and uses this information to send an email.
    It then calls L{SMTPClient.getMailFrom} again; if it returns L{None}, the
    client will disconnect, otherwise it will continue as normal i.e. call
    L{SMTPClient.getMailTo} and L{SMTPClient.getMailData} and send a new email.
    """

    # If enabled then log SMTP client server communication
    debug = True

    # Number of seconds to wait before timing out a connection.  If
    # None, perform no timeout checking.
    timeout = None

    def __init__(self, identity, logsize=10):
        if isinstance(identity, str):
            identity = identity.encode("ascii")

        self.identity = identity or b""
        self.toAddressesResult = []
        self.successAddresses = []
        self._from = None
        self.resp = []
        self.code = -1
        self.log = util.LineLog(logsize)

    def sendLine(self, line):
        # Log sendLine only if you are in debug mode for performance
        if self.debug:
            self.log.append(b">>> " + line)

        basic.LineReceiver.sendLine(self, line)

    def connectionMade(self):
        self.setTimeout(self.timeout)

        self._expected = [220]
        self._okresponse = self.smtpState_helo
        self._failresponse = self.smtpConnectionFailed

    def connectionLost(self, reason=protocol.connectionDone):
        """
        We are no longer connected
        """
        self.setTimeout(None)
        self.mailFile = None

    def timeoutConnection(self):
        self.sendError(
            SMTPTimeoutError(
                -1, b"Timeout waiting for SMTP server response", self.log.str()
            )
        )

    def lineReceived(self, line):
        self.resetTimeout()

        # Log lineReceived only if you are in debug mode for performance
        if self.debug:
            self.log.append(b"<<< " + line)

        why = None

        try:
            self.code = int(line[:3])
        except ValueError:
            # This is a fatal error and will disconnect the transport
            # lineReceived will not be called again.
            self.sendError(
                SMTPProtocolError(
                    -1,
                    f"Invalid response from SMTP server: {line}",
                    self.log.str(),
                )
            )
            return

        if line[0:1] == b"0":
            # Verbose informational message, ignore it
            return

        self.resp.append(line[4:])

        if line[3:4] == b"-":
            # Continuation
            return

        if self.code in self._expected:
            why = self._okresponse(self.code, b"\n".join(self.resp))
        else:
            why = self._failresponse(self.code, b"\n".join(self.resp))

        self.code = -1
        self.resp = []
        return why

    def smtpConnectionFailed(self, code, resp):
        self.sendError(SMTPConnectError(code, resp, self.log.str()))

    def smtpTransferFailed(self, code, resp):
        if code < 0:
            self.sendError(SMTPProtocolError(code, resp, self.log.str()))
        else:
            self.smtpState_msgSent(code, resp)

    def smtpState_helo(self, code, resp):
        self.sendLine(b"HELO " + self.identity)
        self._expected = SUCCESS
        self._okresponse = self.smtpState_from

    def smtpState_from(self, code, resp):
        self._from = self.getMailFrom()
        self._failresponse = self.smtpTransferFailed
        if self._from is not None:
            self.sendLine(b"MAIL FROM:" + quoteaddr(self._from))
            self._expected = [250]
            self._okresponse = self.smtpState_to
        else:
            # All messages have been sent, disconnect
            self._disconnectFromServer()

    def smtpState_disconnect(self, code, resp):
        self.transport.loseConnection()

    def smtpState_to(self, code, resp):
        self.toAddresses = iter(self.getMailTo())
        self.toAddressesResult = []
        self.successAddresses = []
        self._okresponse = self.smtpState_toOrData
        self._expected = range(0, 1000)
        self.lastAddress = None
        return self.smtpState_toOrData(0, b"")

    def smtpState_toOrData(self, code, resp):
        if self.lastAddress is not None:
            self.toAddressesResult.append((self.lastAddress, code, resp))
            if code in SUCCESS:
                self.successAddresses.append(self.lastAddress)
        try:
            self.lastAddress = next(self.toAddresses)
        except StopIteration:
            if self.successAddresses:
                self.sendLine(b"DATA")
                self._expected = [354]
                self._okresponse = self.smtpState_data
            else:
                return self.smtpState_msgSent(code, "No recipients accepted")
        else:
            self.sendLine(b"RCPT TO:" + quoteaddr(self.lastAddress))

    def smtpState_data(self, code, resp):
        s = basic.FileSender()
        d = s.beginFileTransfer(self.getMailData(), self.transport, self.transformChunk)

        def ebTransfer(err):
            self.sendError(err.value)

        d.addCallbacks(self.finishedFileTransfer, ebTransfer)
        self._expected = SUCCESS
        self._okresponse = self.smtpState_msgSent

    def smtpState_msgSent(self, code, resp):
        if self._from is not None:
            self.sentMail(
                code, resp, len(self.successAddresses), self.toAddressesResult, self.log
            )

        self.toAddressesResult = []
        self._from = None
        self.sendLine(b"RSET")
        self._expected = SUCCESS
        self._okresponse = self.smtpState_from

    ##
    ## Helpers for FileSender
    ##
    def transformChunk(self, chunk):
        """
        Perform the necessary local to network newline conversion and escape
        leading periods.

        This method also resets the idle timeout so that as long as process is
        being made sending the message body, the client will not time out.
        """
        self.resetTimeout()
        return chunk.replace(b"\n", b"\r\n").replace(b"\r\n.", b"\r\n..")

    def finishedFileTransfer(self, lastsent):
        if lastsent != b"\n":
            line = b"\r\n."
        else:
            line = b"."
        self.sendLine(line)

    ##
    # these methods should be overridden in subclasses
    def getMailFrom(self):
        """
        Return the email address the mail is from.
        """
        raise NotImplementedError

    def getMailTo(self):
        """
        Return a list of emails to send to.
        """
        raise NotImplementedError

    def getMailData(self):
        """
        Return file-like object containing data of message to be sent.

        Lines in the file should be delimited by '\\n'.
        """
        raise NotImplementedError

    def sendError(self, exc):
        """
        If an error occurs before a mail message is sent sendError will be
        called.  This base class method sends a QUIT if the error is
        non-fatal and disconnects the connection.

        @param exc: The SMTPClientError (or child class) raised
        @type exc: C{SMTPClientError}
        """
        if isinstance(exc, SMTPClientError) and not exc.isFatal:
            self._disconnectFromServer()
        else:
            # If the error was fatal then the communication channel with the
            # SMTP Server is broken so just close the transport connection
            self.smtpState_disconnect(-1, None)

    def sentMail(self, code, resp, numOk, addresses, log):
        """
        Called when an attempt to send an email is completed.

        If some addresses were accepted, code and resp are the response
        to the DATA command. If no addresses were accepted, code is -1
        and resp is an informative message.

        @param code: the code returned by the SMTP Server
        @param resp: The string response returned from the SMTP Server
        @param numOk: the number of addresses accepted by the remote host.
        @param addresses: is a list of tuples (address, code, resp) listing
                          the response to each RCPT command.
        @param log: is the SMTP session log
        """
        raise NotImplementedError

    def _disconnectFromServer(self):
        self._expected = range(0, 1000)
        self._okresponse = self.smtpState_disconnect
        self.sendLine(b"QUIT")


class ESMTPClient(SMTPClient):
    """
    A client for sending emails over ESMTP.

    @ivar heloFallback: Whether or not to fall back to plain SMTP if the C{EHLO}
        command is not recognised by the server. If L{requireAuthentication} is
        C{True}, or L{requireTransportSecurity} is C{True} and the connection is
        not over TLS, this fallback flag will not be honored.
    @type heloFallback: L{bool}

    @ivar requireAuthentication: If C{True}, refuse to proceed if authentication
        cannot be performed. Overrides L{heloFallback}.
    @type requireAuthentication: L{bool}

    @ivar requireTransportSecurity: If C{True}, refuse to proceed if the
        transport cannot be secured. If the transport layer is not already
        secured via TLS, this will override L{heloFallback}.
    @type requireAuthentication: L{bool}

    @ivar context: The context factory to use for STARTTLS, if desired.
    @type context: L{IOpenSSLClientConnectionCreator}

    @ivar _tlsMode: Whether or not the connection is over TLS.
    @type _tlsMode: L{bool}
    """

    heloFallback = True
    requireAuthentication = False
    requireTransportSecurity = False
    context = None
    _tlsMode = False

    def __init__(self, secret, contextFactory=None, *args, **kw):
        SMTPClient.__init__(self, *args, **kw)
        self.authenticators = []
        self.secret = secret
        self.context = contextFactory

    def __getattr__(self, name):
        if name == "tlsMode":
            warnings.warn(
                "tlsMode attribute of twisted.mail.smtp.ESMTPClient "
                "is deprecated since Twisted 13.0",
                category=DeprecationWarning,
                stacklevel=2,
            )
            return self._tlsMode
        else:
            raise AttributeError(
                "%s instance has no attribute %r"
                % (
                    self.__class__.__name__,
                    name,
                )
            )

    def __setattr__(self, name, value):
        if name == "tlsMode":
            warnings.warn(
                "tlsMode attribute of twisted.mail.smtp.ESMTPClient "
                "is deprecated since Twisted 13.0",
                category=DeprecationWarning,
                stacklevel=2,
            )
            self._tlsMode = value
        else:
            self.__dict__[name] = value

    def esmtpEHLORequired(self, code=-1, resp=None):
        """
        Fail because authentication is required, but the server does not support
        ESMTP, which is required for authentication.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(
            EHLORequiredError(
                502, b"Server does not support ESMTP " b"Authentication", self.log.str()
            )
        )

    def esmtpAUTHRequired(self, code=-1, resp=None):
        """
        Fail because authentication is required, but the server does not support
        any schemes we support.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        tmp = []

        for a in self.authenticators:
            tmp.append(a.getName().upper())

        auth = b"[%s]" % b", ".join(tmp)

        self.sendError(
            AUTHRequiredError(
                502,
                b"Server does not support Client " b"Authentication schemes %s" % auth,
                self.log.str(),
            )
        )

    def esmtpTLSRequired(self, code=-1, resp=None):
        """
        Fail because TLS is required and the server does not support it.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(
            TLSRequiredError(
                502,
                b"Server does not support secure " b"communication via TLS / SSL",
                self.log.str(),
            )
        )

    def esmtpTLSFailed(self, code=-1, resp=None):
        """
        Fail because the TLS handshake wasn't able to be completed.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(
            TLSError(
                code, b"Could not complete the SSL/TLS " b"handshake", self.log.str()
            )
        )

    def esmtpAUTHDeclined(self, code=-1, resp=None):
        """
        Fail because the authentication was rejected.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(AUTHDeclinedError(code, resp, self.log.str()))

    def esmtpAUTHMalformedChallenge(self, code=-1, resp=None):
        """
        Fail because the server sent a malformed authentication challenge.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(
            AuthenticationError(
                501,
                b"Login failed because the "
                b"SMTP Server returned a malformed Authentication Challenge",
                self.log.str(),
            )
        )

    def esmtpAUTHServerError(self, code=-1, resp=None):
        """
        Fail because of some other authentication error.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}
        """
        self.sendError(AuthenticationError(code, resp, self.log.str()))

    def registerAuthenticator(self, auth):
        """
        Registers an Authenticator with the ESMTPClient. The ESMTPClient will
        attempt to login to the SMTP Server in the order the Authenticators are
        registered. The most secure Authentication mechanism should be
        registered first.

        @param auth: The Authentication mechanism to register
        @type auth: L{IClientAuthentication} implementor

        @return: L{None}
        """
        self.authenticators.append(auth)

    def connectionMade(self):
        """
        Called when a connection has been made, and triggers sending an C{EHLO}
        to the server.
        """
        self._tlsMode = ISSLTransport.providedBy(self.transport)
        SMTPClient.connectionMade(self)
        self._okresponse = self.esmtpState_ehlo

    def esmtpState_ehlo(self, code, resp):
        """
        Send an C{EHLO} to the server.

        If L{heloFallback} is C{True}, and there is no requirement for TLS or
        authentication, the client will fall back to basic SMTP.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}

        @return: L{None}
        """
        self._expected = SUCCESS

        self._okresponse = self.esmtpState_serverConfig
        self._failresponse = self.esmtpEHLORequired

        if self._tlsMode:
            needTLS = False
        else:
            needTLS = self.requireTransportSecurity

        if self.heloFallback and not self.requireAuthentication and not needTLS:
            self._failresponse = self.smtpState_helo

        self.sendLine(b"EHLO " + self.identity)

    def esmtpState_serverConfig(self, code, resp):
        """
        Handle a positive response to the I{EHLO} command by parsing the
        capabilities in the server's response and then taking the most
        appropriate next step towards entering a mail transaction.
        """
        items = {}
        for line in resp.splitlines():
            e = line.split(None, 1)
            if len(e) > 1:
                items[e[0]] = e[1]
            else:
                items[e[0]] = None

        self.tryTLS(code, resp, items)

    def tryTLS(self, code, resp, items):
        """
        Take a necessary step towards being able to begin a mail transaction.

        The step may be to ask the server to being a TLS session.  If TLS is
        already in use or not necessary and not available then the step may be
        to authenticate with the server.  If TLS is necessary and not available,
        fail the mail transmission attempt.

        This is an internal helper method.

        @param code: The server status code from the most recently received
            server message.
        @type code: L{int}

        @param resp: The server status response from the most recently received
            server message.
        @type resp: L{bytes}

        @param items: A mapping of ESMTP extensions offered by the server.  Keys
            are extension identifiers and values are the associated values.
        @type items: L{dict} mapping L{bytes} to L{bytes}

        @return: L{None}
        """

        # has tls        can tls         must tls       result
        #   t               t               t           authenticate
        #   t               t               f           authenticate
        #   t               f               t           authenticate
        #   t               f               f           authenticate

        #   f               t               t           STARTTLS
        #   f               t               f           STARTTLS
        #   f               f               t           esmtpTLSRequired
        #   f               f               f           authenticate

        hasTLS = self._tlsMode
        canTLS = self.context and b"STARTTLS" in items
        mustTLS = self.requireTransportSecurity

        if hasTLS or not (canTLS or mustTLS):
            self.authenticate(code, resp, items)
        elif canTLS:
            self._expected = [220]
            self._okresponse = self.esmtpState_starttls
            self._failresponse = self.esmtpTLSFailed
            self.sendLine(b"STARTTLS")
        else:
            self.esmtpTLSRequired()

    def esmtpState_starttls(self, code, resp):
        """
        Handle a positive response to the I{STARTTLS} command by starting a new
        TLS session on C{self.transport}.

        Upon success, re-handshake with the server to discover what capabilities
        it has when TLS is in use.
        """
        try:
            self.transport.startTLS(self.context)
            self._tlsMode = True
        except BaseException:
            log.err()
            self.esmtpTLSFailed(451)

        # Send another EHLO once TLS has been started to
        # get the TLS / AUTH schemes. Some servers only allow AUTH in TLS mode.
        self.esmtpState_ehlo(code, resp)

    def authenticate(self, code, resp, items):
        if self.secret and items.get(b"AUTH"):
            schemes = items[b"AUTH"].split()
            tmpSchemes = {}

            # XXX: May want to come up with a more efficient way to do this
            for s in schemes:
                tmpSchemes[s.upper()] = 1

            for a in self.authenticators:
                auth = a.getName().upper()

                if auth in tmpSchemes:
                    self._authinfo = a

                    # Special condition handled
                    if auth == b"PLAIN":
                        self._okresponse = self.smtpState_from
                        self._failresponse = self._esmtpState_plainAuth
                        self._expected = [235]
                        challenge = base64.b64encode(
                            self._authinfo.challengeResponse(self.secret, 1)
                        )
                        self.sendLine(b"AUTH %s %s" % (auth, challenge))
                    else:
                        self._expected = [334]
                        self._okresponse = self.esmtpState_challenge
                        # If some error occurs here, the server declined the
                        # AUTH before the user / password phase. This would be
                        # a very rare case
                        self._failresponse = self.esmtpAUTHServerError
                        self.sendLine(b"AUTH " + auth)
                    return

        if self.requireAuthentication:
            self.esmtpAUTHRequired()
        else:
            self.smtpState_from(code, resp)

    def _esmtpState_plainAuth(self, code, resp):
        self._okresponse = self.smtpState_from
        self._failresponse = self.esmtpAUTHDeclined
        self._expected = [235]
        challenge = base64.b64encode(self._authinfo.challengeResponse(self.secret, 2))
        self.sendLine(b"AUTH PLAIN " + challenge)

    def esmtpState_challenge(self, code, resp):
        self._authResponse(self._authinfo, resp)

    def _authResponse(self, auth, challenge):
        self._failresponse = self.esmtpAUTHDeclined
        try:
            challenge = base64.b64decode(challenge)
        except binascii.Error:
            # Illegal challenge, give up, then quit
            self.sendLine(b"*")
            self._okresponse = self.esmtpAUTHMalformedChallenge
            self._failresponse = self.esmtpAUTHMalformedChallenge
        else:
            resp = auth.challengeResponse(self.secret, challenge)
            self._expected = [235, 334]
            self._okresponse = self.smtpState_maybeAuthenticated
            self.sendLine(base64.b64encode(resp))

    def smtpState_maybeAuthenticated(self, code, resp):
        """
        Called to handle the next message from the server after sending a
        response to a SASL challenge.  The server response might be another
        challenge or it might indicate authentication has succeeded.
        """
        if code == 235:
            # Yes, authenticated!
            del self._authinfo
            self.smtpState_from(code, resp)
        else:
            # No, not authenticated yet.  Keep trying.
            self._authResponse(self._authinfo, resp)


class ESMTP(SMTP):
    ctx = None
    canStartTLS = False
    startedTLS = False

    authenticated = False

    def __init__(self, chal=None, contextFactory=None):
        SMTP.__init__(self)
        if chal is None:
            chal = {}
        self.challengers = chal
        self.authenticated = False
        self.ctx = contextFactory

    def connectionMade(self):
        SMTP.connectionMade(self)
        self.canStartTLS = ITLSTransport.providedBy(self.transport)
        self.canStartTLS = self.canStartTLS and (self.ctx is not None)

    def greeting(self):
        return SMTP.greeting(self) + b" ESMTP"

    def extensions(self):
        """
        SMTP service extensions

        @return: the SMTP service extensions that are supported.
        @rtype: L{dict} with L{bytes} keys and a value of either L{None} or a
            L{list} of L{bytes}.
        """
        ext = {b"AUTH": list(self.challengers.keys())}
        if self.canStartTLS and not self.startedTLS:
            ext[b"STARTTLS"] = None
        return ext

    def lookupMethod(self, command):
        command = nativeString(command)

        m = SMTP.lookupMethod(self, command)
        if m is None:
            m = getattr(self, "ext_" + command.upper(), None)
        return m

    def listExtensions(self):
        r = []
        for c, v in self.extensions().items():
            if v is not None:
                if v:
                    # Intentionally omit extensions with empty argument lists
                    r.append(c + b" " + b" ".join(v))
            else:
                r.append(c)

        return b"\n".join(r)

    def do_EHLO(self, rest):
        peer = self.transport.getPeer().host

        if not isinstance(peer, bytes):
            peer = peer.encode("idna")

        self._helo = (rest, peer)
        self._from = None
        self._to = []
        self.sendCode(
            250,
            (
                self.host
                + b" Hello "
                + peer
                + b", nice to meet you\n"
                + self.listExtensions()
            ),
        )

    def ext_STARTTLS(self, rest):
        if self.startedTLS:
            self.sendCode(503, b"TLS already negotiated")
        elif self.ctx and self.canStartTLS:
            self.sendCode(220, b"Begin TLS negotiation now")
            self.transport.startTLS(self.ctx)
            self.startedTLS = True
        else:
            self.sendCode(454, b"TLS not available")

    def ext_AUTH(self, rest):
        if self.authenticated:
            self.sendCode(503, b"Already authenticated")
            return
        parts = rest.split(None, 1)
        chal = self.challengers.get(parts[0].upper(), lambda: None)()
        if not chal:
            self.sendCode(504, b"Unrecognized authentication type")
            return

        self.mode = AUTH
        self.challenger = chal

        if len(parts) > 1:
            chal.getChallenge()  # Discard it, apparently the client does not
            # care about it.
            rest = parts[1]
        else:
            rest = None
        self.state_AUTH(rest)

    def _cbAuthenticated(self, loginInfo):
        """
        Save the state resulting from a successful cred login and mark this
        connection as authenticated.
        """
        result = SMTP._cbAnonymousAuthentication(self, loginInfo)
        self.authenticated = True
        return result

    def _ebAuthenticated(self, reason):
        """
        Handle cred login errors by translating them to the SMTP authenticate
        failed.  Translate all other errors into a generic SMTP error code and
        log the failure for inspection.  Stop all errors from propagating.

        @param reason: Reason for failure.
        """
        self.challenge = None
        if reason.check(cred.error.UnauthorizedLogin):
            self.sendCode(535, b"Authentication failed")
        else:
            log.err(reason, "SMTP authentication failure")
            self.sendCode(451, b"Requested action aborted: local error in processing")

    def state_AUTH(self, response):
        """
        Handle one step of challenge/response authentication.

        @param response: The text of a response. If None, this
        function has been called as a result of an AUTH command with
        no initial response. A response of '*' aborts authentication,
        as per RFC 2554.
        """
        if self.portal is None:
            self.sendCode(454, b"Temporary authentication failure")
            self.mode = COMMAND
            return

        if response is None:
            challenge = self.challenger.getChallenge()
            encoded = base64.b64encode(challenge)
            self.sendCode(334, encoded)
            return

        if response == b"*":
            self.sendCode(501, b"Authentication aborted")
            self.challenger = None
            self.mode = COMMAND
            return

        try:
            uncoded = base64.b64decode(response)
        except (TypeError, binascii.Error):
            self.sendCode(501, b"Syntax error in parameters or arguments")
            self.challenger = None
            self.mode = COMMAND
            return

        self.challenger.setResponse(uncoded)
        if self.challenger.moreChallenges():
            challenge = self.challenger.getChallenge()
            coded = base64.b64encode(challenge)
            self.sendCode(334, coded)
            return

        self.mode = COMMAND
        result = self.portal.login(
            self.challenger, None, IMessageDeliveryFactory, IMessageDelivery
        )
        result.addCallback(self._cbAuthenticated)
        result.addCallback(
            lambda ign: self.sendCode(235, b"Authentication successful.")
        )
        result.addErrback(self._ebAuthenticated)


class SenderMixin:
    """
    Utility class for sending emails easily.

    Use with SMTPSenderFactory or ESMTPSenderFactory.
    """

    done = 0

    def getMailFrom(self):
        if not self.done:
            self.done = 1
            return str(self.factory.fromEmail)
        else:
            return None

    def getMailTo(self):
        return self.factory.toEmail

    def getMailData(self):
        return self.factory.file

    def sendError(self, exc):
        # Call the base class to close the connection with the SMTP server
        SMTPClient.sendError(self, exc)

        #  Do not retry to connect to SMTP Server if:
        #   1. No more retries left (This allows the correct error to be returned to the errorback)
        #   2. retry is false
        #   3. The error code is not in the 4xx range (Communication Errors)

        if self.factory.retries >= 0 or (
            not exc.retry and not (exc.code >= 400 and exc.code < 500)
        ):
            self.factory.sendFinished = True
            self.factory.result.errback(exc)

    def sentMail(self, code, resp, numOk, addresses, log):
        # Do not retry, the SMTP server acknowledged the request
        self.factory.sendFinished = True
        if code not in SUCCESS:
            errlog = []
            for addr, acode, aresp in addresses:
                if acode not in SUCCESS:
                    errlog.append(
                        addr + b": " + networkString("%03d" % (acode,)) + b" " + aresp
                    )

            errlog.append(log.str())

            exc = SMTPDeliveryError(code, resp, b"\n".join(errlog), addresses)
            self.factory.result.errback(exc)
        else:
            self.factory.result.callback((numOk, addresses))


class SMTPSender(SenderMixin, SMTPClient):
    """
    SMTP protocol that sends a single email based on information it
    gets from its factory, a L{SMTPSenderFactory}.
    """


class SMTPSenderFactory(protocol.ClientFactory):
    """
    Utility factory for sending emails easily.

    @type currentProtocol: L{SMTPSender}
    @ivar currentProtocol: The current running protocol returned by
        L{buildProtocol}.

    @type sendFinished: C{bool}
    @ivar sendFinished: When the value is set to True, it means the message has
        been sent or there has been an unrecoverable error or the sending has
        been cancelled. The default value is False.
    """

    domain = DNSNAME
    protocol: Type[SMTPClient] = SMTPSender

    def __init__(self, fromEmail, toEmail, file, deferred, retries=5, timeout=None):
        """
        @param fromEmail: The RFC 2821 address from which to send this
        message.

        @param toEmail: A sequence of RFC 2821 addresses to which to
        send this message.

        @param file: A file-like object containing the message to send.

        @param deferred: A Deferred to callback or errback when sending
        of this message completes.
        @type deferred: L{defer.Deferred}

        @param retries: The number of times to retry delivery of this
        message.

        @param timeout: Period, in seconds, for which to wait for
        server responses, or None to wait forever.
        """
        assert isinstance(retries, int)

        if isinstance(toEmail, str):
            toEmail = [toEmail.encode("ascii")]
        elif isinstance(toEmail, bytes):
            toEmail = [toEmail]
        else:
            toEmailFinal = []
            for _email in toEmail:
                if not isinstance(_email, bytes):
                    _email = _email.encode("ascii")

                toEmailFinal.append(_email)
            toEmail = toEmailFinal

        self.fromEmail = Address(fromEmail)
        self.nEmails = len(toEmail)
        self.toEmail = toEmail
        self.file = file
        self.result = deferred
        self.result.addBoth(self._removeDeferred)
        self.sendFinished = False
        self.currentProtocol = None

        self.retries = -retries
        self.timeout = timeout

    def _removeDeferred(self, result):
        del self.result
        return result

    def clientConnectionFailed(self, connector, err):
        self._processConnectionError(connector, err)

    def clientConnectionLost(self, connector, err):
        self._processConnectionError(connector, err)

    def _processConnectionError(self, connector, err):
        self.currentProtocol = None
        if (self.retries < 0) and (not self.sendFinished):
            log.msg("SMTP Client retrying server. Retry: %s" % -self.retries)

            # Rewind the file in case part of it was read while attempting to
            # send the message.
            self.file.seek(0, 0)
            connector.connect()
            self.retries += 1
        elif not self.sendFinished:
            # If we were unable to communicate with the SMTP server a ConnectionDone will be
            # returned. We want a more clear error message for debugging
            if err.check(error.ConnectionDone):
                err.value = SMTPConnectError(-1, "Unable to connect to server.")
            self.result.errback(err.value)

    def buildProtocol(self, addr):
        p = self.protocol(self.domain, self.nEmails * 2 + 2)
        p.factory = self
        p.timeout = self.timeout
        self.currentProtocol = p
        self.result.addBoth(self._removeProtocol)
        return p

    def _removeProtocol(self, result):
        """
        Remove the protocol created in C{buildProtocol}.

        @param result: The result/error passed to the callback/errback of
            L{defer.Deferred}.

        @return: The C{result} untouched.
        """
        if self.currentProtocol:
            self.currentProtocol = None
        return result


class LOGINCredentials(_lcredentials):
    """
    L{LOGINCredentials} generates challenges for I{LOGIN} authentication.

    For interoperability with Outlook, the challenge generated does not exactly
    match the one defined in the
    U{draft specification<http://sepp.oetiker.ch/sasl-2.1.19-ds/draft-murchison-sasl-login-00.txt>}.
    """

    def __init__(self):
        _lcredentials.__init__(self)
        self.challenges = [b"Password:", b"Username:"]


@implementer(IClientAuthentication)
class PLAINAuthenticator:
    def __init__(self, user):
        self.user = user

    def getName(self):
        return b"PLAIN"

    def challengeResponse(self, secret, chal=1):
        if chal == 1:
            return self.user + b"\0" + self.user + b"\0" + secret
        else:
            return b"\0" + self.user + b"\0" + secret


class ESMTPSender(SenderMixin, ESMTPClient):

    requireAuthentication = True
    requireTransportSecurity = True

    def __init__(self, username, secret, contextFactory=None, *args, **kw):
        self.heloFallback = 0
        self.username = username

        self._hostname = kw.pop("hostname", None)

        if contextFactory is None:
            contextFactory = self._getContextFactory()

        ESMTPClient.__init__(self, secret, contextFactory, *args, **kw)

        self._registerAuthenticators()

    def _registerAuthenticators(self):
        # Register Authenticator in order from most secure to least secure
        self.registerAuthenticator(CramMD5ClientAuthenticator(self.username))
        self.registerAuthenticator(LOGINAuthenticator(self.username))
        self.registerAuthenticator(PLAINAuthenticator(self.username))

    def _getContextFactory(self):
        if self.context is not None:
            return self.context
        if self._hostname is None:
            return None
        try:
            from twisted.internet.ssl import optionsForClientTLS
        except ImportError:
            return None
        else:
            context = optionsForClientTLS(self._hostname)
            return context


class ESMTPSenderFactory(SMTPSenderFactory):
    """
    Utility factory for sending emails easily.

    @type currentProtocol: L{ESMTPSender}
    @ivar currentProtocol: The current running protocol as made by
        L{buildProtocol}.
    """

    protocol = ESMTPSender

    def __init__(
        self,
        username,
        password,
        fromEmail,
        toEmail,
        file,
        deferred,
        retries=5,
        timeout=None,
        contextFactory=None,
        heloFallback=False,
        requireAuthentication=True,
        requireTransportSecurity=True,
        hostname=None,
    ):

        SMTPSenderFactory.__init__(
            self, fromEmail, toEmail, file, deferred, retries, timeout
        )
        self.username = username
        self.password = password
        self._contextFactory = contextFactory
        self._heloFallback = heloFallback
        self._requireAuthentication = requireAuthentication
        self._requireTransportSecurity = requireTransportSecurity
        self._hostname = hostname

    def buildProtocol(self, addr):
        """
        Build an L{ESMTPSender} protocol configured with C{heloFallback},
        C{requireAuthentication}, and C{requireTransportSecurity} as specified
        in L{__init__}.

        This sets L{currentProtocol} on the factory, as well as returning it.

        @rtype: L{ESMTPSender}
        """
        p = self.protocol(
            self.username,
            self.password,
            self._contextFactory,
            self.domain,
            self.nEmails * 2 + 2,
            hostname=self._hostname,
        )
        p.heloFallback = self._heloFallback
        p.requireAuthentication = self._requireAuthentication
        p.requireTransportSecurity = self._requireTransportSecurity
        p.factory = self
        p.timeout = self.timeout
        self.currentProtocol = p
        self.result.addBoth(self._removeProtocol)
        return p


def sendmail(
    smtphost,
    from_addr,
    to_addrs,
    msg,
    senderDomainName=None,
    port=25,
    reactor=reactor,
    username=None,
    password=None,
    requireAuthentication=False,
    requireTransportSecurity=False,
):
    """
    Send an email.

    This interface is intended to be a replacement for L{smtplib.SMTP.sendmail}
    and related methods. To maintain backwards compatibility, it will fall back
    to plain SMTP, if ESMTP support is not available. If ESMTP support is
    available, it will attempt to provide encryption via STARTTLS and
    authentication if a secret is provided.

    @param smtphost: The host the message should be sent to.
    @type smtphost: L{bytes}

    @param from_addr: The (envelope) address sending this mail.
    @type from_addr: L{bytes}

    @param to_addrs: A list of addresses to send this mail to.  A string will
        be treated as a list of one address.
    @type to_addrs: L{list} of L{bytes} or L{bytes}

    @param msg: The message, including headers, either as a file or a string.
        File-like objects need to support read() and close(). Lines must be
        delimited by '\\n'. If you pass something that doesn't look like a file,
        we try to convert it to a string (so you should be able to pass an
        L{email.message} directly, but doing the conversion with
        L{email.generator} manually will give you more control over the process).

    @param senderDomainName: Name by which to identify. If None, try to pick
        something sane (but this depends on external configuration and may not
        succeed).
    @type senderDomainName: L{bytes}

    @param port: Remote port to which to connect.
    @type port: L{int}

    @param username: The username to use, if wanting to authenticate.
    @type username: L{bytes} or L{unicode}

    @param password: The secret to use, if wanting to authenticate. If you do
        not specify this, SMTP authentication will not occur.
    @type password: L{bytes} or L{unicode}

    @param requireTransportSecurity: Whether or not STARTTLS is required.
    @type requireTransportSecurity: L{bool}

    @param requireAuthentication: Whether or not authentication is required.
    @type requireAuthentication: L{bool}

    @param reactor: The L{reactor} used to make the TCP connection.

    @rtype: L{Deferred}
    @returns: A cancellable L{Deferred}, its callback will be called if a
        message is sent to ANY address, the errback if no message is sent. When
        the C{cancel} method is called, it will stop retrying and disconnect
        the connection immediately.

        The callback will be called with a tuple (numOk, addresses) where numOk
        is the number of successful recipient addresses and addresses is a list
        of tuples (address, code, resp) giving the response to the RCPT command
        for each address.
    """
    if not hasattr(msg, "read"):
        # It's not a file
        msg = BytesIO(bytes(msg))

    def cancel(d):
        """
        Cancel the L{twisted.mail.smtp.sendmail} call, tell the factory not to
        retry and disconnect the connection.

        @param d: The L{defer.Deferred} to be cancelled.
        """
        factory.sendFinished = True
        if factory.currentProtocol:
            factory.currentProtocol.transport.abortConnection()
        else:
            # Connection hasn't been made yet
            connector.disconnect()

    d = defer.Deferred(cancel)

    if isinstance(username, str):
        username = username.encode("utf-8")
    if isinstance(password, str):
        password = password.encode("utf-8")

    tlsHostname = smtphost
    if not isinstance(tlsHostname, str):
        tlsHostname = _idnaText(tlsHostname)

    factory = ESMTPSenderFactory(
        username,
        password,
        from_addr,
        to_addrs,
        msg,
        d,
        heloFallback=True,
        requireAuthentication=requireAuthentication,
        requireTransportSecurity=requireTransportSecurity,
        hostname=tlsHostname,
    )

    if senderDomainName is not None:
        factory.domain = networkString(senderDomainName)

    connector = reactor.connectTCP(smtphost, port, factory)

    return d


import codecs


def xtext_encode(s, errors=None):
    r = []
    for ch in iterbytes(s):
        o = ord(ch)
        if ch == "+" or ch == "=" or o < 33 or o > 126:
            r.append(networkString(f"+{o:02X}"))
        else:
            r.append(bytes((o,)))
    return (b"".join(r), len(s))


def xtext_decode(s, errors=None):
    """
    Decode the xtext-encoded string C{s}.

    @param s: String to decode.
    @param errors: codec error handling scheme.
    @return: The decoded string.
    """
    r = []
    i = 0
    while i < len(s):
        if s[i : i + 1] == b"+":
            try:
                r.append(chr(int(bytes(s[i + 1 : i + 3]), 16)))
            except ValueError:
                r.append(ord(s[i : i + 3]))
            i += 3
        else:
            r.append(bytes(s[i : i + 1]).decode("ascii"))
            i += 1
    return ("".join(r), len(s))


class xtextStreamReader(codecs.StreamReader):
    def decode(self, s, errors="strict"):
        return xtext_decode(s)


class xtextStreamWriter(codecs.StreamWriter):
    def decode(self, s, errors="strict"):
        return xtext_encode(s)


def xtext_codec(name):
    if name == "xtext":
        return (xtext_encode, xtext_decode, xtextStreamReader, xtextStreamWriter)


codecs.register(xtext_codec)
