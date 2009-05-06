from scrapy.contrib.spiders import CrawlSpider, Rule
from scrapy.link.extractors import RegexLinkExtractor

class GenericSpider(CrawlSpider):
    """
    This generic crawler crawls an entire site. It can also be used as a default crawler
    (see setting "DEFAULT_SPIDER")
    """
    
    def __init__(self, domain_name):
        self.domain_name = domain_name
        self.rules = (
            Rule(RegexLinkExtractor(allow_domains=(domain_name,)), self.parse_note, follow=True),
        )
        super(GenericSpider, self).__init__()
        
    def parse_note(self, response):
        pass

# not a singleton