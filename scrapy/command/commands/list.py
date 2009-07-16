from scrapy.command import ScrapyCommand
from scrapy.spider import spiders

class Command(ScrapyCommand):
    def syntax(self):
        return ""
    
    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        print "\n".join(spiders.asdict().keys())
