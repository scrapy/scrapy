"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

import os
import urllib
import urlparse
import signal

from twisted.internet import reactor, threads

from scrapy.spider import spiders
from scrapy.selector import XmlXPathSelector, HtmlXPathSelector
from scrapy.utils.misc import load_object
from scrapy.utils.response import open_in_browser
from scrapy.conf import settings
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.http import Request
from scrapy.fetcher import get_or_create_spider
from scrapy import log

def relevant_var(varname):
    return varname not in ['shelp', 'fetch', 'view', '__builtins__', 'In', \
        'Out', 'help'] and not varname.startswith('_')

def parse_url(url):
    """Parse url which can be a direct path to a direct file"""
    url = url.strip()
    if url:
        u = urlparse.urlparse(url)
        if not u.scheme:
            path = os.path.abspath(url).replace(os.sep, '/')
            url = 'file://' + urllib.pathname2url(path)
            u = urlparse.urlparse(url)
    return url

class Shell(object):

    requires_project = False

    def __init__(self, update_vars=None, nofetch=False):
        self.vars = {}
        self.update_vars = update_vars
        self.item_class = load_object(settings['DEFAULT_ITEM_CLASS'])
        self.nofetch = nofetch

    def fetch(self, request_or_url, print_help=False):
        if isinstance(request_or_url, Request):
            request = request_or_url
            url = request.url
        else:
            url = parse_url(request_or_url)
            request = Request(url)
        spider = get_or_create_spider(url)
        print "Fetching %s..." % request
        response = threads.blockingCallFromThread(reactor, scrapyengine.schedule, \
            request, spider)
        if response:
            self.populate_vars(url, response, request)
            if print_help:
                self.print_help()
            else:
                print "Done - use shelp() to see available objects"

    def populate_vars(self, url=None, response=None, request=None):
        item = self.item_class()
        self.vars['item'] = item
        if url:
            self.vars['xxs'] = XmlXPathSelector(response)
            self.vars['hxs'] = HtmlXPathSelector(response)
            self.vars['url'] = url
            self.vars['response'] = response
            self.vars['request'] = request
            self.vars['spider'] = spiders.fromurl(url)

            if not self.nofetch:
                self.vars['fetch'] = self.fetch
            self.vars['view'] = open_in_browser
            self.vars['shelp'] = self.print_help

        if self.update_vars:
            self.update_vars(self.vars)

    def print_help(self):
        print "Available objects"
        print "================="
        print
        for k, v in self.vars.iteritems():
            if relevant_var(k):
                print "  %-10s: %s" % (k, v)
        print
        print "Available shortcuts"
        print "==================="
        print
        print "  shelp()           : Prints this help."
        if not self.nofetch:
            print "  fetch(req_or_url) : Fetch a new request or URL and update objects"
        print "  view(response)    : View response in a browser"
        print

    def start(self, url):
        # disable accidental Ctrl-C key press from shutting down the engine
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        reactor.callInThread(self._console_thread, url)
        scrapymanager.start()

    def inspect_response(self, response):
        print
        print "Scrapy Shell"
        print "============"
        print
        print "Inspecting: %s" % response
        print "Use shelp() to see available objects"
        print
        request = response.request
        url = request.url
        self.populate_vars(url, response, request)
        self._run_console()

    def _run_console(self):
        try: # use IPython if available
            import IPython
            shell = IPython.Shell.IPShell(argv=[], user_ns=self.vars)
            ip = shell.IP.getapi()
            shell.mainloop()
        except ImportError:
            import code
            try: # readline module is only available on unix systems
                import readline
            except ImportError:
                pass
            else:
                import rlcompleter
                readline.parse_and_bind("tab:complete")
            code.interact(local=self.vars)

    def _console_thread(self, url=None):
        self.populate_vars()
        if url:
            result = self.fetch(url, print_help=True)
        else:
            self.print_help()
        self._run_console()
        reactor.callFromThread(scrapymanager.stop)

def inspect_response(response):
    """Open a shell to inspect the given response"""
    shell = Shell(nofetch=True)
    log._switch_descriptors()
    shell.inspect_response(response)
    log._switch_descriptors()
