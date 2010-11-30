from twisted.internet import reactor, threads

from scrapy.command import ScrapyCommand
from scrapy.commands import runserver
from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict

class Command(runserver.Command):

    requires_project = True
    default_settings = {'LOG_LEVEL': 'WARNING'}

    def syntax(self):
        return "[options] <list|clear|count|add spider1 ..>"

    def short_desc(self):
        return "Deprecated command. See Scrapyd documentation."

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-a", "--arg", dest="spargs", action="append", default=[], \
            help="set spider argument (may be repeated)")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)

    def run(self, args, opts):
        if len(args) < 1:
            raise UsageError()
        cmd = args[0]

        q = self.crawler.queue._queue

        if cmd == 'add' and len(args) < 2:
            raise UsageError()

        d = threads.deferToThread(self._run_in_thread, args, opts, q, cmd)
        d.addBoth(lambda _: reactor.stop())
        from scrapy import log
        log.start()
        reactor.run()

    def _run_in_thread(self, args, opts, q, cmd):
        if cmd == 'add':
            for x in args[1:]:
                self._call(q.add, x, **opts.spargs)
                print "Added: name=%s args=%s" % (x, opts.spargs)
        elif cmd == 'list':
            x = self._call(q.list)
            print "\n".join(map(str, x))
        elif cmd == 'count':
            print self._call(q.count)
        elif cmd == 'clear':
            self._call(q.clear)
        else:
            raise UsageError()

    def _call(self, f, *a, **kw):
        return threads.blockingCallFromThread(reactor, f, *a, **kw)

