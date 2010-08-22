from scrapy.command import ScrapyCommand
from scrapy.project import crawler
from scrapy.utils.misc import load_object
from scrapy.conf import settings

class Command(ScrapyCommand):

    requires_project = True

    def short_desc(self):
        return "Start Scrapy in server mode"

    def run(self, args, opts):
        queue_class = load_object(settings['SERVICE_QUEUE'])
        crawler.queue = queue_class()
        crawler.start()
