from twisted.trial import unittest
from twisted.conch.telnet import ITelnetProtocol
from twisted.cred import credentials
from twisted.internet import defer

from scrapy.extensions.telnet import TelnetConsole
from scrapy.utils.test import get_crawler


class TelnetExtensionTest(unittest.TestCase):
    def _get_console_and_portal(self, settings=None):
        crawler = get_crawler(settings_dict=settings)
        console = TelnetConsole(crawler)

        # This function has some side effects we don't need for this test
        console._get_telnet_vars = lambda: {}

        console.start_listening()
        protocol = console.protocol()
        portal = protocol.protocolArgs[0]

        return console, portal

    @defer.inlineCallbacks
    def test_bad_credentials(self):
        console, portal = self._get_console_and_portal()
        creds = credentials.UsernamePassword(b'username', b'password')
        d = portal.login(creds, None, ITelnetProtocol)
        yield self.assertFailure(d, ValueError)
        console.stop_listening()

    @defer.inlineCallbacks
    def test_good_credentials(self):
        console, portal = self._get_console_and_portal()
        creds = credentials.UsernamePassword(
            console.username.encode('utf8'),
            console.password.encode('utf8')
        )
        d = portal.login(creds, None, ITelnetProtocol)
        yield d
        console.stop_listening()

    @defer.inlineCallbacks
    def test_custom_credentials(self):
        settings = {
            'TELNETCONSOLE_USERNAME': 'user',
            'TELNETCONSOLE_PASSWORD': 'pass',
        }
        console, portal = self._get_console_and_portal(settings=settings)
        creds = credentials.UsernamePassword(b'user', b'pass')
        d = portal.login(creds, None, ITelnetProtocol)
        yield d
        console.stop_listening()
