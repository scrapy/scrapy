from scrapy.command import ScrapyCommand
from scrapy.commands import runserver
from scrapy.exceptions import UsageError
from scrapy.conf import settings

class Command(runserver.Command):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options] <list|clear|add spider1 ..>"

    def short_desc(self):
        return "Control execution queue"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--priority", dest="priority", type="float", default=0.0, \
            help="priority to use for adding spiders")
        parser.add_option("-a", "--arg", dest="spargs", action="append", default=[], \
            help="spider arguments to use for adding spiders")

    def run(self, args, opts):
        if len(args) < 1:
            raise UsageError()
        cmd = args[0]

        botname = settings['BOT_NAME']
        queue = self.crawler.queue.queue

        if cmd == 'add':
            if len(args) < 2:
                raise UsageError()
            msg = dict(x for x in [x.split('=', 1) for x in opts.spargs])
            for x in args[1:]:
                msg.update(name=x)
                queue.put(msg)
                print "Added (priority=%s): %s" % (opts.priority, msg)
        elif cmd == 'list':
            for x, y in queue:
                print "(priority=%s) %s" % (y, x)
        elif cmd == 'clear':
            queue.clear()
            print "Cleared %s queue" % botname
        else:
            raise UsageError()
