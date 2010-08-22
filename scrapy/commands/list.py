from scrapy.command import ScrapyCommand
from scrapy.project import crawler

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        print "\n".join(crawler.spiders.list())
