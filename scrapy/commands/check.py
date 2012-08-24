from functools import wraps

from scrapy.conf import settings
from scrapy.command import ScrapyCommand
from scrapy.http import Request
from scrapy.contracts import ContractsManager
from scrapy.utils import display
from scrapy.utils.misc import load_object
from scrapy.utils.spider import iterate_spider_output

def _generate(cb):
    """ create a callback which does not return anything """
    @wraps(cb)
    def wrapper(response):
        output = cb(response)
        output = list(iterate_spider_output(output))
        # display.pprint(output)
    return wrapper

class Command(ScrapyCommand):
    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Check contracts for given spider"

    def run(self, args, opts):
        self.conman = ContractsManager()

        # load contracts
        contracts = settings['SPIDER_CONTRACTS_BASE'] + \
                settings['SPIDER_CONTRACTS']

        for contract in contracts:
            concls = load_object(contract)
            self.conman.register(concls)

        # schedule requests
        self.crawler.engine.has_capacity = lambda: True

        for spider in args or self.crawler.spiders.list():
            spider = self.crawler.spiders.create(spider)
            requests = self.get_requests(spider)
            self.crawler.crawl(spider, requests)

        # start checks
        self.crawler.start()

    def get_requests(self, spider):
        requests = []

        for key, value in vars(type(spider)).items():
            if callable(value) and value.__doc__:
                bound_method = value.__get__(spider, type(spider))
                request = self.conman.from_method(bound_method)

                if request:
                    request.callback = _generate(request.callback)
                    requests.append(request)

        return requests
