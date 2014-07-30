import sys, os

from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "<spider>"

    def short_desc(self):
        return "Edit spider"

    def long_desc(self):
        return "Edit a spider using the editor defined in EDITOR setting"

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('spider', help='spider to edit')

    def _err(self, msg):
        sys.stderr.write(msg + os.linesep)
        self.exitcode = 1

    def run(self, args, opts):
        # --- backwards compatibility for optparse ---
        if isinstance(args, list):
            if len(args) != 1:
                raise UsageError()
            sname = args[0]
        else:
            sname = args.spider

        crawler = self.crawler_process.create_crawler()
        editor = crawler.settings['EDITOR']
        try:
            spider = crawler.spiders.create(sname)
        except KeyError:
            return self._err("Spider not found: %s" % sname)

        sfile = sys.modules[spider.__module__].__file__
        sfile = sfile.replace('.pyc', '.py')
        self.exitcode = os.system('%s "%s"' % (editor, sfile))
