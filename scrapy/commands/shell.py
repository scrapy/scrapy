"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from scrapy.command import ScrapyCommand
from scrapy.shell import Shell

class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'QUEUE_CLASS': 'scrapy.queue.KeepAliveExecutionQueue'}

    def syntax(self):
        return "[url|file]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url"

    def update_vars(self, vars):
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """
        pass

    def run(self, args, opts):
        url = args[0] if args else None
        shell = Shell(self.crawler, update_vars=self.update_vars, inthread=True)
        shell.start(url=url).addBoth(lambda _: self.crawler.stop())
        self.crawler.start()
