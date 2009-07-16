from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager

class Command(ScrapyCommand):
    def short_desc(self):
        return "Start the Scrapy manager but don't run any spider (idle mode)"

    def run(self, args, opts):
        scrapymanager.start(*args)
