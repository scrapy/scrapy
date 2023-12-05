# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.xmpproutertap}.
"""

from twisted.application import internet
from twisted.trial import unittest
from twisted.words import xmpproutertap as tap
from twisted.words.protocols.jabber import component


class XMPPRouterTapTests(unittest.TestCase):
    def test_port(self):
        """
        The port option is recognised as a parameter.
        """
        opt = tap.Options()
        opt.parseOptions(["--port", "7001"])
        self.assertEqual(opt["port"], "7001")

    def test_portDefault(self):
        """
        The port option has '5347' as default value
        """
        opt = tap.Options()
        opt.parseOptions([])
        self.assertEqual(opt["port"], "tcp:5347:interface=127.0.0.1")

    def test_secret(self):
        """
        The secret option is recognised as a parameter.
        """
        opt = tap.Options()
        opt.parseOptions(["--secret", "hushhush"])
        self.assertEqual(opt["secret"], "hushhush")

    def test_secretDefault(self):
        """
        The secret option has 'secret' as default value
        """
        opt = tap.Options()
        opt.parseOptions([])
        self.assertEqual(opt["secret"], "secret")

    def test_verbose(self):
        """
        The verbose option is recognised as a flag.
        """
        opt = tap.Options()
        opt.parseOptions(["--verbose"])
        self.assertTrue(opt["verbose"])

    def test_makeService(self):
        """
        The service gets set up with a router and factory.
        """
        opt = tap.Options()
        opt.parseOptions([])
        s = tap.makeService(opt)
        self.assertIsInstance(s, internet.StreamServerEndpointService)
        self.assertEqual("127.0.0.1", s.endpoint._interface)
        self.assertEqual(5347, s.endpoint._port)
        factory = s.factory
        self.assertIsInstance(factory, component.XMPPComponentServerFactory)
        self.assertIsInstance(factory.router, component.Router)
        self.assertEqual("secret", factory.secret)
        self.assertFalse(factory.logTraffic)

    def test_makeServiceVerbose(self):
        """
        The verbose flag enables traffic logging.
        """
        opt = tap.Options()
        opt.parseOptions(["--verbose"])
        s = tap.makeService(opt)
        self.assertTrue(s.factory.logTraffic)
