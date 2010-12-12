from scrapy.command import ScrapyCommand
from scrapy.conf import settings

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'KEEP_ALIVE': True}

    def short_desc(self):
        return "Deprecated command. Use 'server' command instead"

    def run(self, args, opts):
        import warnings
        warnings.warn("Scrapy queue command is deprecated - use 'server' command instead.", \
            DeprecationWarning)
        self.crawler.start()
