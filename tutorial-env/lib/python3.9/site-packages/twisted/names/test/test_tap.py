# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.names.tap}.
"""

from twisted.internet.base import ThreadedResolver
from twisted.names.client import Resolver
from twisted.names.dns import PORT
from twisted.names.resolve import ResolverChain
from twisted.names.secondary import SecondaryAuthorityService
from twisted.names.tap import Options, _buildResolvers
from twisted.python.runtime import platform
from twisted.python.usage import UsageError
from twisted.trial.unittest import SynchronousTestCase


class OptionsTests(SynchronousTestCase):
    """
    Tests for L{Options}, defining how command line arguments for the DNS server
    are parsed.
    """

    def test_malformedSecondary(self):
        """
        If the value supplied for an I{--secondary} option does not provide a
        server IP address, optional port number, and domain name,
        L{Options.parseOptions} raises L{UsageError}.
        """
        options = Options()
        self.assertRaises(UsageError, options.parseOptions, ["--secondary", ""])
        self.assertRaises(UsageError, options.parseOptions, ["--secondary", "1.2.3.4"])
        self.assertRaises(
            UsageError, options.parseOptions, ["--secondary", "1.2.3.4:hello"]
        )
        self.assertRaises(
            UsageError,
            options.parseOptions,
            ["--secondary", "1.2.3.4:hello/example.com"],
        )

    def test_secondary(self):
        """
        An argument of the form C{"ip/domain"} is parsed by L{Options} for the
        I{--secondary} option and added to its list of secondaries, using the
        default DNS port number.
        """
        options = Options()
        options.parseOptions(["--secondary", "1.2.3.4/example.com"])
        self.assertEqual([(("1.2.3.4", PORT), ["example.com"])], options.secondaries)

    def test_secondaryExplicitPort(self):
        """
        An argument of the form C{"ip:port/domain"} can be used to specify an
        alternate port number for which to act as a secondary.
        """
        options = Options()
        options.parseOptions(["--secondary", "1.2.3.4:5353/example.com"])
        self.assertEqual([(("1.2.3.4", 5353), ["example.com"])], options.secondaries)

    def test_secondaryAuthorityServices(self):
        """
        After parsing I{--secondary} options, L{Options} constructs a
        L{SecondaryAuthorityService} instance for each configured secondary.
        """
        options = Options()
        options.parseOptions(
            [
                "--secondary",
                "1.2.3.4:5353/example.com",
                "--secondary",
                "1.2.3.5:5354/example.com",
            ]
        )
        self.assertEqual(len(options.svcs), 2)
        secondary = options.svcs[0]
        self.assertIsInstance(options.svcs[0], SecondaryAuthorityService)
        self.assertEqual(secondary.primary, "1.2.3.4")
        self.assertEqual(secondary._port, 5353)
        secondary = options.svcs[1]
        self.assertIsInstance(options.svcs[1], SecondaryAuthorityService)
        self.assertEqual(secondary.primary, "1.2.3.5")
        self.assertEqual(secondary._port, 5354)

    def test_recursiveConfiguration(self):
        """
        Recursive DNS lookups, if enabled, should be a last-resort option.
        Any other lookup method (cache, local lookup, etc.) should take
        precedence over recursive lookups
        """
        options = Options()
        options.parseOptions(["--hosts-file", "hosts.txt", "--recursive"])
        ca, cl = _buildResolvers(options)

        # Extra cleanup, necessary on POSIX because client.Resolver doesn't know
        # when to stop parsing resolv.conf.  See #NNN for improving this.
        for x in cl:
            if isinstance(x, ResolverChain):
                recurser = x.resolvers[-1]
                if isinstance(recurser, Resolver):
                    recurser._parseCall.cancel()

        # On Windows, we need to use a threaded resolver, which leaves trash
        # lying about that we can't easily clean up without reaching into the
        # reactor and cancelling them. We only cancel the cleanup functions, as
        # there should be no others (and it leaving a callLater lying about
        # should rightly cause the test to fail).
        if platform.getType() != "posix":

            # We want the delayed calls on the reactor, which should be all of
            # ours from the threaded resolver cleanup
            from twisted.internet import reactor

            for x in reactor._newTimedCalls:
                self.assertEqual(x.func.__func__, ThreadedResolver._cleanup)
                x.cancel()

        self.assertIsInstance(cl[-1], ResolverChain)
