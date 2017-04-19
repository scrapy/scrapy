import sys
import os

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Edit spider"

    def long_desc(self):
        return "Edit a spider using the editor defined in EDITOR setting"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-e", "--editor", metavar="EDITOR",
                          help="Editor to use for editing spider file")

    def _err(self, msg):
        sys.stderr.write(msg + os.linesep)
        self.exitcode = 1

    def run(self, args, opts):
        if len(args) != 1:
            raise UsageError()

        editor = opts.editor or self.settings['EDITOR']
        try:
            spidercls = self.crawler_process.spider_loader.load(args[0])
        except KeyError:
            return self._err("Spider not found: %s" % args[0])

        sfile = sys.modules[spidercls.__module__].__file__
        sfile = sfile.replace('.pyc', '.py')
        self.exitcode = os.system('%s "%s"' % (editor, sfile))
