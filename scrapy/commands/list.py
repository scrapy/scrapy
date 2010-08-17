from scrapy.command import ScrapyCommand
from scrapy.spider import spiders

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        print "\n".join(spiders.list())
