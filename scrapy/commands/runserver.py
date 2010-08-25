from scrapy.command import ScrapyCommand
from scrapy.conf import settings

class Command(ScrapyCommand):

    requires_project = True

    def short_desc(self):
        return "Start Scrapy in server mode"

    def process_options(self, args, opts):
        super(Command, self).process_options(args, opts)
        settings.overrides['QUEUE_CLASS'] = settings['SERVER_QUEUE_CLASS']

    def run(self, args, opts):
        self.crawler.start()
