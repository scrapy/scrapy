# -*- test-case-name: twisted.mail.test.test_mail -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Infrastructure for relaying mail through a smart host.

Traditional peer-to-peer email has been increasingly replaced by smart host
configurations.  Instead of sending mail directly to the recipient, a sender
sends mail to a smart host.  The smart host finds the mail exchange server for
the recipient and sends on the message.
"""

import email.utils
import os
import pickle
import time
from typing import Type

from twisted.application import internet
from twisted.internet import protocol
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.error import DNSLookupError
from twisted.internet.protocol import connectionDone
from twisted.mail import bounce, relay, smtp
from twisted.python import log
from twisted.python.failure import Failure


class ManagedRelayerMixin:
    """
    SMTP Relayer which notifies a manager

    Notify the manager about successful mail, failed mail
    and broken connections
    """

    def __init__(self, manager):
        self.manager = manager

    @property
    def factory(self):
        return self._factory

    @factory.setter
    def factory(self, value):
        self._factory = value

    def sentMail(self, code, resp, numOk, addresses, log):
        """
        called when e-mail has been sent

        we will always get 0 or 1 addresses.
        """
        message = self.names[0]
        if code in smtp.SUCCESS:
            self.manager.notifySuccess(self.factory, message)
        else:
            self.manager.notifyFailure(self.factory, message)
        del self.messages[0]
        del self.names[0]

    def connectionLost(self, reason: Failure = connectionDone):
        """
        called when connection is broken

        notify manager we will try to send no more e-mail
        """
        self.manager.notifyDone(self.factory)


class SMTPManagedRelayer(ManagedRelayerMixin, relay.SMTPRelayer):  # type: ignore[misc]
    """
    An SMTP managed relayer.

    This managed relayer is an SMTP client which is responsible for sending a
    set of messages and keeping an attempt manager informed about its progress.

    @type factory: L{SMTPManagedRelayerFactory}
    @ivar factory: The factory that created this relayer.  This must be set by
        the factory.
    """

    def __init__(self, messages, manager, *args, **kw):
        """
        @type messages: L{list} of L{bytes}
        @param messages: The base filenames of messages to be relayed.

        @type manager: L{_AttemptManager}
        @param manager: An attempt manager.

        @type args: 1-L{tuple} of (0) L{bytes} or 2-L{tuple} of
            (0) L{bytes}, (1) L{int}
        @param args: Positional arguments for L{SMTPClient.__init__}

        @type kw: L{dict}
        @param kw: Keyword arguments for L{SMTPClient.__init__}
        """
        ManagedRelayerMixin.__init__(self, manager)
        relay.SMTPRelayer.__init__(self, messages, *args, **kw)


class ESMTPManagedRelayer(ManagedRelayerMixin, relay.ESMTPRelayer):  # type: ignore[misc]
    """
    An ESMTP managed relayer.

    This managed relayer is an ESMTP client which is responsible for sending a
    set of messages and keeping an attempt manager informed about its progress.
    """

    def __init__(self, messages, manager, *args, **kw):
        """
        @type messages: L{list} of L{bytes}
        @param messages: The base filenames of messages to be relayed.

        @type manager: L{_AttemptManager}
        @param manager: An attempt manager.

        @type args: 3-L{tuple} of (0) L{bytes}, (1) L{None} or
            L{ClientContextFactory
            <twisted.internet.ssl.ClientContextFactory>}, (2) L{bytes} or
            4-L{tuple} of (0) L{bytes}, (1) L{None} or
            L{ClientContextFactory
            <twisted.internet.ssl.ClientContextFactory>}, (2) L{bytes},
            (3) L{int}
        @param args: Positional arguments for L{ESMTPClient.__init__}

        @type kw: L{dict}
        @param kw: Keyword arguments for L{ESMTPClient.__init__}
        """
        ManagedRelayerMixin.__init__(self, manager)
        relay.ESMTPRelayer.__init__(self, messages, *args, **kw)


class SMTPManagedRelayerFactory(protocol.ClientFactory):
    """
    A factory to create an L{SMTPManagedRelayer}.

    This factory creates a managed relayer which relays a set of messages over
    SMTP and informs an attempt manager of its progress.

    @ivar messages: See L{__init__}
    @ivar manager: See L{__init__}

    @type protocol: callable which returns L{SMTPManagedRelayer}
    @ivar protocol: A callable which returns a managed relayer for SMTP.  See
        L{SMTPManagedRelayer.__init__} for parameters to the callable.

    @type pArgs: 1-L{tuple} of (0) L{bytes} or 2-L{tuple} of
        (0) L{bytes}, (1), L{int}
    @ivar pArgs: Positional arguments for L{SMTPClient.__init__}

    @type pKwArgs: L{dict}
    @ivar pKwArgs: Keyword arguments for L{SMTPClient.__init__}
    """

    protocol: "Type[protocol.Protocol]" = SMTPManagedRelayer

    def __init__(self, messages, manager, *args, **kw):
        """
        @type messages: L{list} of L{bytes}
        @param messages: The base filenames of messages to be relayed.

        @type manager: L{_AttemptManager}
        @param manager: An attempt manager.

        @type args: 1-L{tuple} of (0) L{bytes} or 2-L{tuple} of
            (0) L{bytes}, (1), L{int}
        @param args: Positional arguments for L{SMTPClient.__init__}

        @type kw: L{dict}
        @param kw: Keyword arguments for L{SMTPClient.__init__}
        """
        self.messages = messages
        self.manager = manager
        self.pArgs = args
        self.pKwArgs = kw

    def buildProtocol(self, addr):
        """
        Create an L{SMTPManagedRelayer}.

        @type addr: L{IAddress <twisted.internet.interfaces.IAddress>} provider
        @param addr: The address of the SMTP server.

        @rtype: L{SMTPManagedRelayer}
        @return: A managed relayer for SMTP.
        """
        protocol = self.protocol(
            self.messages, self.manager, *self.pArgs, **self.pKwArgs
        )
        protocol.factory = self
        return protocol

    def clientConnectionFailed(self, connector, reason):
        """
        Notify the attempt manager that a connection could not be established.

        @type connector: L{IConnector <twisted.internet.interfaces.IConnector>}
            provider
        @param connector: A connector.

        @type reason: L{Failure}
        @param reason: The reason the connection attempt failed.
        """
        self.manager.notifyNoConnection(self)
        self.manager.notifyDone(self)


class ESMTPManagedRelayerFactory(SMTPManagedRelayerFactory):
    """
    A factory to create an L{ESMTPManagedRelayer}.

    This factory creates a managed relayer which relays a set of messages over
    ESMTP and informs an attempt manager of its progress.

    @type protocol: callable which returns L{ESMTPManagedRelayer}
    @ivar protocol: A callable which returns a managed relayer for ESMTP.  See
        L{ESMTPManagedRelayer.__init__} for parameters to the callable.

    @ivar secret: See L{__init__}
    @ivar contextFactory: See L{__init__}
    """

    protocol = ESMTPManagedRelayer

    def __init__(self, messages, manager, secret, contextFactory, *args, **kw):
        """
        @type messages: L{list} of L{bytes}
        @param messages: The base filenames of messages to be relayed.

        @type manager: L{_AttemptManager}
        @param manager: An attempt manager.

        @type secret: L{bytes}
        @param secret: A string for the authentication challenge response.

        @type contextFactory: L{None} or
            L{ClientContextFactory <twisted.internet.ssl.ClientContextFactory>}
        @param contextFactory: An SSL context factory.

        @type args: 1-L{tuple} of (0) L{bytes} or 2-L{tuple} of
            (0) L{bytes}, (1), L{int}
        @param args: Positional arguments for L{SMTPClient.__init__}

        @param kw: Keyword arguments for L{SMTPClient.__init__}
        """
        self.secret = secret
        self.contextFactory = contextFactory
        SMTPManagedRelayerFactory.__init__(self, messages, manager, *args, **kw)

    def buildProtocol(self, addr):
        """
        Create an L{ESMTPManagedRelayer}.

        @type addr: L{IAddress <twisted.internet.interfaces.IAddress>} provider
        @param addr: The address of the ESMTP server.

        @rtype: L{ESMTPManagedRelayer}
        @return: A managed relayer for ESMTP.
        """
        s = self.secret and self.secret(addr)
        protocol = self.protocol(
            self.messages,
            self.manager,
            s,
            self.contextFactory,
            *self.pArgs,
            **self.pKwArgs,
        )
        protocol.factory = self
        return protocol


class Queue:
    """
    A queue for messages to be relayed.

    @ivar directory: See L{__init__}

    @type n: L{int}
    @ivar n: A number used to form unique filenames.

    @type waiting: L{dict} of L{bytes}
    @ivar waiting: The base filenames of messages waiting to be relayed.

    @type relayed: L{dict} of L{bytes}
    @ivar relayed: The base filenames of messages in the process of being
        relayed.

    @type noisy: L{bool}
    @ivar noisy: A flag which determines whether informational log messages
        will be generated (C{True}) or not (C{False}).
    """

    noisy = True

    def __init__(self, directory):
        """
        Initialize non-volatile state.

        @type directory: L{bytes}
        @param directory: The pathname of the directory holding messages in the
            queue.
        """
        self.directory = directory
        self._init()

    def _init(self):
        """
        Initialize volatile state.
        """
        self.n = 0
        self.waiting = {}
        self.relayed = {}
        self.readDirectory()

    def __getstate__(self):
        """
        Create a representation of the non-volatile state of the queue.

        @rtype: L{dict} mapping L{bytes} to L{object}
        @return: The non-volatile state of the queue.
        """
        return {"directory": self.directory}

    def __setstate__(self, state):
        """
        Restore the non-volatile state of the queue and recreate the volatile
        state.

        @type state: L{dict} mapping L{bytes} to L{object}
        @param state: The non-volatile state of the queue.
        """
        self.__dict__.update(state)
        self._init()

    def readDirectory(self):
        """
        Scan the message directory for new messages.
        """
        for message in os.listdir(self.directory):
            # Skip non data files
            if message[-2:] != "-D":
                continue
            self.addMessage(message[:-2])

    def getWaiting(self):
        """
        Return the base filenames of messages waiting to be relayed.

        @rtype: L{list} of L{bytes}
        @return: The base filenames of messages waiting to be relayed.
        """
        return self.waiting.keys()

    def hasWaiting(self):
        """
        Return an indication of whether the queue has messages waiting to be
        relayed.

        @rtype: L{bool}
        @return: C{True} if messages are waiting to be relayed.  C{False}
            otherwise.
        """
        return len(self.waiting) > 0

    def getRelayed(self):
        """
        Return the base filenames of messages in the process of being relayed.

        @rtype: L{list} of L{bytes}
        @return: The base filenames of messages in the process of being
            relayed.
        """
        return self.relayed.keys()

    def setRelaying(self, message):
        """
        Mark a message as being relayed.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        del self.waiting[message]
        self.relayed[message] = 1

    def setWaiting(self, message):
        """
        Mark a message as waiting to be relayed.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        del self.relayed[message]
        self.waiting[message] = 1

    def addMessage(self, message):
        """
        Mark a message as waiting to be relayed unless it is in the process of
        being relayed.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        if message not in self.relayed:
            self.waiting[message] = 1
            if self.noisy:
                log.msg("Set " + message + " waiting")

    def done(self, message):
        """
        Remove a message from the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.
        """
        message = os.path.basename(message)
        os.remove(self.getPath(message) + "-D")
        os.remove(self.getPath(message) + "-H")
        del self.relayed[message]

    def getPath(self, message):
        """
        Return the full base pathname of a message in the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.

        @rtype: L{bytes}
        @return: The full base pathname of the message.
        """
        return os.path.join(self.directory, message)

    def getEnvelope(self, message):
        """
        Get the envelope for a message.

        @type message: L{bytes}
        @param message: The base filename of a message.

        @rtype: L{list} of two L{bytes}
        @return: A list containing the origination and destination addresses
            for the message.
        """
        with self.getEnvelopeFile(message) as f:
            return pickle.load(f)

    def getEnvelopeFile(self, message):
        """
        Return the envelope file for a message in the queue.

        @type message: L{bytes}
        @param message: The base filename of a message.

        @rtype: file
        @return: The envelope file for the message.
        """
        return open(os.path.join(self.directory, message + "-H"), "rb")

    def createNewMessage(self):
        """
        Create a new message in the queue.

        @rtype: 2-L{tuple} of (0) file, (1) L{FileMessage}
        @return: The envelope file and a message receiver for a new message in
            the queue.
        """
        fname = f"{os.getpid()}_{time.time()}_{self.n}_{id(self)}"
        self.n = self.n + 1
        headerFile = open(os.path.join(self.directory, fname + "-H"), "wb")
        tempFilename = os.path.join(self.directory, fname + "-C")
        finalFilename = os.path.join(self.directory, fname + "-D")
        messageFile = open(tempFilename, "wb")

        from twisted.mail.mail import FileMessage

        return headerFile, FileMessage(messageFile, tempFilename, finalFilename)


