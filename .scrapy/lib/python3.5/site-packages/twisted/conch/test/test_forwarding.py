# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.ssh.forwarding}.
"""

from __future__ import division, absolute_import

from socket import AF_INET6

from twisted.conch.ssh import forwarding
from twisted.internet import defer
from twisted.internet.address import IPv6Address
from twisted.trial import unittest
from twisted.test.proto_helpers import MemoryReactorClock, StringTransport


class TestSSHConnectForwardingChannel(unittest.TestCase):
    """
    Unit and integration tests for L{SSHConnectForwardingChannel}.
    """

    def patchHostnameEndpointResolver(self, request, response):
        """
        Patch L{forwarding.HostnameEndpoint} to respond with a predefined
        answer for DNS resolver requests.

        @param request: Tupple of requested (hostname, port).
        @type  request: C{tuppe}.

        @param response: Tupple of (family, address) to respond the the
            associated C{request}.
        @type  response: C{tuppe}.
        """
        hostname, port = request
        family, address = response
        riggerResolver = {('fwd.example.org', 1234): (
            AF_INET6, None, None, None, ('::1', 1234))}

        def riggedResolution(this, host, port):
            return defer.succeed([riggerResolver[(host, port)]])
        self.patch(
            forwarding.HostnameEndpoint, '_nameResolution', riggedResolution)


    def makeTCPConnection(self, reactor):
        """
        Fake that connection was established for first connectTCP request made
        on C{reactor}.

        @param reactor: Reactor on which to fake the connection.
        @type  reactor: A reactor.
        """
        factory = reactor.tcpClients[0][2]
        connector = reactor.connectors[0]
        protocol = factory.buildProtocol(None)
        transport = StringTransport(peerAddress=connector.getDestination())
        protocol.makeConnection(transport)


    def test_channelOpenHostnameRequests(self):
        """
        When a hostname is sent as part of forwarding requests, it
        is resolved using HostnameEndpoint's resolver.
        """
        sut = forwarding.SSHConnectForwardingChannel(
            hostport=('fwd.example.org', 1234))
        # Patch channel and resolver to not touch the network.
        sut._reactor = MemoryReactorClock()
        self.patchHostnameEndpointResolver(
            request=('fwd.example.org', 1234),
            response=(AF_INET6 ,'::1'),
            )

        sut.channelOpen(None)

        self.makeTCPConnection(sut._reactor)
        self.successResultOf(sut._channelOpenDeferred)
        # Channel is connected using a forwarding client to the resolved
        # address of the requested host.
        self.assertIsInstance(sut.client, forwarding.SSHForwardingClient)
        self.assertEqual(
            IPv6Address('TCP', '::1', 1234), sut.client.transport.getPeer())
