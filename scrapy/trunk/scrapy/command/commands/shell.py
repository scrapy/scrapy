from twisted.internet import reactor

import scrapy
from scrapy.command import ScrapyCommand
from scrapy.spider import spiders
from scrapy.xpath import XmlXPathSelector, HtmlXPathSelector
from scrapy.utils.misc import load_class
from scrapy.extension import extensions
from scrapy.conf import settings
from scrapy.core.manager import scrapymanager
from scrapy.http import Request, Response
from scrapy.core.downloader.handlers import download_any
from scrapy.fetcher import get_or_create_spider
from scrapy.utils.decompressor import Decompressor

#This code comes from twisted 8. We define here while
#using old twisted version.
def blockingCallFromThread(reactor, f, *a, **kw):
    """
    Run a function in the reactor from a thread, and wait for the result
    synchronously, i.e. until the callback chain returned by the function
    get a result.

    @param reactor: The L{IReactorThreads} provider which will be used to
        schedule the function call.
    @param f: the callable to run in the reactor thread
    @type f: any callable.
    @param a: the arguments to pass to C{f}.
    @param kw: the keyword arguments to pass to C{f}.

    @return: the result of the callback chain.
    @raise: any error raised during the callback chain.
    """
    import Queue
    from twisted.python import failure
    from twisted.internet import defer
    queue = Queue.Queue()
    def _callFromThread():
        result = defer.maybeDeferred(f, *a, **kw)
        result.addBoth(queue.put)
    reactor.callFromThread(_callFromThread)
    result = queue.get()
    if isinstance(result, failure.Failure):
        result.raiseException()
    return result

class Command(ScrapyCommand):
    def syntax(self):
        return "[url]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url. For scraping local files you can use a URL like file://path/to/file.html"

    def update_vars(self):
        """ You can use this function to update the local variables that will be available in the scrape console """
        pass

    def get_url(self, url, decompress=False):
        #def _get_callback(_response):
            #print "done"
            #if not _response:
                #if not opts.loglevel:
                    #print 'Nothing downloaded, run with -o DEBUG to see why it failed'
                #scrapymanager.stop()
                #return
            #self.generate_vars(url, response)

        #def _errback(_failure):
            #print _failure

        print "Downloading URL...           ",
        r = Request(url)
        spider = get_or_create_spider(url)
        try:
            result = blockingCallFromThread(reactor, download_any, r, spider)
            if isinstance(result, Response):
                print "Done."
                if decompress:
                    print "Decompressing response...",
                    d = Decompressor()
                    result = d.extract(result)
                    print "Done."
                self.generate_vars(url, result)
                return True
        except Exception, e:
            print "Error: %s" % e

    def generate_vars(self, url, response):
        itemcls = load_class(settings['DEFAULT_ITEM_CLASS'])
        item = itemcls()
        self.vars['item'] = item
        if url:
            self.vars['xxs'] = XmlXPathSelector(response)
            self.vars['hxs'] = HtmlXPathSelector(response)
            self.vars['url'] = url
            self.vars['response'] = response
            self.vars['spider'] = spiders.fromurl(url)
        self.update_vars()
        self.user_ns.update(self.vars)
        self.print_vars()
        
    def print_vars(self):
        print '-' * 78
        print "Available local variables:"
        for key, val in self.vars.iteritems():
            if isinstance(val, basestring):
                print "   %s: %s" % (key, val)
            else:
                print "   %s: %s" % (key, val.__class__)
        print "Available commands:"
        print "   get <url>: Fetches an url and updates all variables."
        print "   getd <url>: Similar to get, but filter with decompress."
        print "   scrapehelp: Prints this help."
        print '-' * 78
    
    def run(self, args, opts):
        self.vars = {}
        self.user_ns = {}
        url = None
        if args:
            url = args[0]

        print "Scrapy %s - Interactive scraping console\n" % scrapy.__version__

        print "Enabling Scrapy extensions...",
        extensions.load()
        print "done"

        def _console_thread():
            
            def _get_magic(shell, arg):
                self.get_url(arg.strip())
            def _help_magic(shell, _):
                self.print_vars()
            def _getd_magic(shell, arg):
                self.get_url(arg.strip(), decompress=True)
                
            if url:
                result = self.get_url(url)
                if not result:
                    self.generate_vars(None, None)
            else:
                self.generate_vars(None, None)
            try: # use IPython if available
                import IPython
                shell = IPython.Shell.IPShell(argv=[], user_ns=self.user_ns)
                ip = shell.IP.getapi()
                ip.expose_magic("get", _get_magic)
                ip.expose_magic("getd", _getd_magic)
                ip.expose_magic("scrapehelp", _help_magic)
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