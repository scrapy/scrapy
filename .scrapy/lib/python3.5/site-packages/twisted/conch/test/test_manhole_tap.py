# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.manhole_tap}.
"""

try:
    import cryptography
except ImportError:
    cryptography = None

try:
    import pyasn1
except ImportError:
    pyasn1 = None

if cryptography and pyasn1:
    from twisted.conch import manhole_tap, manhole_ssh

from twisted.application.internet import StreamServerEndpointService
from twisted.application.service import MultiService

from twisted.cred import error
from twisted.cred.credentials import UsernamePassword

from twisted.conch import telnet

from twisted.python import usage

from twisted.trial.unittest import TestCase



class MakeServiceTests(TestCase):
    """
    Tests for L{manhole_tap.makeService}.
    """

    if not cryptography:
        skip = "can't run without cryptography"

    if not pyasn1:
        skip = "Cannot run without PyASN1"

    usernamePassword = (b'iamuser', b'thisispassword')

    def setUp(self):
        """
        Create a passwd-like file with a user.
        """
        self.filename = self.mktemp()
        with open(self.filename, 'wb') as f:
            f.write(b':'.join(self.usernamePassword))
        self.options = manhole_tap.Options()


    def test_requiresPort(self):
        """
        L{manhole_tap.makeService} requires either 'telnetPort' or 'sshPort' to
        be given.
        """
        with self.assertRaises(usage.UsageError) as e:
            manhole_tap.Options().parseOptions([])

        self.assertEqual(e.exception.args[0], ("At least one of --telnetPort "
                         "and --sshPort must be specified"))


    def test_telnetPort(self):
        """
        L{manhole_tap.makeService} will make a telnet service on the port
        defined by C{--telnetPort}. It will not make a SSH service.
        """
        self.options.parseOptions(["--telnetPort", "222"])
        service = manhole_tap.makeService(self.options)
        self.assertIsInstance(service, MultiService)
        self.assertEqual(len(service.services), 1)
        self.assertIsInstance(service.services[0], StreamServerEndpointService)
        self.assertIsInstance(service.services[0].factory.protocol,
                              manhole_tap.makeTelnetProtocol)
        self.assertEqual(service.services[0].endpoint._port, 222)


    def test_sshPort(self):
        """
        L{manhole_tap.makeService} will make a SSH service on the port
        defined by C{--sshPort}. It will not make a telnet service.
        """
        # Why the sshKeyDir and sshKeySize params? To prevent it stomping over
        # (or using!) the user's private key, we just make a super small one
        # which will never be used in a temp directory.
        self.options.parseOptions(["--sshKeyDir", self.mktemp(),
                                   "--sshKeySize", "512",
                                   "--sshPort", "223"])
        service = manhole_tap.makeService(self.options)
        self.assertIsInstance(service, MultiService)
        self.assertEqual(len(service.services), 1)
        self.assertIsInstance(service.services[0], StreamServerEndpointService)
        self.assertIsInstance(service.services[0].factory,
                              manhole_ssh.ConchFactory)
        self.assertEqual(service.services[0].endpoint._port, 223)


    def test_passwd(self):
        """
        The C{--passwd} command-line option will load a passwd-like file.
        """
        self.options.parseOptions(['--telnetPort', '22',
                                   '--passwd', self.filename])
        service = manhole_tap.makeService(self.options)
        portal = service.services[0].factory.protocol.portal

        self.assertEqual(len(portal.checkers.keys()), 2)

        # Ensure it's the passwd file we wanted by trying to authenticate
        self.assertTrue(self.successResultOf(
            portal.login(UsernamePassword(*self.usernamePassword),
                         None, telnet.ITelnetProtocol)))
        self.assertIsInstance(self.failureResultOf(
            portal.login(UsernamePassword(b"wrong", b"user"),
                         None, telnet.ITelnetProtocol)).value,
                         error.UnauthorizedLogin)