class _AttemptManager:
    """
    A manager for an attempt to relay a set of messages to a mail exchange
    server.

    @ivar manager: See L{__init__}

    @type _completionDeferreds: L{list} of L{Deferred}
    @ivar _completionDeferreds: Deferreds which are to be notified when the
        attempt to relay is finished.
    """

    def __init__(self, manager, noisy=True, reactor=None):
        """
        @type manager: L{SmartHostSMTPRelayingManager}
        @param manager: A smart host.

        @type noisy: L{bool}
        @param noisy: A flag which determines whether informational log
            messages will be generated (L{True}) or not (L{False}).

        @type reactor: L{IReactorTime
            <twisted.internet.interfaces.IReactorTime>} provider
        @param reactor: A reactor which will be used to schedule delayed calls.
        """
        self.manager = manager
        self._completionDeferreds = []
        self.noisy = noisy

        if not reactor:
            from twisted.internet import reactor
        self.reactor = reactor

    def getCompletionDeferred(self):
        """
        Return a deferred which will fire when the attempt to relay is
        finished.

        @rtype: L{Deferred}
        @return: A deferred which will fire when the attempt to relay is
            finished.
        """
        self._completionDeferreds.append(Deferred())
        return self._completionDeferreds[-1]

    def _finish(self, relay, message):
        """
        Remove a message from the relay queue and from the smart host's list of
        messages being relayed.

        @type relay: L{SMTPManagedRelayerFactory}
        @param relay: The factory for the relayer which sent the message.

        @type message: L{bytes}
        @param message: The path of the file holding the message.
        """
        self.manager.managed[relay].remove(os.path.basename(message))
        self.manager.queue.done(message)

    def notifySuccess(self, relay, message):
        """
        Remove a message from the relay queue after it has been successfully
        sent.

        @type relay: L{SMTPManagedRelayerFactory}
        @param relay: The factory for the relayer which sent the message.

        @type message: L{bytes}
        @param message: The path of the file holding the message.
        """
        if self.noisy:
            log.msg("success sending %s, removing from queue" % message)
        self._finish(relay, message)

    def notifyFailure(self, relay, message):
        """
        Generate a bounce message for a message which cannot be relayed.

        @type relay: L{SMTPManagedRelayerFactory}
        @param relay: The factory for the relayer responsible for the message.

        @type message: L{bytes}
        @param message: The path of the file holding the message.
        """
        if self.noisy:
            log.msg("could not relay " + message)
        # Moshe - Bounce E-mail here
        # Be careful: if it's a bounced bounce, silently
        # discard it
        message = os.path.basename(message)
        with self.manager.queue.getEnvelopeFile(message) as fp:
            from_, to = pickle.load(fp)
        from_, to, bounceMessage = bounce.generateBounce(
            open(self.manager.queue.getPath(message) + "-D"), from_, to
        )
        fp, outgoingMessage = self.manager.queue.createNewMessage()
        with fp:
            pickle.dump([from_, to], fp)
        for line in bounceMessage.splitlines():
            outgoingMessage.lineReceived(line)
        outgoingMessage.eomReceived()
        self._finish(relay, self.manager.queue.getPath(message))

    def notifyDone(self, relay):
        """
        When the connection is lost or cannot be established, prepare to
        resend unsent messages and fire all deferred which are waiting for
        the completion of the attempt to relay.

        @type relay: L{SMTPManagedRelayerFactory}
        @param relay: The factory for the relayer for the connection.
        """
        for message in self.manager.managed.get(relay, ()):
            if self.noisy:
                log.msg("Setting " + message + " waiting")
            self.manager.queue.setWaiting(message)
        try:
            del self.manager.managed[relay]
        except KeyError:
            pass
        notifications = self._completionDeferreds
        self._completionDeferreds = None
        for d in notifications:
            d.callback(None)

    def notifyNoConnection(self, relay):
        """
        When a connection to the mail exchange server cannot be established,
        prepare to resend messages later.

        @type relay: L{SMTPManagedRelayerFactory}
        @param relay: The factory for the relayer meant to use the connection.
        """
        # Back off a bit
        try:
            msgs = self.manager.managed[relay]
        except KeyError:
            log.msg("notifyNoConnection passed unknown relay!")
            return

        if self.noisy:
            log.msg("Backing off on delivery of " + str(msgs))

        def setWaiting(queue, messages):
            map(queue.setWaiting, messages)

        self.reactor.callLater(30, setWaiting, self.manager.queue, msgs)
        del self.manager.managed[relay]


