# -*- test-case-name: twisted.names.test.test_srvconnect -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division

import random

from zope.interface import implementer

from twisted.internet import error, interfaces
from twisted.names import client, dns
from twisted.names.error import DNSNameError
from twisted.python.compat import nativeString, unicode


class _SRVConnector_ClientFactoryWrapper:
    def __init__(self, connector, wrappedFactory):
        self.__connector = connector
        self.__wrappedFactory = wrappedFactory

    def startedConnecting(self, connector):
        self.__wrappedFactory.startedConnecting(self.__connector)

    def clientConnectionFailed(self, connector, reason):
        self.__connector.connectionFailed(reason)

    def clientConnectionLost(self, connector, reason):
        self.__connector.connectionLost(reason)

    def __getattr__(self, key):
        return getattr(self.__wrappedFactory, key)



@implementer(interfaces.IConnector)
class SRVConnector:
    """
    A connector that looks up DNS SRV records.

    RFC 2782 details how SRV records should be interpreted and selected
    for subsequent connection attempts. The algorithm for using the records'
    priority and weight is implemented in L{pickServer}.

    @ivar servers: List of candidate server records for future connection
        attempts.
    @type servers: L{list} of L{dns.Record_SRV}

    @ivar orderedServers: List of server records that have already been tried
        in this round of connection attempts.
    @type orderedServers: L{list} of L{dns.Record_SRV}
    """

    stopAfterDNS=0

    def __init__(self, reactor, service, domain, factory,
                 protocol='tcp', connectFuncName='connectTCP',
                 connectFuncArgs=(),
                 connectFuncKwArgs={},
                 defaultPort=None,
                 ):
        """
        @param domain: The domain to connect to.  If passed as a unicode
            string, it will be encoded using C{idna} encoding.
        @type domain: L{bytes} or L{unicode}

        @param defaultPort: Optional default port number to be used when SRV
            lookup fails and the service name is unknown. This should be the
            port number associated with the service name as defined by the IANA
            registry.
        @type defaultPort: L{int}
        """
        self.reactor = reactor
        self.service = service
        if isinstance(domain, unicode):
            domain = domain.encode('idna')
        self.domain = nativeString(domain)
        self.factory = factory

        self.protocol = protocol
        self.connectFuncName = connectFuncName
        self.connectFuncArgs = connectFuncArgs
        self.connectFuncKwArgs = connectFuncKwArgs
        self._defaultPort = defaultPort

        self.connector = None
        self.servers = None
        self.orderedServers = None # list of servers already used in this round

    def connect(self):
        """Start connection to remote server."""
        self.factory.doStart()
        self.factory.startedConnecting(self)

        if not self.servers:
            if self.domain is None:
                self.connectionFailed(error.DNSLookupError("Domain is not defined."))
                return
            d = client.lookupService('_%s._%s.%s' %
                    (nativeString(self.service),
                     nativeString(self.protocol),
                     self.domain))
            d.addCallbacks(self._cbGotServers, self._ebGotServers)
            d.addCallback(lambda x, self=self: self._reallyConnect())
            if self._defaultPort:
                d.addErrback(self._ebServiceUnknown)
            d.addErrback(self.connectionFailed)
        elif self.connector is None:
            self._reallyConnect()
        else:
            self.connector.connect()

    def _ebGotServers(self, failure):
        failure.trap(DNSNameError)

        # Some DNS servers reply with NXDOMAIN when in fact there are
        # just no SRV records for that domain. Act as if we just got an
        # empty response and use fallback.

        self.servers = []
        self.orderedServers = []

    def _cbGotServers(self, result):
        answers, auth, add = result
        if len(answers) == 1 and answers[0].type == dns.SRV \
                             and answers[0].payload \
                             and answers[0].payload.target == dns.Name(b'.'):
            # decidedly not available
            raise error.DNSLookupError("Service %s not available for domain %s."
                                       % (repr(self.service), repr(self.domain)))

        self.servers = []
        self.orderedServers = []
        for a in answers:
            if a.type != dns.SRV or not a.payload:
                continue

            self.orderedServers.append(a.payload)

    def _ebServiceUnknown(self, failure):
        """
        Connect to the default port when the service name is unknown.

        If no SRV records were found, the service name will be passed as the
        port. If resolving the name fails with
        L{error.ServiceNameUnknownError}, a final attempt is done using the
        default port.
        """
        failure.trap(error.ServiceNameUnknownError)
        self.servers = [dns.Record_SRV(0, 0, self._defaultPort, self.domain)]
        self.orderedServers = []
        self.connect()

    def pickServer(self):
        """
        Pick the next server.

        This selects the next server from the list of SRV records according
        to their priority and weight values, as set out by the default
        algorithm specified in RFC 2782.

        At the beginning of a round, L{servers} is populated with
        L{orderedServers}, and the latter is made empty. L{servers}
        is the list of candidates, and L{orderedServers} is the list of servers
        that have already been tried.

        First, all records are ordered by priority and weight in ascending
        order. Then for each priority level, a running sum is calculated
        over the sorted list of records for that priority. Then a random value
        between 0 and the final sum is compared to each record in order. The
        first record that is greater than or equal to that random value is
        chosen and removed from the list of candidates for this round.

        @return: A tuple of target hostname and port from the chosen DNS SRV
            record.
        @rtype: L{tuple} of native L{str} and L{int}
        """
        assert self.servers is not None
        assert self.orderedServers is not None

        if not self.servers and not self.orderedServers:
            # no SRV record, fall back..
            return self.domain, self.service

        if not self.servers and self.orderedServers:
            # start new round
            self.servers = self.orderedServers
            self.orderedServers = []

        assert self.servers

        self.servers.sort(key=lambda record: (record.priority, record.weight))
        minPriority = self.servers[0].priority

        index = 0
        weightSum = 0
        weightIndex = []
        for x in self.servers:
            if x.priority == minPriority:
                weightSum += x.weight
                weightIndex.append((index, weightSum))
                index += 1

        rand = random.randint(0, weightSum)
        for index, weight in weightIndex:
            if weight >= rand:
                chosen = self.servers[index]
                del self.servers[index]
                self.orderedServers.append(chosen)

                return str(chosen.target), chosen.port

        raise RuntimeError(
            'Impossible %s pickServer result.' % (self.__class__.__name__,))

    def _reallyConnect(self):
        if self.stopAfterDNS:
            self.stopAfterDNS=0
            return

        self.host, self.port = self.pickServer()
        assert self.host is not None, 'Must have a host to connect to.'
        assert self.port is not None, 'Must have a port to connect to.'

        connectFunc = getattr(self.reactor, self.connectFuncName)
        self.connector=connectFunc(
            self.host, self.port,
            _SRVConnector_ClientFactoryWrapper(self, self.factory),
            *self.connectFuncArgs, **self.connectFuncKwArgs)

    def stopConnecting(self):
        """Stop attempting to connect."""
        if self.connector:
            self.connector.stopConnecting()
        else:
            self.stopAfterDNS=1

    def disconnect(self):
        """Disconnect whatever our are state is."""
        if self.connector is not None:
            self.connector.disconnect()
        else:
            self.stopConnecting()

    def getDestination(self):
        assert self.connector
        return self.connector.getDestination()

    def connectionFailed(self, reason):
        self.factory.clientConnectionFailed(self, reason)
        self.factory.doStop()

    def connectionLost(self, reason):
        self.factory.clientConnectionLost(self, reason)
        self.factory.doStop()
