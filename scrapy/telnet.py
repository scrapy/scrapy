"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

import pprint

from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import reactor, protocol

from scrapy.extension import extensions
from scrapy.exceptions import NotConfigured
from scrapy.project import crawler
from scrapy.spider import spiders
from scrapy.stats import stats
from scrapy.utils.signal import send_catch_log
from scrapy.utils.trackref import print_live_refs
from scrapy.utils.engine import print_engine_status
from scrapy.conf import settings

try:
    import guppy
    hpy = guppy.hpy()
except ImportError:
    hpy = None

# signal to update telnet variables
# args: telnet_vars
update_telnet_vars = object()


class TelnetConsole(protocol.ServerFactory):

    def __init__(self):
        if not settings.getbool('TELNETCONSOLE_ENABLED'):
            raise NotConfigured
        self.noisy = False
        port = settings.getint('TELNETCONSOLE_PORT')
        reactor.callWhenRunning(reactor.listenTCP, port, self)

    def protocol(self):
        telnet_vars = self._get_telnet_vars()
        return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
            insults.ServerProtocol, manhole.Manhole, telnet_vars)

    def _get_telnet_vars(self):
        # Note: if you add entries here also update topics/telnetconsole.rst
        telnet_vars = {
            'engine': crawler.engine,
            'manager': crawler,
            'extensions': extensions,
            'stats': stats,
            'spiders': spiders,
            'settings': settings,
            'est': print_engine_status,
            'p': pprint.pprint,
            'prefs': print_live_refs,
            'hpy': hpy,
        }
        send_catch_log(update_telnet_vars, telnet_vars=telnet_vars)
        return telnet_vars
