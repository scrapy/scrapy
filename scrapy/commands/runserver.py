from scrapy.command import ScrapyCommand
from scrapy.conf import settings

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'KEEP_ALIVE': True}

    def short_desc(self):
        return "Start Scrapy in server mode"

    def run(self, args, opts):
        self.crawler.start()
