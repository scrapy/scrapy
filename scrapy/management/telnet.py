"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

import pprint

from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import protocol

from scrapy.extension import extensions
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.spider import spiders
from scrapy.stats import stats
from scrapy.conf import settings

try:
    import guppy
    hpy = guppy.hpy()
except ImportError:
    hpy = None

# if you add entries here also update topics/telnetconsole.rst
telnet_namespace = {
    'engine': scrapyengine,
    'manager': scrapymanager,
    'extensions': extensions,
    'stats': stats,
    'spiders': spiders,
    'settings': settings,
    'p': pprint.pprint,
    'hpy': hpy,
}

def makeProtocol():
    return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
                                  insults.ServerProtocol,
                                  manhole.Manhole, telnet_namespace)

class TelnetConsole(protocol.ServerFactory):

    def __init__(self):
        if not settings.getbool('TELNETCONSOLE_ENABLED'):
            return
        self.protocol = makeProtocol
        self.noisy = False
        port = settings.getint('TELNETCONSOLE_PORT')
        scrapyengine.listenTCP(port, self)
