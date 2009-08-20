"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

import os
import urllib
import urlparse

from twisted.internet import reactor, threads

from scrapy.command import ScrapyCommand
from scrapy.spider import spiders
from scrapy.selector import XmlXPathSelector, HtmlXPathSelector
from scrapy.utils.misc import load_object
from scrapy.conf import settings
from scrapy.core.manager import scrapymanager
from scrapy.core.engine import scrapyengine
from scrapy.http import Request
from scrapy.fetcher import get_or_create_spider

class Command(ScrapyCommand):
    def syntax(self):
        return "[url]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url. For scraping local files you can use a URL like file://path/to/file.html"

    def update_vars(self):
        """ You can use this function to update the Scrapy objects that will be available in the shell"""
        pass

    def get_url(self, url):
        url = url.strip()
        if url:
            u = urlparse.urlparse(url)
            if not u.scheme:
                path = os.path.abspath(url).replace(os.sep, '/')
                url = 'file://' + urllib.pathname2url(path)
                u = urlparse.urlparse(url)

            if u.scheme not in ('http', 'https', 'file'):
                print "Unsupported scheme '%s' in URL: <%s>" % (u.scheme, url)
                return
            request = Request(url)
        else:
            request = self.user_ns['request']

        spider = get_or_create_spider(url)
        print "Fetching %s..." % request
        response = threads.blockingCallFromThread(reactor, scrapyengine.schedule, request, spider)
        if response:
            self.generate_vars(url, response, request)
            return True

    def generate_vars(self, url=None, response=None, request=None):
        itemcls = load_object(settings['DEFAULT_ITEM_CLASS'])
        item = itemcls()
        self.vars['item'] = item
        if url:
            self.vars['xxs'] = XmlXPathSelector(response)
            self.vars['hxs'] = HtmlXPathSelector(response)
            self.vars['url'] = url
            self.vars['response'] = response
            self.vars['request'] = request
            self.vars['spider'] = spiders.fromurl(url)
        self.update_vars()
        self.user_ns.update(self.vars)
        self.print_vars()
        
    def print_vars(self):
        print '-' * 60
        print "Available Scrapy objects:"
        for key, val in self.vars.iteritems():
            print "   %s: %s" % (key, val)
        print "Available commands:"
        print "   get [url]: Fetch a new URL or re-fetch current Request"
        print "   shelp: Prints this help."
        print '-' * 60
    
    def run(self, args, opts):
        self.vars = {}
        self.user_ns = {}
        url = None
        if args:
            url = args[0]

        print "Welcome to Scrapy shell!"

        def _console_thread():
            
            def _get_magic(shell, arg):
                self.get_url(arg)
            def _help_magic(shell, _):
                self.print_vars()
                
            if url:
                result = self.get_url(url)
                if not result:
                    self.generate_vars()
            else:
                self.generate_vars()
            try: # use IPython if available
                import IPython
                shell = IPython.Shell.IPShell(argv=[], user_ns=self.user_ns)
                ip = shell.IP.getapi()
                ip.expose_magic("get", _get_magic)
                ip.expose_magic("shelp", _help_magic)
                shell.mainloop()
                reactor.callFromThread(scrapymanager.stop)
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

        reactor.callInThread(_console_thread)
        scrapymanager.start()