class SmartHostSMTPRelayingManager:
    """
    A smart host which uses SMTP managed relayers to send messages from the
    relay queue.

    L{checkState} must be called periodically at which time the state of the
    relay queue is checked and new relayers are created as needed.

    In order to relay a set of messages to a mail exchange server, a smart host
    creates an attempt manager and a managed relayer factory for that set of
    messages.  When a connection is made with the mail exchange server, the
    managed relayer factory creates a managed relayer to send the messages.
    The managed relayer reports on its progress to the attempt manager which,
    in turn, updates the smart host's relay queue and information about its
    managed relayers.

    @ivar queue: See L{__init__}.
    @ivar maxConnections: See L{__init__}.
    @ivar maxMessagesPerConnection: See L{__init__}.

    @type fArgs: 3-L{tuple} of (0) L{list} of L{bytes},
        (1) L{_AttemptManager}, (2) L{bytes} or 4-L{tuple} of (0) L{list}
        of L{bytes}, (1) L{_AttemptManager}, (2) L{bytes}, (3) L{int}
    @ivar fArgs: Positional arguments for
        L{SMTPManagedRelayerFactory.__init__}.

    @type fKwArgs: L{dict}
    @ivar fKwArgs: Keyword arguments for L{SMTPManagedRelayerFactory.__init__}.

    @type factory: callable which returns L{SMTPManagedRelayerFactory}
    @ivar factory: A callable which creates a factory for creating a managed
        relayer. See L{SMTPManagedRelayerFactory.__init__} for parameters to
        the callable.

    @type PORT: L{int}
    @ivar PORT: The port over which to connect to the SMTP server.

    @type mxcalc: L{None} or L{MXCalculator}
    @ivar mxcalc: A resource for mail exchange host lookups.

    @type managed: L{dict} mapping L{SMTPManagedRelayerFactory} to L{list} of
        L{bytes}
    @ivar managed: A mapping of factory for a managed relayer to
        filenames of messages the managed relayer is responsible for.
    """

    factory: Type[protocol.ClientFactory] = SMTPManagedRelayerFactory

    PORT = 25

    mxcalc = None

    def __init__(self, queue, maxConnections=2, maxMessagesPerConnection=10):
        """
        Initialize a smart host.

        The default values specify connection limits appropriate for a
        low-volume smart host.

        @type queue: L{Queue}
        @param queue: A relay queue.

        @type maxConnections: L{int}
        @param maxConnections: The maximum number of concurrent connections to
            SMTP servers.

        @type maxMessagesPerConnection: L{int}
        @param maxMessagesPerConnection: The maximum number of messages for
            which a relayer will be given responsibility.
        """
        self.maxConnections = maxConnections
        self.maxMessagesPerConnection = maxMessagesPerConnection
        self.managed = {}  # SMTP clients we're managing
        self.queue = queue
        self.fArgs = ()
        self.fKwArgs = {}

    def __getstate__(self):
        """
        Create a representation of the non-volatile state of this object.

        @rtype: L{dict} mapping L{bytes} to L{object}
        @return: The non-volatile state of the queue.
        """
        dct = self.__dict__.copy()
        del dct["managed"]
        return dct

    def __setstate__(self, state):
        """
        Restore the non-volatile state of this object and recreate the volatile
        state.

        @type state: L{dict} mapping L{bytes} to L{object}
        @param state: The non-volatile state of the queue.
        """
        self.__dict__.update(state)
        self.managed = {}

    def checkState(self):
        """
        Check the state of the relay queue and, if possible, launch relayers to
        handle waiting messages.

        @rtype: L{None} or L{Deferred}
        @return: No return value if no further messages can be relayed or a
            deferred which fires when all of the SMTP connections initiated by
            this call have disconnected.
        """
        self.queue.readDirectory()
        if len(self.managed) >= self.maxConnections:
            return
        if not self.queue.hasWaiting():
            return

        return self._checkStateMX()

    def _checkStateMX(self):
        nextMessages = self.queue.getWaiting()
        nextMessages.reverse()

        exchanges = {}
        for msg in nextMessages:
            from_, to = self.queue.getEnvelope(msg)
            name, addr = email.utils.parseaddr(to)
            parts = addr.split("@", 1)
            if len(parts) != 2:
                log.err("Illegal message destination: " + to)
                continue
            domain = parts[1]

            self.queue.setRelaying(msg)
            exchanges.setdefault(domain, []).append(self.queue.getPath(msg))
            if len(exchanges) >= (self.maxConnections - len(self.managed)):
                break

        if self.mxcalc is None:
            self.mxcalc = MXCalculator()

        relays = []
        for (domain, msgs) in exchanges.iteritems():
            manager = _AttemptManager(self, self.queue.noisy)
            factory = self.factory(msgs, manager, *self.fArgs, **self.fKwArgs)
            self.managed[factory] = map(os.path.basename, msgs)
            relayAttemptDeferred = manager.getCompletionDeferred()
            connectSetupDeferred = self.mxcalc.getMX(domain)
            connectSetupDeferred.addCallback(lambda mx: str(mx.name))
            connectSetupDeferred.addCallback(self._cbExchange, self.PORT, factory)
            connectSetupDeferred.addErrback(
                lambda err: (relayAttemptDeferred.errback(err), err)[1]
            )
            connectSetupDeferred.addErrback(self._ebExchange, factory, domain)
            relays.append(relayAttemptDeferred)
        return DeferredList(relays)

    def _cbExchange(self, address, port, factory):
        """
        Initiate a connection with a mail exchange server.

        This callback function runs after mail exchange server for the domain
        has been looked up.

        @type address: L{bytes}
        @param address: The hostname of a mail exchange server.

        @type port: L{int}
        @param port: A port number.

        @type factory: L{SMTPManagedRelayerFactory}
        @param factory: A factory which can create a relayer for the mail
            exchange server.
        """
        from twisted.internet import reactor

        reactor.connectTCP(address, port, factory)

    def _ebExchange(self, failure, factory, domain):
        """
        Prepare to resend messages later.

        This errback function runs when no mail exchange server for the domain
        can be found.

        @type failure: L{Failure}
        @param failure: The reason the mail exchange lookup failed.

        @type factory: L{SMTPManagedRelayerFactory}
        @param factory: A factory which can create a relayer for the mail
            exchange server.

        @type domain: L{bytes}
        @param domain: A domain.
        """
        log.err("Error setting up managed relay factory for " + domain)
        log.err(failure)

        def setWaiting(queue, messages):
            map(queue.setWaiting, messages)

        from twisted.internet import reactor

        reactor.callLater(30, setWaiting, self.queue, self.managed[factory])
        del self.managed[factory]


