from scrapy.core.queue import KeepAliveExecutionQueue
from scrapy.command import ScrapyCommand
from scrapy.core.manager import scrapymanager

class Command(ScrapyCommand):

    requires_project = True

    def short_desc(self):
        return "Start the Scrapy manager but don't run any spider (idle mode)"

    def run(self, args, opts):
        q = KeepAliveExecutionQueue()
        scrapymanager.queue = q
        scrapymanager.start()
