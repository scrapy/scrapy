import pprint

from twisted.internet import reactor
from twisted.conch import manhole, telnet
from twisted.conch.insults import insults
from twisted.internet import protocol

from scrapy.extension import extensions
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.stats import stats
from scrapy.conf import settings

try:
    import guppy
    hpy = guppy.hpy()
except ImportError:
    hpy = None

telnet_namespace = {'ee': scrapyengine,
                    'em': scrapymanager,
                    'ex': extensions.enabled,
                    'st': stats,
                    'h': hpy,
                    'p': pprint.pprint}  # useful shortcut for debugging

def makeProtocol():
    return telnet.TelnetTransport(telnet.TelnetBootstrapProtocol,
                                  insults.ServerProtocol,
                                  manhole.Manhole, telnet_namespace)

class TelnetConsole(protocol.ServerFactory):

    def __init__(self):
        if not settings.getbool('TELNETCONSOLE_ENABLED'):
            return

        #protocol.ServerFactory.__init__(self)
        self.protocol = makeProtocol
        self.noisy = False
        port = settings.getint('TELNETCONSOLE_PORT')
        scrapyengine.listenTCP(port, self)
