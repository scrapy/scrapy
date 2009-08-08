"""
Base class for Scrapy commands
"""

from __future__ import with_statement

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
        parser.add_option("--logfile", dest="logfile", metavar="FILE", \
            help="log file. if omitted stderr will be used")
        parser.add_option("-L", "--loglevel", dest="loglevel", metavar="LEVEL", \
            default=None, \
            help="log level. use SILENT level to diasble all log messages")
        parser.add_option("--default-spider", dest="default_spider", default=None, \
            help="use this spider when arguments are urls and no spider is found")
        parser.add_option("--spider", dest="spider", default=None, \
            help="always use this spider when arguments are urls")
        parser.add_option("--profile", dest="profile", metavar="FILE", default=None, \
            help="write python cProfile stats to FILE")
        parser.add_option("--pidfile", dest="pidfile", metavar="FILE", \
            help="write process ID to FILE")
        parser.add_option("--set", dest="settings", action="append", \
            metavar="SETTING=VALUE", default=[], \
            help="set/override setting (may be repeated)")
        
    def process_options(self, args, opts):
        if opts.logfile:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOGFILE'] = opts.logfile

        if opts.loglevel:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOGLEVEL'] = opts.loglevel

        if opts.default_spider:
            from scrapy.spider import spiders
            spiders.default_domain = opts.default_spider
            
        if opts.spider:
            from scrapy.spider import spiders
            spiders.force_domain = opts.spider

        if opts.pidfile:
            with open(opts.pidfile, "w") as f:
                f.write(str(os.getpid()))

        for setting in opts.settings:
            if '=' in setting:
                name, val = setting.split('=', 1)
                settings.overrides[name] = val
            else:
                sys.stderr.write("%s: invalid argument --set %s - proper format is --set SETTING=VALUE'\n" % (sys.argv[0], setting))
                sys.exit(2)

    def run(self, args, opts):
        """
        Entry point for running commands
        """
        raise NotImplementedError


