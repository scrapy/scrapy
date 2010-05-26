"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

import pprint

from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import reactor, protocol

from scrapy.extension import extensions
from scrapy.core.exceptions import NotConfigured
from scrapy.core.manager import scrapymanager
from scrapy.spider import spiders
from scrapy.stats import stats
from scrapy.utils.trackref import print_live_refs
from scrapy.utils.engine import print_engine_status
from scrapy.conf import settings

try:
    import guppy
    hpy = guppy.hpy()
except ImportError:
    hpy = None

# if you add entries here also update topics/telnetconsole.rst
telnet_namespace = {
    'engine': scrapymanager.engine,
    'manager': scrapymanager,
    'extensions': extensions,
    'stats': stats,
    'spiders': spiders,
    'settings': settings,
    'est': print_engine_status,
    'p': pprint.pprint,
    'prefs': print_live_refs,
    'hpy': hpy,
}

def makeProtocol():
    return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
        insults.ServerProtocol, manhole.Manhole, telnet_namespace)

class TelnetConsole(protocol.ServerFactory):

    def __init__(self):
        if not settings.getbool('TELNETCONSOLE_ENABLED'):
            raise NotConfigured
        self.protocol = makeProtocol
        self.noisy = False
        port = settings.getint('TELNETCONSOLE_PORT')
        reactor.callWhenRunning(reactor.listenTCP, port, self)
