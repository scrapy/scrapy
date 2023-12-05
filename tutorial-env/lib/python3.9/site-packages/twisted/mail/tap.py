# -*- test-case-name: twisted.mail.test.test_options -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Support for creating mail servers with twistd.
"""

import os

from twisted.application import internet
from twisted.cred import checkers, strcred
from twisted.internet import endpoints
from twisted.mail import alias, mail, maildir, relay, relaymanager
from twisted.python import usage


class Options(usage.Options, strcred.AuthOptionMixin):
    """
    An options list parser for twistd mail.

    @type synopsis: L{bytes}
    @ivar synopsis: A description of options for use in the usage message.

    @type optParameters: L{list} of L{list} of (0) L{bytes}, (1) L{bytes},
        (2) L{object}, (3) L{bytes}, (4) L{None} or
        callable which takes L{bytes} and returns L{object}
    @ivar optParameters: Information about supported parameters.  See
        L{Options <twisted.python.usage.Options>} for details.

    @type optFlags: L{list} of L{list} of (0) L{bytes}, (1) L{bytes} or
        L{None}, (2) L{bytes}
    @ivar optFlags: Information about supported flags.  See
        L{Options <twisted.python.usage.Options>} for details.

    @type _protoDefaults: L{dict} mapping L{bytes} to L{int}
    @ivar _protoDefaults: A mapping of default service to port.

    @type compData: L{Completions <usage.Completions>}
    @ivar compData: Metadata for the shell tab completion system.

    @type longdesc: L{bytes}
    @ivar longdesc: A long description of the plugin for use in the usage
        message.

    @type service: L{MailService}
    @ivar service: The email service.

    @type last_domain: L{IDomain} provider or L{None}
    @ivar last_domain: The most recently specified domain.
    """

    synopsis = "[options]"

    optParameters = [
        [
            "relay",
            "R",
            None,
            "Relay messages according to their envelope 'To', using "
            "the given path as a queue directory.",
        ],
        ["hostname", "H", None, "The hostname by which to identify this server."],
    ]

    optFlags = [
        ["esmtp", "E", "Use RFC 1425/1869 SMTP extensions"],
        ["disable-anonymous", None, "Disallow non-authenticated SMTP connections"],
        ["no-pop3", None, "Disable the default POP3 server."],
        ["no-smtp", None, "Disable the default SMTP server."],
    ]

    _protoDefaults = {
        "pop3": 8110,
        "smtp": 8025,
    }

    compData = usage.Completions(optActions={"hostname": usage.CompleteHostnames()})

    longdesc = """
    An SMTP / POP3 email server plugin for twistd.

    Examples:

    1. SMTP and POP server

    twistd mail --maildirdbmdomain=example.com=/tmp/example.com
    --user=joe=password

    Starts an SMTP server that only accepts emails to joe@example.com and saves
    them to /tmp/example.com.

    Also starts a POP mail server which will allow a client to log in using
    username: joe@example.com and password: password and collect any email that
    has been saved in /tmp/example.com.

    2. SMTP relay

    twistd mail --relay=/tmp/mail_queue

    Starts an SMTP server that accepts emails to any email address and relays
    them to an appropriate remote SMTP server. Queued emails will be
    temporarily stored in /tmp/mail_queue.
    """

    def __init__(self):
        """
        Parse options and create a mail service.
        """
        usage.Options.__init__(self)
        self.service = mail.MailService()
        self.last_domain = None
        for service in self._protoDefaults:
            self[service] = []

    def addEndpoint(self, service, description):
        """
        Add an endpoint to a service.

        @type service: L{bytes}
        @param service: A service, either C{b'smtp'} or C{b'pop3'}.

        @type description: L{bytes}
        @param description: An endpoint description string or a TCP port
            number.
        """
        from twisted.internet import reactor

        self[service].append(endpoints.serverFromString(reactor, description))

    def opt_pop3(self, description):
        """
        Add a POP3 port listener on the specified endpoint.

        You can listen on multiple ports by specifying multiple --pop3 options.
        """
        self.addEndpoint("pop3", description)

    opt_p = opt_pop3

    def opt_smtp(self, description):
        """
        Add an SMTP port listener on the specified endpoint.

        You can listen on multiple ports by specifying multiple --smtp options.
        """
        self.addEndpoint("smtp", description)

    opt_s = opt_smtp

    def opt_default(self):
        """
        Make the most recently specified domain the default domain.
        """
        if self.last_domain:
            self.service.addDomain("", self.last_domain)
        else:
            raise usage.UsageError("Specify a domain before specifying using --default")

    opt_D = opt_default

    def opt_maildirdbmdomain(self, domain):
        """
        Generate an SMTP/POP3 virtual domain.

        This option requires an argument of the form 'NAME=PATH' where NAME is
        the DNS domain name for which email will be accepted and where PATH is
        a the filesystem path to a Maildir folder.
        [Example: 'example.com=/tmp/example.com']
        """
        try:
            name, path = domain.split("=")
        except ValueError:
            raise usage.UsageError(
                "Argument to --maildirdbmdomain must be of the form 'name=path'"
            )

        self.last_domain = maildir.MaildirDirdbmDomain(
            self.service, os.path.abspath(path)
        )
        self.service.addDomain(name, self.last_domain)

    opt_d = opt_maildirdbmdomain

    def opt_user(self, user_pass):
        """
        Add a user and password to the last specified domain.
        """
        try:
            user, password = user_pass.split("=", 1)
        except ValueError:
            raise usage.UsageError(
                "Argument to --user must be of the form 'user=password'"
            )
        if self.last_domain:
            self.last_domain.addUser(user, password)
        else:
            raise usage.UsageError("Specify a domain before specifying users")

    opt_u = opt_user

    def opt_bounce_to_postmaster(self):
        """
        Send undeliverable messages to the postmaster.
        """
        self.last_domain.postmaster = 1

    opt_b = opt_bounce_to_postmaster

    def opt_aliases(self, filename):
        """
        Specify an aliases(5) file to use for the last specified domain.
        """
        if self.last_domain is not None:
            if mail.IAliasableDomain.providedBy(self.last_domain):
                aliases = alias.loadAliasFile(self.service.domains, filename)
                self.last_domain.setAliasGroup(aliases)
                self.service.monitor.monitorFile(
                    filename, AliasUpdater(self.service.domains, self.last_domain)
                )
            else:
                raise usage.UsageError(
                    "%s does not support alias files"
                    % (self.last_domain.__class__.__name__,)
                )
        else:
            raise usage.UsageError("Specify a domain before specifying aliases")

    opt_A = opt_aliases

    def _getEndpoints(self, reactor, service):
        """
        Return a list of endpoints for the specified service, constructing
        defaults if necessary.

        If no endpoints were configured for the service and the protocol
        was not explicitly disabled with a I{--no-*} option, a default
        endpoint for the service is created.

        @type reactor: L{IReactorTCP <twisted.internet.interfaces.IReactorTCP>}
            provider
        @param reactor: If any endpoints are created, the reactor with
            which they are created.

        @type service: L{bytes}
        @param service: The type of service for which to retrieve endpoints,
            either C{b'pop3'} or C{b'smtp'}.

        @rtype: L{list} of L{IStreamServerEndpoint
            <twisted.internet.interfaces.IStreamServerEndpoint>} provider
        @return: The endpoints for the specified service as configured by the
            command line parameters.
        """
        if self[service]:
            # If there are any services set up, just return those.
            return self[service]
        elif self["no-" + service]:
            # If there are no services, but the service was explicitly disabled,
            # return nothing.
            return []
        else:
            # Otherwise, return the old default service.
            return [endpoints.TCP4ServerEndpoint(reactor, self._protoDefaults[service])]

    def postOptions(self):
        """
        Check the validity of the specified set of options and
        configure authentication.

        @raise UsageError: When the set of options is invalid.
        """
        from twisted.internet import reactor

        if self["esmtp"] and self["hostname"] is None:
            raise usage.UsageError("--esmtp requires --hostname")

        # If the --auth option was passed, this will be present -- otherwise,
        # it won't be, which is also a perfectly valid state.
        if "credCheckers" in self:
            for ch in self["credCheckers"]:
                self.service.smtpPortal.registerChecker(ch)

        if not self["disable-anonymous"]:
            self.service.smtpPortal.registerChecker(checkers.AllowAnonymousAccess())

        anything = False
        for service in self._protoDefaults:
            self[service] = self._getEndpoints(reactor, service)
            if self[service]:
                anything = True

        if not anything:
            raise usage.UsageError("You cannot disable all protocols")


class AliasUpdater:
    """
    A callable object which updates the aliases for a domain from an aliases(5)
    file.

    @ivar domains: See L{__init__}.
    @ivar domain: See L{__init__}.
    """

    def __init__(self, domains, domain):
        """
        @type domains: L{dict} mapping L{bytes} to L{IDomain} provider
        @param domains: A mapping of domain name to domain object

        @type domain: L{IAliasableDomain} provider
        @param domain: The domain to update.
        """
        self.domains = domains
        self.domain = domain

    def __call__(self, new):
        """
        Update the aliases for a domain from an aliases(5) file.

        @type new: L{bytes}
        @param new: The name of an aliases(5) file.
        """
        self.domain.setAliasGroup(alias.loadAliasFile(self.domains, new))


def makeService(config):
    """
    Configure a service for operating a mail server.

    The returned service may include POP3 servers, SMTP servers, or both,
    depending on the configuration passed in.  If there are multiple servers,
    they will share all of their non-network state (i.e. the same user accounts
    are available on all of them).

    @type config: L{Options <usage.Options>}
    @param config: Configuration options specifying which servers to include in
        the returned service and where they should keep mail data.

    @rtype: L{IService <twisted.application.service.IService>} provider
    @return: A service which contains the requested mail servers.
    """
    if config["esmtp"]:
        rmType = relaymanager.SmartHostESMTPRelayingManager
        smtpFactory = config.service.getESMTPFactory
    else:
        rmType = relaymanager.SmartHostSMTPRelayingManager
        smtpFactory = config.service.getSMTPFactory

    if config["relay"]:
        dir = config["relay"]
        if not os.path.isdir(dir):
            os.mkdir(dir)

        config.service.setQueue(relaymanager.Queue(dir))
        default = relay.DomainQueuer(config.service)

        manager = rmType(config.service.queue)
        if config["esmtp"]:
            manager.fArgs += (None, None)
        manager.fArgs += (config["hostname"],)

        helper = relaymanager.RelayStateHelper(manager, 1)
        helper.setServiceParent(config.service)
        config.service.domains.setDefaultDomain(default)

    if config["pop3"]:
        f = config.service.getPOP3Factory()
        for endpoint in config["pop3"]:
            svc = internet.StreamServerEndpointService(endpoint, f)
            svc.setServiceParent(config.service)

    if config["smtp"]:
        f = smtpFactory()
        if config["hostname"]:
            f.domain = config["hostname"]
            f.fArgs = (f.domain,)
        if config["esmtp"]:
            f.fArgs = (None, None) + f.fArgs
        for endpoint in config["smtp"]:
            svc = internet.StreamServerEndpointService(endpoint, f)
            svc.setServiceParent(config.service)

    return config.service
