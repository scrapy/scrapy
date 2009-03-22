"""
Base class for Scrapy commands
"""
import os
import sys
from scrapy.conf import settings

class ScrapyCommand(object):
    def syntax(self):
        """
        Command syntax (preferably one-line). Do not include command name.
        """
        return ""

    def short_desc(self):
        """
        A short description of the command
        """
        return ""

    def long_desc(self):
        """
        A long description of the command. Return short description when not
        available. It cannot contain newlines, since contents will be formatted
        by optparser which removes newlines and wraps text.
        """
        return self.short_desc()

    def help(self):
        """
        An extensive help for the command. It will be shown when using the
        "help" command. It can contain newlines, since not post-formatting will
        be applied to its contents.
        """
        return self.long_desc()

    def add_options(self, parser):
        """
        Populate option parse with options available for this command
        """
        parser.add_option("-f", "--logfile", dest="logfile", help="logfile to use. if omitted stderr will be used", metavar="FILE")
        parser.add_option("-o", "--loglevel", dest="loglevel", default=None, help="log level")
        parser.add_option("--default-spider", dest="default_spider", default=None, help="default spider (domain) to use if no spider is found")
        parser.add_option("--spider", dest="spider", default=None, help="Force using the given spider when the arguments are urls")
        parser.add_option("--nolog", dest="nolog", action="store_true", help="disable all log messages")
        parser.add_option("--profile", dest="profile", default=None, help="write profiling stats in FILE, to analyze later with: python -m pstats FILE", metavar="FILE")
        parser.add_option("--pidfile", dest="pidfile", help="Write process pid to file FILE", metavar="FILE")
        parser.add_option("--set", dest="settings", action="append", metavar="SETTING:VALUE", default=[], 
                            help="Override Scrapy setting SETTING with VALUE. May be repeated.")
        
    def process_options(self, args, opts):
        if opts.logfile:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOGFILE'] = opts.logfile

        if opts.loglevel:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOGLEVEL'] = opts.loglevel

        if opts.nolog:
            settings.overrides['LOG_ENABLED'] = False

        if opts.default_spider:
            from scrapy.spider import spiders
            spiders.default_domain = opts.default_spider
            
        if opts.spider:
            from scrapy.spider import spiders
            spiders.force_domain = opts.spider

        if opts.pidfile:
            pid = os.getpid()
            open(opts.pidfile, "w").write(str(pid))

        for setting in opts.settings:
            if ':' in setting:
                name, val = setting.split(':', 1)
                settings.overrides[name] = val
            else:
                sys.stderr.write("%s: invalid argument --set=%s - proper format is --set=SETTING:VALUE'\n" % (sys.argv[0], setting))
                sys.exit(2)

    def run(self, args, opts):
        """
        Entry point for running commands
        """
        raise NotImplementedError


