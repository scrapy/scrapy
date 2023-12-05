# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.ssh.forwarding}.
"""


from twisted.python.reflect import requireModule

cryptography = requireModule("cryptography")
if cryptography:
    from twisted.conch.ssh import forwarding

from twisted.internet.address import IPv6Address
from twisted.internet.test.test_endpoints import deterministicResolvingReactor
from twisted.test.proto_helpers import MemoryReactorClock, StringTransport
from twisted.trial import unittest


class TestSSHConnectForwardingChannel(unittest.TestCase):
    """
    Unit and integration tests for L{SSHConnectForwardingChannel}.
    """

    if not cryptography:
        skip = "Cannot run without cryptography"

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
        sut = forwarding.SSHConnectForwardingChannel(hostport=("fwd.example.org", 1234))
        # Patch channel and resolver to not touch the network.
        memoryReactor = MemoryReactorClock()
        sut._reactor = deterministicResolvingReactor(memoryReactor, ["::1"])
        sut.channelOpen(None)

        self.makeTCPConnection(memoryReactor)
        self.successResultOf(sut._channelOpenDeferred)
        # Channel is connected using a forwarding client to the resolved
        # address of the requested host.
        self.assertIsInstance(sut.client, forwarding.SSHForwardingClient)
        self.assertEqual(
            IPv6Address("TCP", "::1", 1234), sut.client.transport.getPeer()
        )
