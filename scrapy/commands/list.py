from __future__ import print_function
from scrapy.command import ScrapyCommand

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        for s in sorted(self.crawler_process.spiders.list()):
            print(s)
