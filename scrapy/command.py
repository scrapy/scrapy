"""
Base class for Scrapy commands
"""

from __future__ import with_statement

import os
import sys
from optparse import OptionGroup

import scrapy
from scrapy import log
from scrapy.conf import settings
from scrapy.utils.conf import arglist_to_dict
from scrapy.exceptions import UsageError

class ScrapyCommand(object):

    requires_project = False

    # default settings to be used for this command instead of global defaults
    default_settings = {}

    exitcode = 0

    def set_crawler(self, crawler):
        self._crawler = crawler

    @property
    def crawler(self):
        if not log.started:
            log.start()
        self._crawler.configure()
        return self._crawler

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
        """A long description of the command. Return short description when not
        available. It cannot contain newlines, since contents will be formatted
        by optparser which removes newlines and wraps text.
        """
        return self.short_desc()

    def help(self):
        """An extensive help for the command. It will be shown when using the
        "help" command. It can contain newlines, since not post-formatting will
        be applied to its contents.
        """
        return self.long_desc()

    def add_options(self, parser):
        """
        Populate option parse with options available for this command
        """
        group = OptionGroup(parser, "Global Options")
        group.add_option("--logfile", dest="logfile", metavar="FILE", \
            help="log file. if omitted stderr will be used")
        group.add_option("-L", "--loglevel", dest="loglevel", metavar="LEVEL", \
            default=None, \
            help="log level (default: %s)" % settings['LOGLEVEL'])
        group.add_option("--nolog", action="store_true", dest="nolog", \
            help="disable logging completely")
        group.add_option("--profile", dest="profile", metavar="FILE", default=None, \
            help="write python cProfile stats to FILE")
        group.add_option("--lsprof", dest="lsprof", metavar="FILE", default=None, \
            help="write lsprof profiling stats to FILE")
        group.add_option("--pidfile", dest="pidfile", metavar="FILE", \
            help="write process ID to FILE")
        group.add_option("-s", "--set", dest="set", action="append", default=[], metavar="NAME=VALUE", \
            help="set/override setting (may be repeated)")
        parser.add_option_group(group)
        
    def process_options(self, args, opts):
        try:
            settings.overrides.update(arglist_to_dict(opts.set))
        except ValueError:
            raise UsageError("Invalid --set value, use --set NAME=VALUE", print_help=False)

        if opts.logfile:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOG_FILE'] = opts.logfile

        if opts.loglevel:
            settings.overrides['LOG_ENABLED'] = True
            settings.overrides['LOG_LEVEL'] = opts.loglevel

        if opts.nolog:
            settings.overrides['LOG_ENABLED'] = False

        if opts.pidfile:
            with open(opts.pidfile, "w") as f:
                f.write(str(os.getpid()) + os.linesep)

    def run(self, args, opts):
        """
        Entry point for running commands
        """
        raise NotImplementedError
