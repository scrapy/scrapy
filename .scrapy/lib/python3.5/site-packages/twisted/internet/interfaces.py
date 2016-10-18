# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interface documentation.

Maintainer: Itamar Shtull-Trauring
"""

from __future__ import division, absolute_import

from zope.interface import Interface, Attribute


class IAddress(Interface):
    """
    An address, e.g. a TCP C{(host, port)}.

    Default implementations are in L{twisted.internet.address}.
    """

### Reactor Interfaces

class IConnector(Interface):
    """
    Object used to interface between connections and protocols.

    Each L{IConnector} manages one connection.
    """

    def stopConnecting():
        """
        Stop attempting to connect.
        """

    def disconnect():
        """
        Disconnect regardless of the connection state.

        If we are connected, disconnect, if we are trying to connect,
        stop trying.
        """

    def connect():
        """
        Try to connect to remote address.
        """

    def getDestination():
        """
        Return destination this will try to connect to.

        @return: An object which provides L{IAddress}.
        """



class IResolverSimple(Interface):
    def getHostByName(name, timeout = (1, 3, 11, 45)):
        """
        Resolve the domain name C{name} into an IP address.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{twisted.internet.defer.Deferred}
        @return: The callback of the Deferred that is returned will be
            passed a string that represents the IP address of the
            specified name, or the errback will be called if the
            lookup times out.  If multiple types of address records
            are associated with the name, A6 records will be returned
            in preference to AAAA records, which will be returned in
            preference to A records.  If there are multiple records of
            the type to be returned, one will be selected at random.

        @raise twisted.internet.defer.TimeoutError: Raised
            (asynchronously) if the name cannot be resolved within the
            specified timeout period.
        """



class IResolver(IResolverSimple):
    def query(query, timeout=None):
        """
        Dispatch C{query} to the method which can handle its type.

        @type query: L{twisted.names.dns.Query}
        @param query: The DNS query being issued, to which a response is to be
            generated.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupAddress(name, timeout=None):
        """
        Perform an A record lookup.

        @type name: L{bytes}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupAddress6(name, timeout=None):
        """
        Perform an A6 record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupIPV6Address(name, timeout=None):
        """
        Perform an AAAA record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupMailExchange(name, timeout=None):
        """
        Perform an MX record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupNameservers(name, timeout=None):
        """
        Perform an NS record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupCanonicalName(name, timeout=None):
        """
        Perform a CNAME record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupMailBox(name, timeout=None):
        """
        Perform an MB record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupMailGroup(name, timeout=None):
        """
        Perform an MG record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupMailRename(name, timeout=None):
        """
        Perform an MR record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupPointer(name, timeout=None):
        """
        Perform a PTR record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupAuthority(name, timeout=None):
        """
        Perform an SOA record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupNull(name, timeout=None):
        """
        Perform a NULL record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupWellKnownServices(name, timeout=None):
        """
        Perform a WKS record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupHostInfo(name, timeout=None):
        """
        Perform a HINFO record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupMailboxInfo(name, timeout=None):
        """
        Perform an MINFO record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupText(name, timeout=None):
        """
        Perform a TXT record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupResponsibility(name, timeout=None):
        """
        Perform an RP record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupAFSDatabase(name, timeout=None):
        """
        Perform an AFSDB record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupService(name, timeout=None):
        """
        Perform an SRV record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupAllRecords(name, timeout=None):
        """
        Perform an ALL_RECORD lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupSenderPolicy(name, timeout= 10):
        """
        Perform a SPF record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupNamingAuthorityPointer(name, timeout=None):
        """
        Perform a NAPTR record lookup.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: Sequence of C{int}
        @param timeout: Number of seconds after which to reissue the query.
            When the last timeout expires, the query is considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.  The first element of the
            tuple gives answers.  The second element of the tuple gives
            authorities.  The third element of the tuple gives additional
            information.  The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """


    def lookupZone(name, timeout=None):
        """
        Perform an AXFR record lookup.

        NB This is quite different from other DNS requests. See
        U{http://cr.yp.to/djbdns/axfr-notes.html} for more
        information.

        NB Unlike other C{lookup*} methods, the timeout here is not a
        list of ints, it is a single int.

        @type name: C{str}
        @param name: DNS name to resolve.

        @type timeout: C{int}
        @param timeout: When this timeout expires, the query is
            considered failed.

        @rtype: L{Deferred}
        @return: A L{Deferred} which fires with a three-tuple of lists of
            L{twisted.names.dns.RRHeader} instances.
            The first element of the tuple gives answers.
            The second and third elements are always empty.
            The L{Deferred} may instead fail with one of the
            exceptions defined in L{twisted.names.error} or with
            C{NotImplementedError}.
        """



class IReactorTCP(Interface):

    def listenTCP(port, factory, backlog=50, interface=''):
        """
        Connects a given protocol factory to the given numeric TCP/IP port.

        @param port: a port number on which to listen

        @param factory: a L{twisted.internet.protocol.ServerFactory} instance

        @param backlog: size of the listen queue

        @param interface: The local IPv4 or IPv6 address to which to bind;
            defaults to '', ie all IPv4 addresses.  To bind to all IPv4 and IPv6
            addresses, you must call this method twice.

        @return: an object that provides L{IListeningPort}.

        @raise CannotListenError: as defined here
                                  L{twisted.internet.error.CannotListenError},
                                  if it cannot listen on this port (e.g., it
                                  cannot bind to the required port number)
        """

    def connectTCP(host, port, factory, timeout=30, bindAddress=None):
        """
        Connect a TCP client.

        @param host: A hostname or an IPv4 or IPv6 address literal.

        @type host: L{bytes}

        @param port: a port number

        @param factory: a L{twisted.internet.protocol.ClientFactory} instance

        @param timeout: number of seconds to wait before assuming the
                        connection has failed.

        @param bindAddress: a (host, port) tuple of local address to bind
                            to, or None.

        @return: An object which provides L{IConnector}. This connector will
                 call various callbacks on the factory when a connection is
                 made, failed, or lost - see
                 L{ClientFactory<twisted.internet.protocol.ClientFactory>}
                 docs for details.
        """

class IReactorSSL(Interface):

    def connectSSL(host, port, factory, contextFactory, timeout=30, bindAddress=None):
        """
        Connect a client Protocol to a remote SSL socket.

        @param host: a host name

        @param port: a port number

        @param factory: a L{twisted.internet.protocol.ClientFactory} instance

        @param contextFactory: a L{twisted.internet.ssl.ClientContextFactory} object.

        @param timeout: number of seconds to wait before assuming the
                        connection has failed.

        @param bindAddress: a (host, port) tuple of local address to bind to,
                            or L{None}.

        @return: An object which provides L{IConnector}.
        """

    def listenSSL(port, factory, contextFactory, backlog=50, interface=''):
        """
        Connects a given protocol factory to the given numeric TCP/IP port.
        The connection is a SSL one, using contexts created by the context
        factory.

        @param port: a port number on which to listen

        @param factory: a L{twisted.internet.protocol.ServerFactory} instance

        @param contextFactory: an implementor of L{IOpenSSLContextFactory}

        @param backlog: size of the listen queue

        @param interface: the hostname to bind to, defaults to '' (all)
        """



class IReactorUNIX(Interface):
    """
    UNIX socket methods.
    """

    def connectUNIX(address, factory, timeout=30, checkPID=0):
        """
        Connect a client protocol to a UNIX socket.

        @param address: a path to a unix socket on the filesystem.

        @param factory: a L{twisted.internet.protocol.ClientFactory} instance

        @param timeout: number of seconds to wait before assuming the connection
            has failed.

        @param checkPID: if True, check for a pid file to verify that a server
            is listening.  If C{address} is a Linux abstract namespace path,
            this must be C{False}.

        @return: An object which provides L{IConnector}.
        """


    def listenUNIX(address, factory, backlog=50, mode=0o666, wantPID=0):
        """
        Listen on a UNIX socket.

        @param address: a path to a unix socket on the filesystem.

        @param factory: a L{twisted.internet.protocol.Factory} instance.

        @param backlog: number of connections to allow in backlog.

        @param mode: The mode (B{not} umask) to set on the unix socket.  See
            platform specific documentation for information about how this
            might affect connection attempts.
        @type mode: C{int}

        @param wantPID: if True, create a pidfile for the socket.  If C{address}
            is a Linux abstract namespace path, this must be C{False}.

        @return: An object which provides L{IListeningPort}.
        """



class IReactorUNIXDatagram(Interface):
    """
    Datagram UNIX socket methods.
    """

    def connectUNIXDatagram(address, protocol, maxPacketSize=8192, mode=0o666, bindAddress=None):
        """
        Connect a client protocol to a datagram UNIX socket.

        @param address: a path to a unix socket on the filesystem.

        @param protocol: a L{twisted.internet.protocol.ConnectedDatagramProtocol} instance

        @param maxPacketSize: maximum packet size to accept

        @param mode: The mode (B{not} umask) to set on the unix socket.  See
            platform specific documentation for information about how this
            might affect connection attempts.
        @type mode: C{int}

        @param bindAddress: address to bind to

        @return: An object which provides L{IConnector}.
        """


    def listenUNIXDatagram(address, protocol, maxPacketSize=8192, mode=0o666):
        """
        Listen on a datagram UNIX socket.

        @param address: a path to a unix socket on the filesystem.

        @param protocol: a L{twisted.internet.protocol.DatagramProtocol} instance.

        @param maxPacketSize: maximum packet size to accept

        @param mode: The mode (B{not} umask) to set on the unix socket.  See
            platform specific documentation for information about how this
            might affect connection attempts.
        @type mode: C{int}

        @return: An object which provides L{IListeningPort}.
        """



class IReactorWin32Events(Interface):
    """
    Win32 Event API methods

    @since: 10.2
    """

    def addEvent(event, fd, action):
        """
        Add a new win32 event to the event loop.

        @param event: a Win32 event object created using win32event.CreateEvent()

        @param fd: an instance of L{twisted.internet.abstract.FileDescriptor}

        @param action: a string that is a method name of the fd instance.
                       This method is called in response to the event.

        @return: None
        """


    def removeEvent(event):
        """
        Remove an event.

        @param event: a Win32 event object added using L{IReactorWin32Events.addEvent}

        @return: None
        """



class IReactorUDP(Interface):
    """
    UDP socket methods.
    """

    def listenUDP(port, protocol, interface='', maxPacketSize=8192):
        """
        Connects a given L{DatagramProtocol} to the given numeric UDP port.

        @param port: A port number on which to listen.
        @type port: C{int}

        @param protocol: A L{DatagramProtocol} instance which will be
            connected to the given C{port}.
        @type protocol: L{DatagramProtocol}

        @param interface: The local IPv4 or IPv6 address to which to bind;
            defaults to '', ie all IPv4 addresses.
        @type interface: C{str}

        @param maxPacketSize: The maximum packet size to accept.
        @type maxPacketSize: C{int}

        @return: object which provides L{IListeningPort}.
        """



class IReactorMulticast(Interface):
    """
    UDP socket methods that support multicast.

    IMPORTANT: This is an experimental new interface. It may change
    without backwards compatibility. Suggestions are welcome.
    """

    def listenMulticast(port, protocol, interface='', maxPacketSize=8192,
                        listenMultiple=False):
        """
        Connects a given
        L{DatagramProtocol<twisted.internet.protocol.DatagramProtocol>} to the
        given numeric UDP port.

        @param listenMultiple: If set to True, allows multiple sockets to
            bind to the same address and port number at the same time.
        @type listenMultiple: C{bool}

        @returns: An object which provides L{IListeningPort}.

        @see: L{twisted.internet.interfaces.IMulticastTransport}
        @see: U{http://twistedmatrix.com/documents/current/core/howto/udp.html}
        """



class IReactorSocket(Interface):
    """
    Methods which allow a reactor to use externally created sockets.

    For example, to use C{adoptStreamPort} to implement behavior equivalent
    to that of L{IReactorTCP.listenTCP}, you might write code like this::

        from socket import SOMAXCONN, AF_INET, SOCK_STREAM, socket
        portSocket = socket(AF_INET, SOCK_STREAM)
        # Set FD_CLOEXEC on port, left as an exercise.  Then make it into a
        # non-blocking listening port:
        portSocket.setblocking(False)
        portSocket.bind(('192.168.1.2', 12345))
        portSocket.listen(SOMAXCONN)

        # Now have the reactor use it as a TCP port
        port = reactor.adoptStreamPort(
            portSocket.fileno(), AF_INET, YourFactory())

        # portSocket itself is no longer necessary, and needs to be cleaned
        # up by us.
        portSocket.close()

        # Whenever the server is no longer needed, stop it as usual.
        stoppedDeferred = port.stopListening()

    Another potential use is to inherit a listening descriptor from a parent
    process (for example, systemd or launchd), or to receive one over a UNIX
    domain socket.

    Some plans for extending this interface exist.  See:

        - U{http://twistedmatrix.com/trac/ticket/5573}: AF_UNIX SOCK_STREAM ports
        - U{http://twistedmatrix.com/trac/ticket/6594}: AF_UNIX SOCK_DGRAM ports
    """

    def adoptStreamPort(fileDescriptor, addressFamily, factory):
        """
        Add an existing listening I{SOCK_STREAM} socket to the reactor to
        monitor for new connections to accept and handle.

        @param fileDescriptor: A file descriptor associated with a socket which
            is already bound to an address and marked as listening.  The socket
            must be set non-blocking.  Any additional flags (for example,
            close-on-exec) must also be set by application code.  Application
            code is responsible for closing the file descriptor, which may be
            done as soon as C{adoptStreamPort} returns.
        @type fileDescriptor: C{int}

        @param addressFamily: The address family (or I{domain}) of the socket.
            For example, L{socket.AF_INET6}.

        @param factory: A L{ServerFactory} instance to use to create new
            protocols to handle connections accepted via this socket.

        @return: An object providing L{IListeningPort}.

        @raise twisted.internet.error.UnsupportedAddressFamily: If the
            given address family is not supported by this reactor, or
            not supported with the given socket type.

        @raise twisted.internet.error.UnsupportedSocketType: If the
            given socket type is not supported by this reactor, or not
            supported with the given socket type.
        """


    def adoptStreamConnection(fileDescriptor, addressFamily, factory):
        """
        Add an existing connected I{SOCK_STREAM} socket to the reactor to
        monitor for data.

        Note that the given factory won't have its C{startFactory} and
        C{stopFactory} methods called, as there is no sensible time to call
        them in this situation.

        @param fileDescriptor: A file descriptor associated with a socket which
            is already connected.  The socket must be set non-blocking.  Any
            additional flags (for example, close-on-exec) must also be set by
            application code.  Application code is responsible for closing the
            file descriptor, which may be done as soon as
            C{adoptStreamConnection} returns.
        @type fileDescriptor: C{int}

        @param addressFamily: The address family (or I{domain}) of the socket.
            For example, L{socket.AF_INET6}.

        @param factory: A L{ServerFactory} instance to use to create a new
            protocol to handle the connection via this socket.

        @raise UnsupportedAddressFamily: If the given address family is not
            supported by this reactor, or not supported with the given socket
            type.

        @raise UnsupportedSocketType: If the given socket type is not supported
            by this reactor, or not supported with the given socket type.
        """


    def adoptDatagramPort(fileDescriptor, addressFamily, protocol,
                          maxPacketSize=8192):
        """
        Add an existing listening I{SOCK_DGRAM} socket to the reactor to
        monitor for read and write readiness.

        @param fileDescriptor: A file descriptor associated with a socket which
            is already bound to an address and marked as listening.  The socket
            must be set non-blocking.  Any additional flags (for example,
            close-on-exec) must also be set by application code.  Application
            code is responsible for closing the file descriptor, which may be
            done as soon as C{adoptDatagramPort} returns.
        @type fileDescriptor: C{int}

        @param addressFamily: The address family or I{domain} of the socket.
            For example, L{socket.AF_INET6}.
        @type addressFamily: C{int}

        @param protocol: A L{DatagramProtocol} instance to connect to
            a UDP transport.
        @type protocol: L{DatagramProtocol}

        @param maxPacketSize: The maximum packet size to accept.
        @type maxPacketSize: C{int}

        @return: An object providing L{IListeningPort}.

        @raise UnsupportedAddressFamily: If the given address family is not
            supported by this reactor, or not supported with the given socket
            type.

        @raise UnsupportedSocketType: If the given socket type is not supported
            by this reactor, or not supported with the given socket type.
        """



class IReactorProcess(Interface):

    def spawnProcess(processProtocol, executable, args=(), env={}, path=None,
                     uid=None, gid=None, usePTY=0, childFDs=None):
        """
        Spawn a process, with a process protocol.

        @type processProtocol: L{IProcessProtocol} provider
        @param processProtocol: An object which will be notified of all
            events related to the created process.

        @param executable: the file name to spawn - the full path should be
                           used.

        @param args: the command line arguments to pass to the process; a
                     sequence of strings. The first string should be the
                     executable's name.

        @type env: a C{dict} mapping C{str} to C{str}, or L{None}.
        @param env: the environment variables to pass to the child process. The
                    resulting behavior varies between platforms. If
                      - C{env} is not set:
                        - On POSIX: pass an empty environment.
                        - On Windows: pass C{os.environ}.
                      - C{env} is L{None}:
                        - On POSIX: pass C{os.environ}.
                        - On Windows: pass C{os.environ}.
                      - C{env} is a C{dict}:
                        - On POSIX: pass the key/value pairs in C{env} as the
                          complete environment.
                        - On Windows: update C{os.environ} with the key/value
                          pairs in the C{dict} before passing it. As a
                          consequence of U{bug #1640
                          <http://twistedmatrix.com/trac/ticket/1640>}, passing
                          keys with empty values in an effort to unset
                          environment variables I{won't} unset them.

        @param path: the path to run the subprocess in - defaults to the
                     current directory.

        @param uid: user ID to run the subprocess as. (Only available on
                    POSIX systems.)

        @param gid: group ID to run the subprocess as. (Only available on
                    POSIX systems.)

        @param usePTY: if true, run this process in a pseudo-terminal.
                       optionally a tuple of C{(masterfd, slavefd, ttyname)},
                       in which case use those file descriptors.
                       (Not available on all systems.)

        @param childFDs: A dictionary mapping file descriptors in the new child
                         process to an integer or to the string 'r' or 'w'.

                         If the value is an integer, it specifies a file
                         descriptor in the parent process which will be mapped
                         to a file descriptor (specified by the key) in the
                         child process.  This is useful for things like inetd
                         and shell-like file redirection.

                         If it is the string 'r', a pipe will be created and
                         attached to the child at that file descriptor: the
                         child will be able to write to that file descriptor
                         and the parent will receive read notification via the
                         L{IProcessProtocol.childDataReceived} callback.  This
                         is useful for the child's stdout and stderr.

                         If it is the string 'w', similar setup to the previous
                         case will occur, with the pipe being readable by the
                         child instead of writeable.  The parent process can
                         write to that file descriptor using
                         L{IProcessTransport.writeToChild}.  This is useful for
                         the child's stdin.

                         If childFDs is not passed, the default behaviour is to
                         use a mapping that opens the usual stdin/stdout/stderr
                         pipes.

        @see: L{twisted.internet.protocol.ProcessProtocol}

        @return: An object which provides L{IProcessTransport}.

        @raise OSError: Raised with errno C{EAGAIN} or C{ENOMEM} if there are
                        insufficient system resources to create a new process.
        """

class IReactorTime(Interface):
    """
    Time methods that a Reactor should implement.
    """

    def seconds():
        """
        Get the current time in seconds.

        @return: A number-like object of some sort.
        """


    def callLater(delay, callable, *args, **kw):
        """
        Call a function later.

        @type delay:  C{float}
        @param delay: the number of seconds to wait.

        @param callable: the callable object to call later.

        @param args: the arguments to call it with.

        @param kw: the keyword arguments to call it with.

        @return: An object which provides L{IDelayedCall} and can be used to
                 cancel the scheduled call, by calling its C{cancel()} method.
                 It also may be rescheduled by calling its C{delay()} or
                 C{reset()} methods.
        """


    def getDelayedCalls():
        """
        Retrieve all currently scheduled delayed calls.

        @return: A tuple of all L{IDelayedCall} providers representing all
                 currently scheduled calls. This is everything that has been
                 returned by C{callLater} but not yet called or canceled.
        """


class IDelayedCall(Interface):
    """
    A scheduled call.

    There are probably other useful methods we can add to this interface;
    suggestions are welcome.
    """

    def getTime():
        """
        Get time when delayed call will happen.

        @return: time in seconds since epoch (a float).
        """

    def cancel():
        """
        Cancel the scheduled call.

        @raises twisted.internet.error.AlreadyCalled: if the call has already
            happened.
        @raises twisted.internet.error.AlreadyCancelled: if the call has already
            been cancelled.
        """

    def delay(secondsLater):
        """
        Delay the scheduled call.

        @param secondsLater: how many seconds from its current firing time to delay

        @raises twisted.internet.error.AlreadyCalled: if the call has already
            happened.
        @raises twisted.internet.error.AlreadyCancelled: if the call has already
            been cancelled.
        """

    def reset(secondsFromNow):
        """
        Reset the scheduled call's timer.

        @param secondsFromNow: how many seconds from now it should fire,
            equivalent to C{.cancel()} and then doing another
            C{reactor.callLater(secondsLater, ...)}

        @raises twisted.internet.error.AlreadyCalled: if the call has already
            happened.
        @raises twisted.internet.error.AlreadyCancelled: if the call has already
            been cancelled.
        """

    def active():
        """
        @return: True if this call is still active, False if it has been
                 called or cancelled.
        """



class IReactorFromThreads(Interface):
    """
    This interface is the set of thread-safe methods which may be invoked on
    the reactor from other threads.

    @since: 15.4
    """

    def callFromThread(callable, *args, **kw):
        """
        Cause a function to be executed by the reactor thread.

        Use this method when you want to run a function in the reactor's thread
        from another thread.  Calling L{callFromThread} should wake up the main
        thread (where L{reactor.run() <IReactorCore.run>} is executing) and run
        the given callable in that thread.

        If you're writing a multi-threaded application the C{callable} may need
        to be thread safe, but this method doesn't require it as such.  If you
        want to call a function in the next mainloop iteration, but you're in
        the same thread, use L{callLater} with a delay of 0.
        """


class IReactorInThreads(Interface):
    """
    This interface contains the methods exposed by a reactor which will let you
    run functions in another thread.

    @since: 15.4
    """

    def callInThread(callable, *args, **kwargs):
        """
        Run the given callable object in a separate thread, with the given
        arguments and keyword arguments.
        """



class IReactorThreads(IReactorFromThreads, IReactorInThreads):
    """
    Dispatch methods to be run in threads.

    Internally, this should use a thread pool and dispatch methods to them.
    """

    def getThreadPool():
        """
        Return the threadpool used by L{IReactorInThreads.callInThread}.
        Create it first if necessary.

        @rtype: L{twisted.python.threadpool.ThreadPool}
        """


    def suggestThreadPoolSize(size):
        """
        Suggest the size of the internal threadpool used to dispatch functions
        passed to L{IReactorInThreads.callInThread}.
        """



class IReactorCore(Interface):
    """
    Core methods that a Reactor must implement.
    """

    running = Attribute(
        "A C{bool} which is C{True} from I{during startup} to "
        "I{during shutdown} and C{False} the rest of the time.")


    def resolve(name, timeout=10):
        """
        Return a L{twisted.internet.defer.Deferred} that will resolve a hostname.
        """

    def run():
        """
        Fire 'startup' System Events, move the reactor to the 'running'
        state, then run the main loop until it is stopped with C{stop()} or
        C{crash()}.
        """

    def stop():
        """
        Fire 'shutdown' System Events, which will move the reactor to the
        'stopped' state and cause C{reactor.run()} to exit.
        """

    def crash():
        """
        Stop the main loop *immediately*, without firing any system events.

        This is named as it is because this is an extremely "rude" thing to do;
        it is possible to lose data and put your system in an inconsistent
        state by calling this.  However, it is necessary, as sometimes a system
        can become wedged in a pre-shutdown call.
        """

    def iterate(delay=0):
        """
        Run the main loop's I/O polling function for a period of time.

        This is most useful in applications where the UI is being drawn "as
        fast as possible", such as games. All pending L{IDelayedCall}s will
        be called.

        The reactor must have been started (via the C{run()} method) prior to
        any invocations of this method.  It must also be stopped manually
        after the last call to this method (via the C{stop()} method).  This
        method is not re-entrant: you must not call it recursively; in
        particular, you must not call it while the reactor is running.
        """

    def fireSystemEvent(eventType):
        """
        Fire a system-wide event.

        System-wide events are things like 'startup', 'shutdown', and
        'persist'.
        """

    def addSystemEventTrigger(phase, eventType, callable, *args, **kw):
        """
        Add a function to be called when a system event occurs.

        Each "system event" in Twisted, such as 'startup', 'shutdown', and
        'persist', has 3 phases: 'before', 'during', and 'after' (in that
        order, of course).  These events will be fired internally by the
        Reactor.

        An implementor of this interface must only implement those events
        described here.

        Callbacks registered for the "before" phase may return either None or a
        Deferred.  The "during" phase will not execute until all of the
        Deferreds from the "before" phase have fired.

        Once the "during" phase is running, all of the remaining triggers must
        execute; their return values must be ignored.

        @param phase: a time to call the event -- either the string 'before',
                      'after', or 'during', describing when to call it
                      relative to the event's execution.

        @param eventType: this is a string describing the type of event.

        @param callable: the object to call before shutdown.

        @param args: the arguments to call it with.

        @param kw: the keyword arguments to call it with.

        @return: an ID that can be used to remove this call with
                 removeSystemEventTrigger.
        """

    def removeSystemEventTrigger(triggerID):
        """
        Removes a trigger added with addSystemEventTrigger.

        @param triggerID: a value returned from addSystemEventTrigger.

        @raise KeyError: If there is no system event trigger for the given
            C{triggerID}.

        @raise ValueError: If there is no system event trigger for the given
            C{triggerID}.

        @raise TypeError: If there is no system event trigger for the given
            C{triggerID}.
        """

    def callWhenRunning(callable, *args, **kw):
        """
        Call a function when the reactor is running.

        If the reactor has not started, the callable will be scheduled
        to run when it does start. Otherwise, the callable will be invoked
        immediately.

        @param callable: the callable object to call later.

        @param args: the arguments to call it with.

        @param kw: the keyword arguments to call it with.

        @return: None if the callable was invoked, otherwise a system
                 event id for the scheduled call.
        """


class IReactorPluggableResolver(Interface):
    """
    A reactor with a pluggable name resolver interface.
    """

    def installResolver(resolver):
        """
        Set the internal resolver to use to for name lookups.

        @type resolver: An object implementing the L{IResolverSimple} interface
        @param resolver: The new resolver to use.

        @return: The previously installed resolver.
        """


class IReactorDaemonize(Interface):
    """
    A reactor which provides hooks that need to be called before and after
    daemonization.

    Notes:
       - This interface SHOULD NOT be called by applications.
       - This interface should only be implemented by reactors as a workaround
         (in particular, it's implemented currently only by kqueue()).
         For details please see the comments on ticket #1918.
    """

    def beforeDaemonize():
        """
        Hook to be called immediately before daemonization. No reactor methods
        may be called until L{afterDaemonize} is called.

        @return: L{None}.
        """


    def afterDaemonize():
        """
        Hook to be called immediately after daemonization. This may only be
        called after L{beforeDaemonize} had been called previously.

        @return: L{None}.
        """



class IReactorFDSet(Interface):
    """
    Implement me to be able to use L{IFileDescriptor} type resources.

    This assumes that your main-loop uses UNIX-style numeric file descriptors
    (or at least similarly opaque IDs returned from a .fileno() method)
    """

    def addReader(reader):
        """
        I add reader to the set of file descriptors to get read events for.

        @param reader: An L{IReadDescriptor} provider that will be checked for
                       read events until it is removed from the reactor with
                       L{removeReader}.

        @return: L{None}.
        """

    def addWriter(writer):
        """
        I add writer to the set of file descriptors to get write events for.

        @param writer: An L{IWriteDescriptor} provider that will be checked for
                       write events until it is removed from the reactor with
                       L{removeWriter}.

        @return: L{None}.
        """

    def removeReader(reader):
        """
        Removes an object previously added with L{addReader}.

        @return: L{None}.
        """

    def removeWriter(writer):
        """
        Removes an object previously added with L{addWriter}.

        @return: L{None}.
        """

    def removeAll():
        """
        Remove all readers and writers.

        Should not remove reactor internal reactor connections (like a waker).

        @return: A list of L{IReadDescriptor} and L{IWriteDescriptor} providers
                 which were removed.
        """

    def getReaders():
        """
        Return the list of file descriptors currently monitored for input
        events by the reactor.

        @return: the list of file descriptors monitored for input events.
        @rtype: C{list} of C{IReadDescriptor}
        """

    def getWriters():
        """
        Return the list file descriptors currently monitored for output events
        by the reactor.

        @return: the list of file descriptors monitored for output events.
        @rtype: C{list} of C{IWriteDescriptor}
        """


class IListeningPort(Interface):
    """
    A listening port.
    """

    def startListening():
        """
        Start listening on this port.

        @raise CannotListenError: If it cannot listen on this port (e.g., it is
                                  a TCP port and it cannot bind to the required
                                  port number).
        """

    def stopListening():
        """
        Stop listening on this port.

        If it does not complete immediately, will return Deferred that fires
        upon completion.
        """

    def getHost():
        """
        Get the host that this port is listening for.

        @return: An L{IAddress} provider.
        """


class ILoggingContext(Interface):
    """
    Give context information that will be used to log events generated by
    this item.
    """

    def logPrefix():
        """
        @return: Prefix used during log formatting to indicate context.
        @rtype: C{str}
        """



class IFileDescriptor(ILoggingContext):
    """
    An interface representing a UNIX-style numeric file descriptor.
    """

    def fileno():
        """
        @raise: If the descriptor no longer has a valid file descriptor
            number associated with it.

        @return: The platform-specified representation of a file descriptor
            number.  Or C{-1} if the descriptor no longer has a valid file
            descriptor number associated with it.  As long as the descriptor
            is valid, calls to this method on a particular instance must
            return the same value.
        """


    def connectionLost(reason):
        """
        Called when the connection was lost.

        This is called when the connection on a selectable object has been
        lost.  It will be called whether the connection was closed explicitly,
        an exception occurred in an event handler, or the other end of the
        connection closed it first.

        See also L{IHalfCloseableDescriptor} if your descriptor wants to be
        notified separately of the two halves of the connection being closed.

        @param reason: A failure instance indicating the reason why the
                       connection was lost.  L{error.ConnectionLost} and
                       L{error.ConnectionDone} are of special note, but the
                       failure may be of other classes as well.
        """



class IReadDescriptor(IFileDescriptor):
    """
    An L{IFileDescriptor} that can read.

    This interface is generally used in conjunction with L{IReactorFDSet}.
    """

    def doRead():
        """
        Some data is available for reading on your descriptor.

        @return: If an error is encountered which causes the descriptor to
            no longer be valid, a L{Failure} should be returned.  Otherwise,
            L{None}.
        """


class IWriteDescriptor(IFileDescriptor):
    """
    An L{IFileDescriptor} that can write.

    This interface is generally used in conjunction with L{IReactorFDSet}.
    """

    def doWrite():
        """
        Some data can be written to your descriptor.

        @return: If an error is encountered which causes the descriptor to
            no longer be valid, a L{Failure} should be returned.  Otherwise,
            L{None}.
        """


class IReadWriteDescriptor(IReadDescriptor, IWriteDescriptor):
    """
    An L{IFileDescriptor} that can both read and write.
    """


class IHalfCloseableDescriptor(Interface):
    """
    A descriptor that can be half-closed.
    """

    def writeConnectionLost(reason):
        """
        Indicates write connection was lost.
        """

    def readConnectionLost(reason):
        """
        Indicates read connection was lost.
        """


class ISystemHandle(Interface):
    """
    An object that wraps a networking OS-specific handle.
    """

    def getHandle():
        """
        Return a system- and reactor-specific handle.

        This might be a socket.socket() object, or some other type of
        object, depending on which reactor is being used. Use and
        manipulate at your own risk.

        This might be used in cases where you want to set specific
        options not exposed by the Twisted APIs.
        """


class IConsumer(Interface):
    """
    A consumer consumes data from a producer.
    """

    def registerProducer(producer, streaming):
        """
        Register to receive data from a producer.

        This sets self to be a consumer for a producer.  When this object runs
        out of data (as when a send(2) call on a socket succeeds in moving the
        last data from a userspace buffer into a kernelspace buffer), it will
        ask the producer to resumeProducing().

        For L{IPullProducer} providers, C{resumeProducing} will be called once
        each time data is required.

        For L{IPushProducer} providers, C{pauseProducing} will be called
        whenever the write buffer fills up and C{resumeProducing} will only be
        called when it empties.

        @type producer: L{IProducer} provider

        @type streaming: C{bool}
        @param streaming: C{True} if C{producer} provides L{IPushProducer},
        C{False} if C{producer} provides L{IPullProducer}.

        @raise RuntimeError: If a producer is already registered.

        @return: L{None}
        """


    def unregisterProducer():
        """
        Stop consuming data from a producer, without disconnecting.
        """


    def write(data):
        """
        The producer will write data by calling this method.

        The implementation must be non-blocking and perform whatever
        buffering is necessary.  If the producer has provided enough data
        for now and it is a L{IPushProducer}, the consumer may call its
        C{pauseProducing} method.
        """



class IProducer(Interface):
    """
    A producer produces data for a consumer.

    Typically producing is done by calling the write method of a class
    implementing L{IConsumer}.
    """

    def stopProducing():
        """
        Stop producing data.

        This tells a producer that its consumer has died, so it must stop
        producing data for good.
        """


class IPushProducer(IProducer):
    """
    A push producer, also known as a streaming producer is expected to
    produce (write to this consumer) data on a continuous basis, unless
    it has been paused. A paused push producer will resume producing
    after its resumeProducing() method is called.   For a push producer
    which is not pauseable, these functions may be noops.
    """

    def pauseProducing():
        """
        Pause producing data.

        Tells a producer that it has produced too much data to process for
        the time being, and to stop until resumeProducing() is called.
        """
    def resumeProducing():
        """
        Resume producing data.

        This tells a producer to re-add itself to the main loop and produce
        more data for its consumer.
        """

class IPullProducer(IProducer):
    """
    A pull producer, also known as a non-streaming producer, is
    expected to produce data each time resumeProducing() is called.
    """

    def resumeProducing():
        """
        Produce data for the consumer a single time.

        This tells a producer to produce data for the consumer once
        (not repeatedly, once only). Typically this will be done
        by calling the consumer's write() method a single time with
        produced data.
        """

class IProtocol(Interface):

    def dataReceived(data):
        """
        Called whenever data is received.

        Use this method to translate to a higher-level message.  Usually, some
        callback will be made upon the receipt of each complete protocol
        message.

        @param data: a string of indeterminate length.  Please keep in mind
            that you will probably need to buffer some data, as partial
            (or multiple) protocol messages may be received!  I recommend
            that unit tests for protocols call through to this method with
            differing chunk sizes, down to one byte at a time.
        """

    def connectionLost(reason):
        """
        Called when the connection is shut down.

        Clear any circular references here, and any external references
        to this Protocol.  The connection has been closed. The C{reason}
        Failure wraps a L{twisted.internet.error.ConnectionDone} or
        L{twisted.internet.error.ConnectionLost} instance (or a subclass
        of one of those).

        @type reason: L{twisted.python.failure.Failure}
        """

    def makeConnection(transport):
        """
        Make a connection to a transport and a server.
        """

    def connectionMade():
        """
        Called when a connection is made.

        This may be considered the initializer of the protocol, because
        it is called when the connection is completed.  For clients,
        this is called once the connection to the server has been
        established; for servers, this is called after an accept() call
        stops blocking and a socket has been received.  If you need to
        send any greeting or initial message, do it here.
        """


class IProcessProtocol(Interface):
    """
    Interface for process-related event handlers.
    """

    def makeConnection(process):
        """
        Called when the process has been created.

        @type process: L{IProcessTransport} provider
        @param process: An object representing the process which has been
            created and associated with this protocol.
        """


    def childDataReceived(childFD, data):
        """
        Called when data arrives from the child process.

        @type childFD: C{int}
        @param childFD: The file descriptor from which the data was
            received.

        @type data: C{str}
        @param data: The data read from the child's file descriptor.
        """


    def childConnectionLost(childFD):
        """
        Called when a file descriptor associated with the child process is
        closed.

        @type childFD: C{int}
        @param childFD: The file descriptor which was closed.
        """


    def processExited(reason):
        """
        Called when the child process exits.

        @type reason: L{twisted.python.failure.Failure}
        @param reason: A failure giving the reason the child process
            terminated.  The type of exception for this failure is either
            L{twisted.internet.error.ProcessDone} or
            L{twisted.internet.error.ProcessTerminated}.

        @since: 8.2
        """


    def processEnded(reason):
        """
        Called when the child process exits and all file descriptors associated
        with it have been closed.

        @type reason: L{twisted.python.failure.Failure}
        @param reason: A failure giving the reason the child process
            terminated.  The type of exception for this failure is either
            L{twisted.internet.error.ProcessDone} or
            L{twisted.internet.error.ProcessTerminated}.
        """



class IHalfCloseableProtocol(Interface):
    """
    Implemented to indicate they want notification of half-closes.

    TCP supports the notion of half-closing the connection, e.g.
    closing the write side but still not stopping reading. A protocol
    that implements this interface will be notified of such events,
    instead of having connectionLost called.
    """

    def readConnectionLost():
        """
        Notification of the read connection being closed.

        This indicates peer did half-close of write side. It is now
        the responsibility of the this protocol to call
        loseConnection().  In addition, the protocol MUST make sure a
        reference to it still exists (i.e. by doing a callLater with
        one of its methods, etc.)  as the reactor will only have a
        reference to it if it is writing.

        If the protocol does not do so, it might get garbage collected
        without the connectionLost method ever being called.
        """

    def writeConnectionLost():
        """
        Notification of the write connection being closed.

        This will never be called for TCP connections as TCP does not
        support notification of this type of half-close.
        """



class IHandshakeListener(Interface):
    """
    An interface implemented by a L{IProtocol} to indicate that it would like
    to be notified when TLS handshakes complete when run over a TLS-based
    transport.

    This interface is only guaranteed to be called when run over a TLS-based
    transport: non TLS-based transports will not respect this interface.
    """

    def handshakeCompleted():
        """
        Notification of the TLS handshake being completed.

        This notification fires when OpenSSL has completed the TLS handshake.
        At this point the TLS connection is established, and the protocol can
        interrogate its transport (usually an L{ISSLTransport}) for details of
        the TLS connection.

        This notification *also* fires whenever the TLS session is
        renegotiated. As a result, protocols that have certain minimum security
        requirements should implement this interface to ensure that they are
        able to re-evaluate the security of the TLS session if it changes.
        """



class IFileDescriptorReceiver(Interface):
    """
    Protocols may implement L{IFileDescriptorReceiver} to receive file
    descriptors sent to them.  This is useful in conjunction with
    L{IUNIXTransport}, which allows file descriptors to be sent between
    processes on a single host.
    """
    def fileDescriptorReceived(descriptor):
        """
        Called when a file descriptor is received over the connection.

        @param descriptor: The descriptor which was received.
        @type descriptor: C{int}

        @return: L{None}
        """



class IProtocolFactory(Interface):
    """
    Interface for protocol factories.
    """

    def buildProtocol(addr):
        """
        Called when a connection has been established to addr.

        If None is returned, the connection is assumed to have been refused,
        and the Port will close the connection.

        @type addr: (host, port)
        @param addr: The address of the newly-established connection

        @return: None if the connection was refused, otherwise an object
                 providing L{IProtocol}.
        """

    def doStart():
        """
        Called every time this is connected to a Port or Connector.
        """

    def doStop():
        """
        Called every time this is unconnected from a Port or Connector.
        """


class ITransport(Interface):
    """
    I am a transport for bytes.

    I represent (and wrap) the physical connection and synchronicity
    of the framework which is talking to the network.  I make no
    representations about whether calls to me will happen immediately
    or require returning to a control loop, or whether they will happen
    in the same or another thread.  Consider methods of this class
    (aside from getPeer) to be 'thrown over the wall', to happen at some
    indeterminate time.
    """

    def write(data):
        """
        Write some data to the physical connection, in sequence, in a
        non-blocking fashion.

        If possible, make sure that it is all written.  No data will
        ever be lost, although (obviously) the connection may be closed
        before it all gets through.

        @type data: L{bytes}
        @param data: The data to write.
        """

    def writeSequence(data):
        """
        Write an iterable of byte strings to the physical connection.

        If possible, make sure that all of the data is written to
        the socket at once, without first copying it all into a
        single byte string.

        @type data: an iterable of L{bytes}
        @param data: The data to write.
        """

    def loseConnection():
        """
        Close my connection, after writing all pending data.

        Note that if there is a registered producer on a transport it
        will not be closed until the producer has been unregistered.
        """

    def getPeer():
        """
        Get the remote address of this connection.

        Treat this method with caution.  It is the unfortunate result of the
        CGI and Jabber standards, but should not be considered reliable for
        the usual host of reasons; port forwarding, proxying, firewalls, IP
        masquerading, etc.

        @return: An L{IAddress} provider.
        """

    def getHost():
        """
        Similar to getPeer, but returns an address describing this side of the
        connection.

        @return: An L{IAddress} provider.
        """


class ITCPTransport(ITransport):
    """
    A TCP based transport.
    """

    def loseWriteConnection():
        """
        Half-close the write side of a TCP connection.

        If the protocol instance this is attached to provides
        IHalfCloseableProtocol, it will get notified when the operation is
        done. When closing write connection, as with loseConnection this will
        only happen when buffer has emptied and there is no registered
        producer.
        """


    def abortConnection():
        """
        Close the connection abruptly.

        Discards any buffered data, stops any registered producer,
        and, if possible, notifies the other end of the unclean
        closure.

        @since: 11.1
        """


    def getTcpNoDelay():
        """
        Return if C{TCP_NODELAY} is enabled.
        """

    def setTcpNoDelay(enabled):
        """
        Enable/disable C{TCP_NODELAY}.

        Enabling C{TCP_NODELAY} turns off Nagle's algorithm. Small packets are
        sent sooner, possibly at the expense of overall throughput.
        """

    def getTcpKeepAlive():
        """
        Return if C{SO_KEEPALIVE} is enabled.
        """

    def setTcpKeepAlive(enabled):
        """
        Enable/disable C{SO_KEEPALIVE}.

        Enabling C{SO_KEEPALIVE} sends packets periodically when the connection
        is otherwise idle, usually once every two hours. They are intended
        to allow detection of lost peers in a non-infinite amount of time.
        """

    def getHost():
        """
        Returns L{IPv4Address} or L{IPv6Address}.
        """

    def getPeer():
        """
        Returns L{IPv4Address} or L{IPv6Address}.
        """



class IUNIXTransport(ITransport):
    """
    Transport for stream-oriented unix domain connections.
    """
    def sendFileDescriptor(descriptor):
        """
        Send a duplicate of this (file, socket, pipe, etc) descriptor to the
        other end of this connection.

        The send is non-blocking and will be queued if it cannot be performed
        immediately.  The send will be processed in order with respect to other
        C{sendFileDescriptor} calls on this transport, but not necessarily with
        respect to C{write} calls on this transport.  The send can only be
        processed if there are also bytes in the normal connection-oriented send
        buffer (ie, you must call C{write} at least as many times as you call
        C{sendFileDescriptor}).

        @param descriptor: An C{int} giving a valid file descriptor in this
            process.  Note that a I{file descriptor} may actually refer to a
            socket, a pipe, or anything else POSIX tries to treat in the same
            way as a file.

        @return: L{None}
        """



class IOpenSSLServerConnectionCreator(Interface):
    """
    A provider of L{IOpenSSLServerConnectionCreator} can create
    L{OpenSSL.SSL.Connection} objects for TLS servers.

    @see: L{twisted.internet.ssl}

    @note: Creating OpenSSL connection objects is subtle, error-prone, and
        security-critical.  Before implementing this interface yourself,
        consider using L{twisted.internet.ssl.CertificateOptions} as your
        C{contextFactory}.  (For historical reasons, that class does not
        actually I{implement} this interface; nevertheless it is usable in all
        Twisted APIs which require a provider of this interface.)
    """

    def serverConnectionForTLS(tlsProtocol):
        """
        Create a connection for the given server protocol.

        @param tlsProtocol: the protocol server making the request.
        @type tlsProtocol: L{twisted.protocols.tls.TLSMemoryBIOProtocol}.

        @return: an OpenSSL connection object configured appropriately for the
            given Twisted protocol.
        @rtype: L{OpenSSL.SSL.Connection}
        """



class IOpenSSLClientConnectionCreator(Interface):
    """
    A provider of L{IOpenSSLClientConnectionCreator} can create
    L{OpenSSL.SSL.Connection} objects for TLS clients.

    @see: L{twisted.internet.ssl}

    @note: Creating OpenSSL connection objects is subtle, error-prone, and
        security-critical.  Before implementing this interface yourself,
        consider using L{twisted.internet.ssl.optionsForClientTLS} as your
        C{contextFactory}.
    """

    def clientConnectionForTLS(tlsProtocol):
        """
        Create a connection for the given client protocol.

        @param tlsProtocol: the client protocol making the request.
        @type tlsProtocol: L{twisted.protocols.tls.TLSMemoryBIOProtocol}.

        @return: an OpenSSL connection object configured appropriately for the
            given Twisted protocol.
        @rtype: L{OpenSSL.SSL.Connection}
        """



class IProtocolNegotiationFactory(Interface):
    """
    A provider of L{IProtocolNegotiationFactory} can provide information about
    the various protocols that the factory can create implementations of. This
    can be used, for example, to provide protocol names for Next Protocol
    Negotiation and Application Layer Protocol Negotiation.

    @see: L{twisted.internet.ssl}
    """

    def acceptableProtocols():
        """
        Returns a list of protocols that can be spoken by the connection
        factory in the form of ALPN tokens, as laid out in the IANA registry
        for ALPN tokens.

        @return: a list of ALPN tokens in order of preference.
        @rtype: L{list} of L{bytes}
        """



class IOpenSSLContextFactory(Interface):
    """
    A provider of L{IOpenSSLContextFactory} is capable of generating
    L{OpenSSL.SSL.Context} classes suitable for configuring TLS on a
    connection. A provider will store enough state to be able to generate these
    contexts as needed for individual connections.

    @see: L{twisted.internet.ssl}
    """

    def getContext():
        """
        Returns a TLS context object, suitable for securing a TLS connection.
        This context object will be appropriately customized for the connection
        based on the state in this object.

        @return: A TLS context object.
        @rtype: L{OpenSSL.SSL.Context}
        """



class ITLSTransport(ITCPTransport):
    """
    A TCP transport that supports switching to TLS midstream.

    Once TLS mode is started the transport will implement L{ISSLTransport}.
    """

    def startTLS(contextFactory):
        """
        Initiate TLS negotiation.

        @param contextFactory: An object which creates appropriately configured
            TLS connections.

            For clients, use L{twisted.internet.ssl.optionsForClientTLS}; for
            servers, use L{twisted.internet.ssl.CertificateOptions}.

        @type contextFactory: L{IOpenSSLClientConnectionCreator} or
            L{IOpenSSLServerConnectionCreator}, depending on whether this
            L{ITLSTransport} is a server or not.  If the appropriate interface
            is not provided by the value given for C{contextFactory}, it must
            be an implementor of L{IOpenSSLContextFactory}.
        """



class ISSLTransport(ITCPTransport):
    """
    A SSL/TLS based transport.
    """

    def getPeerCertificate():
        """
        Return an object with the peer's certificate info.
        """



class INegotiated(ISSLTransport):
    """
    A TLS based transport that supports using ALPN/NPN to negotiate the
    protocol to be used inside the encrypted tunnel.
    """
    negotiatedProtocol = Attribute(
        """
        The protocol selected to be spoken using ALPN/NPN. The result from ALPN
        is preferred to the result from NPN if both were used. If the remote
        peer does not support ALPN or NPN, or neither NPN or ALPN are available
        on this machine, will be L{None}. Otherwise, will be the name of the
        selected protocol as C{bytes}. Note that until the handshake has
        completed this property may incorrectly return L{None}: wait until data
        has been received before trusting it (see
        https://twistedmatrix.com/trac/ticket/6024).
        """
    )



class ICipher(Interface):
    """
    A TLS cipher.
    """
    fullName = Attribute(
        "The fully qualified name of the cipher in L{unicode}."
    )



class IAcceptableCiphers(Interface):
    """
    A list of acceptable ciphers for a TLS context.
    """
    def selectCiphers(availableCiphers):
        """
        Choose which ciphers to allow to be negotiated on a TLS connection.

        @param availableCiphers: A L{list} of L{ICipher} which gives the names
            of all ciphers supported by the TLS implementation in use.

        @return: A L{list} of L{ICipher} which represents the ciphers
            which may be negotiated on the TLS connection.  The result is
            ordered by preference with more preferred ciphers appearing
            earlier.
        """



class IProcessTransport(ITransport):
    """
    A process transport.
    """

    pid = Attribute(
        "From before L{IProcessProtocol.makeConnection} is called to before "
        "L{IProcessProtocol.processEnded} is called, C{pid} is an L{int} "
        "giving the platform process ID of this process.  C{pid} is L{None} "
        "at all other times.")

    def closeStdin():
        """
        Close stdin after all data has been written out.
        """

    def closeStdout():
        """
        Close stdout.
        """

    def closeStderr():
        """
        Close stderr.
        """

    def closeChildFD(descriptor):
        """
        Close a file descriptor which is connected to the child process, identified
        by its FD in the child process.
        """

    def writeToChild(childFD, data):
        """
        Similar to L{ITransport.write} but also allows the file descriptor in
        the child process which will receive the bytes to be specified.

        @type childFD: C{int}
        @param childFD: The file descriptor to which to write.

        @type data: C{str}
        @param data: The bytes to write.

        @return: L{None}

        @raise KeyError: If C{childFD} is not a file descriptor that was mapped
            in the child when L{IReactorProcess.spawnProcess} was used to create
            it.
        """

    def loseConnection():
        """
        Close stdin, stderr and stdout.
        """

    def signalProcess(signalID):
        """
        Send a signal to the process.

        @param signalID: can be
          - one of C{"KILL"}, C{"TERM"}, or C{"INT"}.
              These will be implemented in a
              cross-platform manner, and so should be used
              if possible.
          - an integer, where it represents a POSIX
              signal ID.

        @raise twisted.internet.error.ProcessExitedAlready: If the process has
            already exited.
        @raise OSError: If the C{os.kill} call fails with an errno different
            from C{ESRCH}.
        """


class IServiceCollection(Interface):
    """
    An object which provides access to a collection of services.
    """

    def getServiceNamed(serviceName):
        """
        Retrieve the named service from this application.

        Raise a C{KeyError} if there is no such service name.
        """

    def addService(service):
        """
        Add a service to this collection.
        """

    def removeService(service):
        """
        Remove a service from this collection.
        """


class IUDPTransport(Interface):
    """
    Transport for UDP DatagramProtocols.
    """

    def write(packet, addr=None):
        """
        Write packet to given address.

        @param addr: a tuple of (ip, port). For connected transports must
                     be the address the transport is connected to, or None.
                     In non-connected mode this is mandatory.

        @raise twisted.internet.error.MessageLengthError: C{packet} was too
        long.
        """

    def connect(host, port):
        """
        Connect the transport to an address.

        This changes it to connected mode. Datagrams can only be sent to
        this address, and will only be received from this address. In addition
        the protocol's connectionRefused method might get called if destination
        is not receiving datagrams.

        @param host: an IP address, not a domain name ('127.0.0.1', not 'localhost')
        @param port: port to connect to.
        """

    def getHost():
        """
        Get this port's host address.

        @return: an address describing the listening port.
        @rtype: L{IPv4Address} or L{IPv6Address}.
        """

    def stopListening():
        """
        Stop listening on this port.

        If it does not complete immediately, will return L{Deferred} that fires
        upon completion.
        """

    def setBroadcastAllowed(enabled):
        """
        Set whether this port may broadcast.

        @param enabled: Whether the port may broadcast.
        @type enabled: L{bool}
        """

    def getBroadcastAllowed():
        """
        Checks if broadcast is currently allowed on this port.

        @return: Whether this port may broadcast.
        @rtype: L{bool}
        """


class IUNIXDatagramTransport(Interface):
    """
    Transport for UDP PacketProtocols.
    """

    def write(packet, address):
        """
        Write packet to given address.
        """

    def getHost():
        """
        Returns L{UNIXAddress}.
        """


class IUNIXDatagramConnectedTransport(Interface):
    """
    Transport for UDP ConnectedPacketProtocols.
    """

    def write(packet):
        """
        Write packet to address we are connected to.
        """

    def getHost():
        """
        Returns L{UNIXAddress}.
        """

    def getPeer():
        """
        Returns L{UNIXAddress}.
        """


class IMulticastTransport(Interface):
    """
    Additional functionality for multicast UDP.
    """

    def getOutgoingInterface():
        """
        Return interface of outgoing multicast packets.
        """

    def setOutgoingInterface(addr):
        """
        Set interface for outgoing multicast packets.

        Returns Deferred of success.
        """

    def getLoopbackMode():
        """
        Return if loopback mode is enabled.
        """

    def setLoopbackMode(mode):
        """
        Set if loopback mode is enabled.
        """

    def getTTL():
        """
        Get time to live for multicast packets.
        """

    def setTTL(ttl):
        """
        Set time to live on multicast packets.
        """

    def joinGroup(addr, interface=""):
        """
        Join a multicast group. Returns L{Deferred} of success or failure.

        If an error occurs, the returned L{Deferred} will fail with
        L{error.MulticastJoinError}.
        """

    def leaveGroup(addr, interface=""):
        """
        Leave multicast group, return L{Deferred} of success.
        """


class IStreamClientEndpoint(Interface):
    """
    A stream client endpoint is a place that L{ClientFactory} can connect to.
    For example, a remote TCP host/port pair would be a TCP client endpoint.

    @since: 10.1
    """

    def connect(protocolFactory):
        """
        Connect the C{protocolFactory} to the location specified by this
        L{IStreamClientEndpoint} provider.

        @param protocolFactory: A provider of L{IProtocolFactory}
        @return: A L{Deferred} that results in an L{IProtocol} upon successful
            connection otherwise a L{Failure} wrapping L{ConnectError} or
            L{NoProtocol <twisted.internet.error.NoProtocol>}.
        """



class IStreamServerEndpoint(Interface):
    """
    A stream server endpoint is a place that a L{Factory} can listen for
    incoming connections.

    @since: 10.1
    """

    def listen(protocolFactory):
        """
        Listen with C{protocolFactory} at the location specified by this
        L{IStreamServerEndpoint} provider.

        @param protocolFactory: A provider of L{IProtocolFactory}
        @return: A L{Deferred} that results in an L{IListeningPort} or an
            L{CannotListenError}
        """



class IStreamServerEndpointStringParser(Interface):
    """
    An L{IStreamServerEndpointStringParser} is like an
    L{IStreamClientEndpointStringParserWithReactor}, except for
    L{IStreamServerEndpoint}s instead of clients.  It integrates with
    L{endpoints.serverFromString} in much the same way.
    """

    prefix = Attribute(
        """
        A C{str}, the description prefix to respond to.  For example, an
        L{IStreamServerEndpointStringParser} plugin which had C{"foo"} for its
        C{prefix} attribute would be called for endpoint descriptions like
        C{"foo:bar:baz"} or C{"foo:"}.
        """
    )


    def parseStreamServer(reactor, *args, **kwargs):
        """
        Parse a stream server endpoint from a reactor and string-only arguments
        and keyword arguments.

        @see: L{IStreamClientEndpointStringParserWithReactor.parseStreamClient}

        @return: a stream server endpoint
        @rtype: L{IStreamServerEndpoint}
        """


class IStreamClientEndpointStringParserWithReactor(Interface):
    """
    An L{IStreamClientEndpointStringParserWithReactor} is a parser which can
    convert a set of string C{*args} and C{**kwargs} into an
    L{IStreamClientEndpoint} provider.

    This interface is really only useful in the context of the plugin system
    for L{endpoints.clientFromString}.  See the document entitled "I{The
    Twisted Plugin System}" for more details on how to write a plugin.

    If you place an L{IStreamClientEndpointStringParserWithReactor} plugin in
    the C{twisted.plugins} package, that plugin's C{parseStreamClient} method
    will be used to produce endpoints for any description string that begins
    with the result of that L{IStreamClientEndpointStringParserWithReactor}'s
    prefix attribute.
    """

    prefix = Attribute(
        """
        L{bytes}, the description prefix to respond to.  For example, an
        L{IStreamClientEndpointStringParserWithReactor} plugin which had
        C{b"foo"} for its C{prefix} attribute would be called for endpoint
        descriptions like C{b"foo:bar:baz"} or C{b"foo:"}.
        """
    )


    def parseStreamClient(reactor, *args, **kwargs):
        """
        This method is invoked by L{endpoints.clientFromString}, if the type of
        endpoint matches the return value from this
        L{IStreamClientEndpointStringParserWithReactor}'s C{prefix} method.

        @param reactor: The reactor passed to L{endpoints.clientFromString}.

        @param args: The byte string arguments, minus the endpoint type, in the
            endpoint description string, parsed according to the rules
            described in L{endpoints.quoteStringArgument}.  For example, if the
            description were C{b"my-type:foo:bar:baz=qux"}, C{args} would be
            C{(b'foo', b'bar')}

        @param kwargs: The byte string arguments from the endpoint description
            passed as keyword arguments.  For example, if the description were
            C{b"my-type:foo:bar:baz=qux"}, C{kwargs} would be
            C{dict(baz=b'qux')}.

        @return: a client endpoint
        @rtype: a provider of L{IStreamClientEndpoint}
        """
