# -*- test-case-name: twisted.mail.test.test_mail -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Mail service support.
"""

# System imports
import os
import warnings

from zope.interface import implementer

from twisted.application import internet, service
from twisted.cred.portal import Portal

# Twisted imports
from twisted.internet import defer

# Sibling imports
from twisted.mail import protocols, smtp
from twisted.mail.interfaces import IAliasableDomain, IDomain
from twisted.python import log, util


class DomainWithDefaultDict:
    """
    A simulated dictionary for mapping domain names to domain objects with
    a default value for non-existing keys.

    @ivar domains: See L{__init__}
    @ivar default: See L{__init__}
    """

    def __init__(self, domains, default):
        """
        @type domains: L{dict} of L{bytes} -> L{IDomain} provider
        @param domains: A mapping of domain name to domain object.

        @type default: L{IDomain} provider
        @param default: The default domain.
        """
        self.domains = domains
        self.default = default

    def setDefaultDomain(self, domain):
        """
        Set the default domain.

        @type domain: L{IDomain} provider
        @param domain: The default domain.
        """
        self.default = domain

    def has_key(self, name):
        """
        Test for the presence of a domain name in this dictionary.

        This always returns C{True} because a default value will be returned
        if the name doesn't exist in this dictionary.

        @type name: L{bytes}
        @param name: A domain name.

        @rtype: L{bool}
        @return: C{True} to indicate that the domain name is in this
            dictionary.
        """
        warnings.warn(
            "twisted.mail.mail.DomainWithDefaultDict.has_key was deprecated "
            "in Twisted 16.3.0. "
            "Use the `in` keyword instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        return 1

    @classmethod
    def fromkeys(klass, keys, value=None):
        """
        Create a new L{DomainWithDefaultDict} with the specified keys.

        @type keys: iterable of L{bytes}
        @param keys: Domain names to serve as keys in the new dictionary.

        @type value: L{None} or L{IDomain} provider
        @param value: A domain object to serve as the value for all new keys
            in the dictionary.

        @rtype: L{DomainWithDefaultDict}
        @return: A new dictionary.
        """
        d = klass()
        for k in keys:
            d[k] = value
        return d

    def __contains__(self, name):
        """
        Test for the presence of a domain name in this dictionary.

        This always returns C{True} because a default value will be returned
        if the name doesn't exist in this dictionary.

        @type name: L{bytes}
        @param name: A domain name.

        @rtype: L{bool}
        @return: C{True} to indicate that the domain name is in this
            dictionary.
        """
        return 1

    def __getitem__(self, name):
        """
        Look up a domain name and, if it is present, return the domain object
        associated with it.  Otherwise return the default domain.

        @type name: L{bytes}
        @param name: A domain name.

        @rtype: L{IDomain} provider or L{None}
        @return: A domain object.
        """
        return self.domains.get(name, self.default)

    def __setitem__(self, name, value):
        """
        Associate a domain object with a domain name in this dictionary.

        @type name: L{bytes}
        @param name: A domain name.

        @type value: L{IDomain} provider
        @param value: A domain object.
        """
        self.domains[name] = value

    def __delitem__(self, name):
        """
        Delete the entry for a domain name in this dictionary.

        @type name: L{bytes}
        @param name: A domain name.
        """
        del self.domains[name]

    def __iter__(self):
        """
        Return an iterator over the domain names in this dictionary.

        @rtype: iterator over L{bytes}
        @return: An iterator over the domain names.
        """
        return iter(self.domains)

    def __len__(self):
        """
        Return the number of domains in this dictionary.

        @rtype: L{int}
        @return: The number of domains in this dictionary.
        """
        return len(self.domains)

    def __str__(self) -> str:
        """
        Build an informal string representation of this dictionary.

        @rtype: L{bytes}
        @return: A string containing the mapping of domain names to domain
            objects.
        """
        return f"<DomainWithDefaultDict {self.domains}>"

    def __repr__(self) -> str:
        """
        Build an "official" string representation of this dictionary.

        @rtype: L{bytes}
        @return: A pseudo-executable string describing the underlying domain
            mapping of this object.
        """
        return f"DomainWithDefaultDict({self.domains})"

    def get(self, key, default=None):
        """
        Look up a domain name in this dictionary.

        @type key: L{bytes}
        @param key: A domain name.

        @type default: L{IDomain} provider or L{None}
        @param default: A domain object to be returned if the domain name is
            not in this dictionary.

        @rtype: L{IDomain} provider or L{None}
        @return: The domain object associated with the domain name if it is in
            this dictionary.  Otherwise, the default value.
        """
        return self.domains.get(key, default)

    def copy(self):
        """
        Make a copy of this dictionary.

        @rtype: L{DomainWithDefaultDict}
        @return: A copy of this dictionary.
        """
        return DomainWithDefaultDict(self.domains.copy(), self.default)

    def iteritems(self):
        """
        Return an iterator over the domain name/domain object pairs in the
        dictionary.

        Using the returned iterator while adding or deleting entries from the
        dictionary may result in a L{RuntimeError} or failing to iterate over
        all the domain name/domain object pairs.

        @rtype: iterator over 2-L{tuple} of (E{1}) L{bytes},
            (E{2}) L{IDomain} provider or L{None}
        @return: An iterator over the domain name/domain object pairs.
        """
        return self.domains.iteritems()

    def iterkeys(self):
        """
        Return an iterator over the domain names in this dictionary.

        Using the returned iterator while adding or deleting entries from the
        dictionary may result in a L{RuntimeError} or failing to iterate over
        all the domain names.

        @rtype: iterator over L{bytes}
        @return: An iterator over the domain names.
        """
        return self.domains.iterkeys()

    def itervalues(self):
        """
        Return an iterator over the domain objects in this dictionary.

        Using the returned iterator while adding or deleting entries from the
        dictionary may result in a L{RuntimeError} or failing to iterate over
        all the domain objects.

        @rtype: iterator over L{IDomain} provider or
            L{None}
        @return: An iterator over the domain objects.
        """
        return self.domains.itervalues()

    def keys(self):
        """
        Return a list of all domain names in this dictionary.

        @rtype: L{list} of L{bytes}
        @return: The domain names in this dictionary.

        """
        return self.domains.keys()

    def values(self):
        """
        Return a list of all domain objects in this dictionary.

        @rtype: L{list} of L{IDomain} provider or L{None}
        @return: The domain objects in this dictionary.
        """
        return self.domains.values()

    def items(self):
        """
        Return a list of all domain name/domain object pairs in this
        dictionary.

        @rtype: L{list} of 2-L{tuple} of (E{1}) L{bytes}, (E{2}) L{IDomain}
            provider or L{None}
        @return: Domain name/domain object pairs in this dictionary.
        """
        return self.domains.items()

    def popitem(self):
        """
        Remove a random domain name/domain object pair from this dictionary and
        return it as a tuple.

        @rtype: 2-L{tuple} of (E{1}) L{bytes}, (E{2}) L{IDomain} provider or
            L{None}
        @return: A domain name/domain object pair.

        @raise KeyError: When this dictionary is empty.
        """
        return self.domains.popitem()

    def update(self, other):
        """
        Update this dictionary with domain name/domain object pairs from
        another dictionary.

        When this dictionary contains a domain name which is in the other
        dictionary, its value will be overwritten.

        @type other: L{dict} of L{bytes} -> L{IDomain} provider and/or
            L{bytes} -> L{None}
        @param other: Another dictionary of domain name/domain object pairs.

        @rtype: L{None}
        @return: None.
        """
        return self.domains.update(other)

    def clear(self):
        """
        Remove all items from this dictionary.

        @rtype: L{None}
        @return: None.
        """
        return self.domains.clear()

    def setdefault(self, key, default):
        """
        Return the domain object associated with the domain name if it is
        present in this dictionary. Otherwise, set the value for the
        domain name to the default and return that value.

        @type key: L{bytes}
        @param key: A domain name.

        @type default: L{IDomain} provider
        @param default: A domain object.

        @rtype: L{IDomain} provider or L{None}
        @return: The domain object associated with the domain name.
        """
        return self.domains.setdefault(key, default)


@implementer(IDomain)
class BounceDomain:
    """
    A domain with no users.

    This can be used to block off a domain.
    """

    def exists(self, user):
        """
        Raise an exception to indicate that the user does not exist in this
        domain.

        @type user: L{User}
        @param user: A user.

        @raise SMTPBadRcpt: When the given user does not exist in this domain.
        """
        raise smtp.SMTPBadRcpt(user)

    def willRelay(self, user, protocol):
        """
        Indicate that this domain will not relay.

        @type user: L{Address}
        @param user: The destination address.

        @type protocol: L{Protocol <twisted.internet.protocol.Protocol>}
        @param protocol: The protocol over which the message to be relayed is
            being received.

        @rtype: L{bool}
        @return: C{False}.
        """
        return False

    def addUser(self, user, password):
        """
        Ignore attempts to add a user to this domain.

        @type user: L{bytes}
        @param user: A username.

        @type password: L{bytes}
        @param password: A password.
        """
        pass

    def getCredentialsCheckers(self):
        """
        Return no credentials checkers for this domain.

        @rtype: L{list}
        @return: The empty list.
        """
        return []


@implementer(smtp.IMessage)
class FileMessage:
    """
    A message receiver which delivers a message to a file.

    @ivar fp: See L{__init__}.
    @ivar name: See L{__init__}.
    @ivar finalName: See L{__init__}.
    """

    def __init__(self, fp, name, finalName):
        """
        @type fp: file-like object
        @param fp: The file in which to store the message while it is being
            received.

        @type name: L{bytes}
        @param name: The full path name of the temporary file.

        @type finalName: L{bytes}
        @param finalName: The full path name that should be given to the file
            holding the message after it has been fully received.
        """
        self.fp = fp
        self.name = name
        self.finalName = finalName

    def lineReceived(self, line):
        """
        Write a received line to the file.

        @type line: L{bytes}
        @param line: A received line.
        """
        self.fp.write(line + b"\n")

    def eomReceived(self):
        """
        At the end of message, rename the file holding the message to its
        final name.

        @rtype: L{Deferred} which successfully results in L{bytes}
        @return: A deferred which returns the final name of the file.
        """
        self.fp.close()
        os.rename(self.name, self.finalName)
        return defer.succeed(self.finalName)

    def connectionLost(self):
        """
        Delete the file holding the partially received message.
        """
        self.fp.close()
        os.remove(self.name)


class MailService(service.MultiService):
    """
    An email service.

    @type queue: L{Queue} or L{None}
    @ivar queue: A queue for outgoing messages.

    @type domains: L{dict} of L{bytes} -> L{IDomain} provider
    @ivar domains: A mapping of supported domain name to domain object.

    @type portals: L{dict} of L{bytes} -> L{Portal}
    @ivar portals: A mapping of domain name to authentication portal.

    @type aliases: L{None} or L{dict} of
        L{bytes} -> L{IAlias} provider
    @ivar aliases: A mapping of domain name to alias.

    @type smtpPortal: L{Portal}
    @ivar smtpPortal: A portal for authentication for the SMTP server.

    @type monitor: L{FileMonitoringService}
    @ivar monitor: A service to monitor changes to files.
    """

    queue = None
    domains = None
    portals = None
    aliases = None
    smtpPortal = None

    def __init__(self):
        """
        Initialize the mail service.
        """
        service.MultiService.__init__(self)
        # Domains and portals for "client" protocols - POP3, IMAP4, etc
        self.domains = DomainWithDefaultDict({}, BounceDomain())
        self.portals = {}

        self.monitor = FileMonitoringService()
        self.monitor.setServiceParent(self)
        self.smtpPortal = Portal(self)

    def getPOP3Factory(self):
        """
        Create a POP3 protocol factory.

        @rtype: L{POP3Factory}
        @return: A POP3 protocol factory.
        """
        return protocols.POP3Factory(self)

    def getSMTPFactory(self):
        """
        Create an SMTP protocol factory.

        @rtype: L{SMTPFactory <protocols.SMTPFactory>}
        @return: An SMTP protocol factory.
        """
        return protocols.SMTPFactory(self, self.smtpPortal)

    def getESMTPFactory(self):
        """
        Create an ESMTP protocol factory.

        @rtype: L{ESMTPFactory <protocols.ESMTPFactory>}
        @return: An ESMTP protocol factory.
        """
        return protocols.ESMTPFactory(self, self.smtpPortal)

    def addDomain(self, name, domain):
        """
        Add a domain for which the service will accept email.

        @type name: L{bytes}
        @param name: A domain name.

        @type domain: L{IDomain} provider
        @param domain: A domain object.
        """
        portal = Portal(domain)
        map(portal.registerChecker, domain.getCredentialsCheckers())
        self.domains[name] = domain
        self.portals[name] = portal
        if self.aliases and IAliasableDomain.providedBy(domain):
            domain.setAliasGroup(self.aliases)

    def setQueue(self, queue):
        """
        Set the queue for outgoing emails.

        @type queue: L{Queue}
        @param queue: A queue for outgoing messages.
        """
        self.queue = queue

    def requestAvatar(self, avatarId, mind, *interfaces):
        """
        Return a message delivery for an authenticated SMTP user.

        @type avatarId: L{bytes}
        @param avatarId: A string which identifies an authenticated user.

        @type mind: L{None}
        @param mind: Unused.

        @type interfaces: n-L{tuple} of C{zope.interface.Interface}
        @param interfaces: A group of interfaces one of which the avatar must
            support.

        @rtype: 3-L{tuple} of (E{1}) L{IMessageDelivery},
            (E{2}) L{ESMTPDomainDelivery}, (E{3}) no-argument callable
        @return: A tuple of the supported interface, a message delivery, and
            a logout function.

        @raise NotImplementedError: When the given interfaces do not include
            L{IMessageDelivery}.
        """
        if smtp.IMessageDelivery in interfaces:
            a = protocols.ESMTPDomainDelivery(self, avatarId)
            return smtp.IMessageDelivery, a, lambda: None
        raise NotImplementedError()

    def lookupPortal(self, name):
        """
        Find the portal for a domain.

        @type name: L{bytes}
        @param name: A domain name.

        @rtype: L{Portal}
        @return: A portal.
        """
        return self.portals[name]

    def defaultPortal(self):
        """
        Return the portal for the default domain.

        The default domain is named ''.

        @rtype: L{Portal}
        @return: The portal for the default domain.
        """
        return self.portals[""]


class FileMonitoringService(internet.TimerService):
    """
    A service for monitoring changes to files.

    @type files: L{list} of L{list} of (E{1}) L{float}, (E{2}) L{bytes},
        (E{3}) callable which takes a L{bytes} argument, (E{4}) L{float}
    @ivar files: Information about files to be monitored.  Each list entry
        provides the following information for a file: interval in seconds
        between checks, filename, callback function, time of last modification
        to the file.

    @type intervals: L{_IntervalDifferentialIterator
        <twisted.python.util._IntervalDifferentialIterator>}
    @ivar intervals: Intervals between successive file checks.

    @type _call: L{IDelayedCall <twisted.internet.interfaces.IDelayedCall>}
        provider
    @ivar _call: The next scheduled call to check a file.

    @type index: L{int}
    @ivar index: The index of the next file to be checked.
    """

    def __init__(self):
        """
        Initialize the file monitoring service.
        """
        self.files = []
        self.intervals = iter(util.IntervalDifferential([], 60))

    def startService(self):
        """
        Start the file monitoring service.
        """
        service.Service.startService(self)
        self._setupMonitor()

    def _setupMonitor(self):
        """
        Schedule the next monitoring call.
        """
        from twisted.internet import reactor

        t, self.index = self.intervals.next()
        self._call = reactor.callLater(t, self._monitor)

    def stopService(self):
        """
        Stop the file monitoring service.
        """
        service.Service.stopService(self)
        if self._call:
            self._call.cancel()
            self._call = None

    def monitorFile(self, name, callback, interval=10):
        """
        Start monitoring a file for changes.

        @type name: L{bytes}
        @param name: The name of a file to monitor.

        @type callback: callable which takes a L{bytes} argument
        @param callback: The function to call when the file has changed.

        @type interval: L{float}
        @param interval: The interval in seconds between checks.
        """
        try:
            mtime = os.path.getmtime(name)
        except BaseException:
            mtime = 0
        self.files.append([interval, name, callback, mtime])
        self.intervals.addInterval(interval)

    def unmonitorFile(self, name):
        """
        Stop monitoring a file.

        @type name: L{bytes}
        @param name: A file name.
        """
        for i in range(len(self.files)):
            if name == self.files[i][1]:
                self.intervals.removeInterval(self.files[i][0])
                del self.files[i]
                break

    def _monitor(self):
        """
        Monitor a file and make a callback if it has changed.
        """
        self._call = None
        if self.index is not None:
            name, callback, mtime = self.files[self.index][1:]
            try:
                now = os.path.getmtime(name)
            except BaseException:
                now = 0
            if now > mtime:
                log.msg(f"{name} changed, notifying listener")
                self.files[self.index][3] = now
                callback(name)
        self._setupMonitor()
