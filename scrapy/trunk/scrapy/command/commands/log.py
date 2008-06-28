import re

from scrapy.command import ScrapyCommand

log_crawled_re = re.compile(r'^(.*?) \[\w+/(.*?)\].*Crawled <(.*?)> from <(.*?)>$')
log_scraped_re = re.compile('^(.*?) \[\w+/(.*?)\].*Scraped (.*) in <(.*?)>$')
log_opendomain_re = re.compile('^(.*?) \[\w+.*? Started scraping (.*)$')
log_closedomain_re = re.compile('^(.*?) \[\w+.*? Finished scraping (.*)$')
log_debug_re = re.compile(r'\[\w+/(.*?)\] DEBUG')
log_info_re = re.compile(r'\[\w+/(.*?)\] INFO')
log_warning_re = re.compile(r'\[\w+/(.*?)\] WARNING')
log_error_re = re.compile(r'\[\w+/(.*?)\] ERROR')

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <logfile>"

    def short_desc(self):
        return "Several tools to perform scrapy log analysis"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--sitemap", dest="sitemap", action="store_true", help="show sitemap based on given log file")

    def sitemap(self, logfile):
        from scrapy.utils.datatypes import Sitemap

        sm = Sitemap()
        for l in open(logfile).readlines():
            m = log_crawled_re.search(l.strip())
            if m:
                sm.add_node(m.group(3), m.group(4))
            m = log_scraped_re.search(l.strip())
            if m:
                sm.add_item(m.group(4), m.group(3))
        print sm.to_string()

    def run(self, args, opts):
        if not args:
            print "A log file is required"
            return

        if opts.sitemap:
            self.sitemap(args[0])
        else:
            print "No analysis method specified"