class SmartHostESMTPRelayingManager(SmartHostSMTPRelayingManager):
    """
    A smart host which uses ESMTP managed relayers to send messages from the
    relay queue.

    @type factory: callable which returns L{ESMTPManagedRelayerFactory}
    @ivar factory: A callable which creates a factory for creating a managed
        relayer. See L{ESMTPManagedRelayerFactory.__init__} for parameters to
        the callable.
    """

    factory = ESMTPManagedRelayerFactory


def _checkState(manager):
    """
    Prompt a relaying manager to check state.

    @type manager: L{SmartHostSMTPRelayingManager}
    @param manager: A relaying manager.
    """
    manager.checkState()


def RelayStateHelper(manager, delay):
    """
    Set up a periodic call to prompt a relaying manager to check state.

    @type manager: L{SmartHostSMTPRelayingManager}
    @param manager: A relaying manager.

    @type delay: L{float}
    @param delay: The number of seconds between calls.

    @rtype: L{TimerService <internet.TimerService>}
    @return: A service which periodically reminds a relaying manager to check
        state.
    """
    return internet.TimerService(delay, _checkState, manager)


class CanonicalNameLoop(Exception):
    """
    An error indicating that when trying to look up a mail exchange host, a set
    of canonical name records was found which form a cycle and resolution was
    abandoned.
    """


