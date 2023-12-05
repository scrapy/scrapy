# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.strports}.
"""


from twisted.application import internet, strports
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import Factory
from twisted.trial.unittest import TestCase


class ServiceTests(TestCase):
    """
    Tests for L{strports.service}.
    """

    def test_service(self):
        """
        L{strports.service} returns a L{StreamServerEndpointService}
        constructed with an endpoint produced from
        L{endpoint.serverFromString}, using the same syntax.
        """
        reactor = object()  # the cake is a lie
        aFactory = Factory()
        aGoodPort = 1337
        svc = strports.service("tcp:" + str(aGoodPort), aFactory, reactor=reactor)
        self.assertIsInstance(svc, internet.StreamServerEndpointService)

        # See twisted.application.test.test_internet.EndpointServiceTests.
        # test_synchronousRaiseRaisesSynchronously
        self.assertTrue(svc._raiseSynchronously)
        self.assertIsInstance(svc.endpoint, TCP4ServerEndpoint)
        # Maybe we should implement equality for endpoints.
        self.assertEqual(svc.endpoint._port, aGoodPort)
        self.assertIs(svc.factory, aFactory)
        self.assertIs(svc.endpoint._reactor, reactor)

    def test_serviceDefaultReactor(self):
        """
        L{strports.service} will use the default reactor when none is provided
        as an argument.
        """
        from twisted.internet import reactor as globalReactor

        aService = strports.service("tcp:80", None)
        self.assertIs(aService.endpoint._reactor, globalReactor)
