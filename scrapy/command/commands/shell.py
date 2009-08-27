"""
Scrapy Shell

See documentation in docs/topics/shell.rst
"""

from scrapy.command import ScrapyCommand
from scrapy.shell import Shell

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "[url]"

    def short_desc(self):
        return "Interactive scraping console"

    def long_desc(self):
        return "Interactive console for scraping the given url. For scraping " \
            "local files you can use a URL like file://path/to/file.html"

    def update_vars(self, vars):
        """You can use this function to update the Scrapy objects that will be
        available in the shell
        """
        pass

    def run(self, args, opts):
        url = args[0] if args else None
        shell = Shell(self.update_vars)
        shell.start(url)