class CanonicalNameChainTooLong(Exception):
    """
    An error indicating that when trying to look up a mail exchange host, too
    many canonical name records which point to other canonical name records
    were encountered and resolution was abandoned.
    """


class MXCalculator:
    """
    A utility for looking up mail exchange hosts and tracking whether they are
    working or not.

    @type clock: L{IReactorTime <twisted.internet.interfaces.IReactorTime>}
        provider
    @ivar clock: A reactor which will be used to schedule timeouts.

    @type resolver: L{IResolver <twisted.internet.interfaces.IResolver>}
    @ivar resolver: A resolver.

    @type badMXs: L{dict} mapping L{bytes} to L{float}
    @ivar badMXs: A mapping of non-functioning mail exchange hostname to time
        at which another attempt at contacting it may be made.

    @type timeOutBadMX: L{int}
    @ivar timeOutBadMX: Period in seconds between attempts to contact a
        non-functioning mail exchange host.

    @type fallbackToDomain: L{bool}
    @ivar fallbackToDomain: A flag indicating whether to attempt to use the
        hostname directly when no mail exchange can be found (C{True}) or
        not (C{False}).
    """

    timeOutBadMX = 60 * 60  # One hour
    fallbackToDomain = True

    def __init__(self, resolver=None, clock=None):
        """
        @type resolver: L{IResolver <twisted.internet.interfaces.IResolver>}
            provider or L{None}
        @param resolver: A resolver.

        @type clock: L{IReactorTime <twisted.internet.interfaces.IReactorTime>}
            provider or L{None}
        @param clock: A reactor which will be used to schedule timeouts.
        """
        self.badMXs = {}
        if resolver is None:
            from twisted.names.client import createResolver

            resolver = createResolver()
        self.resolver = resolver
        if clock is None:
            from twisted.internet import reactor as clock
        self.clock = clock

    def markBad(self, mx):
        """
        Record that a mail exchange host is not currently functioning.

        @type mx: L{bytes}
        @param mx: The hostname of a mail exchange host.
        """
        self.badMXs[str(mx)] = self.clock.seconds() + self.timeOutBadMX

    def markGood(self, mx):
        """
        Record that a mail exchange host is functioning.

        @type mx: L{bytes}
        @param mx: The hostname of a mail exchange host.
        """
        try:
            del self.badMXs[mx]
        except KeyError:
            pass

    def getMX(self, domain, maximumCanonicalChainLength=3):
        """
        Find the name of a host that acts as a mail exchange server
        for a domain.

        @type domain: L{bytes}
        @param domain: A domain name.

        @type maximumCanonicalChainLength: L{int}
        @param maximumCanonicalChainLength: The maximum number of unique
            canonical name records to follow while looking up the mail exchange
            host.

        @rtype: L{Deferred} which successfully fires with L{Record_MX}
        @return: A deferred which succeeds with the MX record for the mail
            exchange server for the domain or fails if none can be found.
        """
        mailExchangeDeferred = self.resolver.lookupMailExchange(domain)
        mailExchangeDeferred.addCallback(self._filterRecords)
        mailExchangeDeferred.addCallback(
            self._cbMX, domain, maximumCanonicalChainLength
        )
        mailExchangeDeferred.addErrback(self._ebMX, domain)
        return mailExchangeDeferred

    def _filterRecords(self, records):
        """
        Organize the records of a DNS response by record name.

        @type records: 3-L{tuple} of (0) L{list} of L{RRHeader
            <twisted.names.dns.RRHeader>}, (1) L{list} of L{RRHeader
            <twisted.names.dns.RRHeader>}, (2) L{list} of L{RRHeader
            <twisted.names.dns.RRHeader>}
        @param records: Answer resource records, authority resource records and
            additional resource records.

        @rtype: L{dict} mapping L{bytes} to L{list} of L{IRecord
            <twisted.names.dns.IRecord>} provider
        @return: A mapping of record name to record payload.
        """
        recordBag = {}
        for answer in records[0]:
            recordBag.setdefault(str(answer.name), []).append(answer.payload)
        return recordBag

    def _cbMX(self, answers, domain, cnamesLeft):
        """
        Try to find the mail exchange host for a domain from the given DNS
        records.

        This will attempt to resolve canonical name record results.  It can
        recognize loops and will give up on non-cyclic chains after a specified
        number of lookups.

        @type answers: L{dict} mapping L{bytes} to L{list} of L{IRecord
            <twisted.names.dns.IRecord>} provider
        @param answers: A mapping of record name to record payload.

        @type domain: L{bytes}
        @param domain: A domain name.

        @type cnamesLeft: L{int}
        @param cnamesLeft: The number of unique canonical name records
            left to follow while looking up the mail exchange host.

        @rtype: L{Record_MX <twisted.names.dns.Record_MX>} or L{Failure}
        @return: An MX record for the mail exchange host or a failure if one
            cannot be found.
        """
        # Do this import here so that relaymanager.py doesn't depend on
        # twisted.names, only MXCalculator will.
        from twisted.names import dns, error

        seenAliases = set()
        exchanges = []
        # Examine the answers for the domain we asked about
        pertinentRecords = answers.get(domain, [])
        while pertinentRecords:
            record = pertinentRecords.pop()

            # If it's a CNAME, we'll need to do some more processing
            if record.TYPE == dns.CNAME:

                # Remember that this name was an alias.
                seenAliases.add(domain)

                canonicalName = str(record.name)
                # See if we have some local records which might be relevant.
                if canonicalName in answers:

                    # Make sure it isn't a loop contained entirely within the
                    # results we have here.
                    if canonicalName in seenAliases:
                        return Failure(CanonicalNameLoop(record))

                    pertinentRecords = answers[canonicalName]
                    exchanges = []
                else:
                    if cnamesLeft:
                        # Request more information from the server.
                        return self.getMX(canonicalName, cnamesLeft - 1)
                    else:
                        # Give up.
                        return Failure(CanonicalNameChainTooLong(record))

            # If it's an MX, collect it.
            if record.TYPE == dns.MX:
                exchanges.append((record.preference, record))

        if exchanges:
            exchanges.sort()
            for (preference, record) in exchanges:
                host = str(record.name)
                if host not in self.badMXs:
                    return record
                t = self.clock.seconds() - self.badMXs[host]
                if t >= 0:
                    del self.badMXs[host]
                    return record
            return exchanges[0][1]
        else:
            # Treat no answers the same as an error - jump to the errback to
            # try to look up an A record.  This provides behavior described as
            # a special case in RFC 974 in the section headed I{Interpreting
            # the List of MX RRs}.
            return Failure(error.DNSNameError(f"No MX records for {domain!r}"))

    def _ebMX(self, failure, domain):
        """
        Attempt to use the name of the domain directly when mail exchange
        lookup fails.

        @type failure: L{Failure}
        @param failure: The reason for the lookup failure.

        @type domain: L{bytes}
        @param domain: The domain name.

        @rtype: L{Record_MX <twisted.names.dns.Record_MX>} or L{Failure}
        @return: An MX record for the domain or a failure if the fallback to
            domain option is not in effect and an error, other than not
            finding an MX record, occurred during lookup.

        @raise IOError: When no MX record could be found and the fallback to
            domain option is not in effect.

        @raise DNSLookupError: When no MX record could be found and the
            fallback to domain option is in effect but no address for the
            domain could be found.
        """
        from twisted.names import dns, error

        if self.fallbackToDomain:
            failure.trap(error.DNSNameError)
            log.msg(
                "MX lookup failed; attempting to use hostname ({}) directly".format(
                    domain
                )
            )

            # Alright, I admit, this is a bit icky.
            d = self.resolver.getHostByName(domain)

            def cbResolved(addr):
                return dns.Record_MX(name=addr)

            def ebResolved(err):
                err.trap(error.DNSNameError)
                raise DNSLookupError()

            d.addCallbacks(cbResolved, ebResolved)
            return d
        elif failure.check(error.DNSNameError):
            raise OSError(f"No MX found for {domain!r}")
        return failure
