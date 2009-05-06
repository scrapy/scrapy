from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager


class Command(ScrapyCommand):
    def syntax(self):
        return "[options]"

    def short_desc(self):
        return "Start the Scrapy server"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)

    def run(self, args, opts):
        scrapymanager.start(*args, **opts.__dict__)
