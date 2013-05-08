"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

import pprint

from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import protocol

from scrapy.exceptions import NotConfigured
from scrapy import log, signals
from scrapy.utils.trackref import print_live_refs
from scrapy.utils.engine import print_engine_status
from scrapy.utils.reactor import listen_tcp

try:
    import guppy
    hpy = guppy.hpy()
except ImportError:
    hpy = None

# signal to update telnet variables
# args: telnet_vars
update_telnet_vars = object()


class TelnetConsole(protocol.ServerFactory):

    def __init__(self, crawler):
        if not crawler.settings.getbool('TELNETCONSOLE_ENABLED'):
            raise NotConfigured
        self.crawler = crawler
        self.noisy = False
        self.portrange = map(int, crawler.settings.getlist('TELNETCONSOLE_PORT'))
        self.host = crawler.settings['TELNETCONSOLE_HOST']
        self.crawler.signals.connect(self.start_listening, signals.engine_started)
        self.crawler.signals.connect(self.stop_listening, signals.engine_stopped)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def start_listening(self):
        self.port = listen_tcp(self.portrange, self.host, self)
        h = self.port.getHost()
        log.msg(format="Telnet console listening on %(host)s:%(port)d",
                level=log.DEBUG, host=h.host, port=h.port)

    def stop_listening(self):
        self.port.stopListening()

    def protocol(self):
        telnet_vars = self._get_telnet_vars()
        return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
            insults.ServerProtocol, manhole.Manhole, telnet_vars)

    def _get_telnet_vars(self):
        # Note: if you add entries here also update topics/telnetconsole.rst
        slots = self.crawler.engine.slots
        if len(slots) == 1:
            spider, slot = slots.items()[0]
        telnet_vars = {
            'engine': self.crawler.engine,
            'spider': spider,
            'slot': slot,
            'crawler': self.crawler,
            'extensions': self.crawler.extensions,
            'stats': self.crawler.stats,
            'spiders': self.crawler.spiders,
            'settings': self.crawler.settings,
            'est': lambda: print_engine_status(self.crawler.engine),
            'p': pprint.pprint,
            'prefs': print_live_refs,
            'hpy': hpy,
            'help': "This is Scrapy telnet console. For more info see: " \
                "http://doc.scrapy.org/en/latest/topics/telnetconsole.html",
        }
        self.crawler.signals.send_catch_log(update_telnet_vars, telnet_vars=telnet_vars)
        return telnet_vars
