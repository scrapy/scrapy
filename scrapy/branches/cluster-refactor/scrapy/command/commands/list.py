from scrapy.command import ScrapyCommand
from scrapy.spider import spiders

class Command(ScrapyCommand):
    def syntax(self):
        return ""
    
    def short_desc(self):
        return "List available spiders (both enabled and disabled)"

    def run(self, args, opts):
        spiders_dict = spiders.asdict()
        for n, p in spiders_dict.items():
            disabled = "disabled" if getattr(p, 'disabled', False) else "enabled"
            print "%-30s %-30s %s" % (n, p.__class__.__name__, disabled)
        print "Total spiders: %d" % len(spiders_dict)
