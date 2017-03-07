from __future__ import print_function
from scrapy.commands import ScrapyCommand

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False,
                        'SPIDER_LOADER_WARN_ONLY': True}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        for s in sorted(self.crawler_process.spider_loader.list()):
            print(s)
