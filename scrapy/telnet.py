"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

import pprint

from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import protocol

from scrapy.xlib.pydispatch import dispatcher
from scrapy.exceptions import NotConfigured
from scrapy.project import crawler
from scrapy.stats import stats
from scrapy import log, signals
from scrapy.utils.signal import send_catch_log
from scrapy.utils.trackref import print_live_refs
from scrapy.utils.engine import print_engine_status
from scrapy.utils.reactor import listen_tcp
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
        self.portrange = map(int, settings.getlist('TELNETCONSOLE_PORT'))
        self.host = settings['TELNETCONSOLE_HOST']
        dispatcher.connect(self.start_listening, signals.engine_started)
        dispatcher.connect(self.stop_listening, signals.engine_stopped)

    def start_listening(self):
        self.port = listen_tcp(self.portrange, self.host, self)
        h = self.port.getHost()
        log.msg("Telnet console listening on %s:%d" % (h.host, h.port), log.DEBUG)

    def stop_listening(self):
        self.port.stopListening()

    def protocol(self):
        telnet_vars = self._get_telnet_vars()
        return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
            insults.ServerProtocol, manhole.Manhole, telnet_vars)

    def _get_telnet_vars(self):
        # Note: if you add entries here also update topics/telnetconsole.rst
        telnet_vars = {
            'engine': crawler.engine,
            'manager': crawler,
            'extensions': crawler.extensions,
            'stats': stats,
            'spiders': crawler.spiders,
            'settings': settings,
            'est': print_engine_status,
            'p': pprint.pprint,
            'prefs': print_live_refs,
            'hpy': hpy,
            'help': "This is Scrapy telnet console. For more info see: " \
                "http://doc.scrapy.org/topics/telnetconsole.html", # see #284
        }
        send_catch_log(update_telnet_vars, telnet_vars=telnet_vars)
        return telnet_vars
