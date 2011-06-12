from scrapy.command import ScrapyCommand
from scrapy.utils.misc import load_object
from scrapy.conf import settings

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        spman_cls = load_object(settings['SPIDER_MANAGER_CLASS'])
        spiders = spman_cls.from_settings(settings)
        for s in spiders.list():
            print s
