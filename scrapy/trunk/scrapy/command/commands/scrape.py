import scrapy
from scrapy.command import ScrapyCommand
from scrapy.fetcher import fetch
from scrapy.spider import spiders
from scrapy.xpath import XmlXPathSelector, HtmlXPathSelector
from scrapy.utils.misc import load_class
from scrapy.extension import extensions
from scrapy.conf import settings

def get_url(url):
    from scrapy.http import Request
    from scrapy.core.downloader.handlers import download_any
    request = Request(url)
    spider = spiders.fromurl(url)

    return download_any(request, spider)

def load_url(url, response):
    vars = {}
    itemcls = load_class(settings['DEFAULT_ITEM_CLASS'])
    item = itemcls()
    vars['item'] = item
    vars['xxs'] = XmlXPathSelector(response)
    vars['hxs'] = HtmlXPathSelector(response)
    if url:
        vars['url'] = url
        vars['response'] = response
        vars['spider'] = spiders.fromurl(url)
    vars['get'] = get_url
    return vars

def print_vars(vars):
    print '-' * 78
    print "Available local variables:"
    for key, val in vars.iteritems():
        if isinstance(val, basestring):
            print "   %s: %s" % (key, val)
        else:
            print "   %s: %s" % (key, val.__class__)
    print '-' * 78

class Command(ScrapyCommand):
    def syntax(self):
        return "[url]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url. For scraping local files you can use a URL like file://path/to/file.html"

    def update_vars(self, vars):
        """ You can use this function to update the local variables that will be available in the scrape console """
        pass

    def run(self, args, opts):
        
        url = None
        if args:
            url = args[0]

        print "Scrapy %s - Interactive scraping console\n" % scrapy.__version__

        print "Enabling Scrapy extensions...",
        extensions.load()
        print "done"
        response = None
        if url:
            print "Downloading URL...           ",
            responses = fetch([url])
            print "done"
            if not responses:
                if not opts.loglevel:
                    print 'Nothing downloaded, run with -o DEBUG to see why it failed'
                return
            response = responses[0]

        vars = load_url(url, response)
        self.update_vars(vars)
        print_vars(vars)

        try: # use IPython if available
            import IPython
            shell = IPython.Shell.IPShell(argv=[], user_ns=vars)
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
            code.interact(local=vars)
