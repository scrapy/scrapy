from __future__ import absolute_import

from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError

class Command(ScrapyCommand):

    requires_project = True

    def short_desc(self):
        return "Start Scrapyd server for this project"

    def long_desc(self):
        return "Start Scrapyd server for this project, which can be referred " \
            "from the JSON API with the name 'default'"

    def run(self, args, opts):
        try:
            from scrapyd.script import execute
            execute()
        except ImportError:
            raise UsageError("Scrapyd is not available in this system")
