from collections import defaultdict
from functools import wraps

from scrapy.command import ScrapyCommand
from scrapy.contracts import ContractsManager
from scrapy.utils.misc import load_object
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.conf import build_component_list


def _generate(cb):
    """ create a callback which does not return anything """
    @wraps(cb)
    def wrapper(response):
        output = cb(response)
        output = list(iterate_spider_output(output))
    return wrapper


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Check spider contracts"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-l", "--list", dest="list", action="store_true",
            help="only list contracts, without checking them")

    def run(self, args, opts):
        # load contracts
        contracts = build_component_list(
            self.settings['SPIDER_CONTRACTS_BASE'],
            self.settings['SPIDER_CONTRACTS'],
        )
        self.conman = ContractsManager([load_object(c) for c in contracts])

        # contract requests
        contract_reqs = defaultdict(list)
        self.crawler.engine.has_capacity = lambda: True

        for spider in args or self.crawler.spiders.list():
            spider = self.crawler.spiders.create(spider)
            requests = self.get_requests(spider)

            if opts.list:
                for req in requests:
                    contract_reqs[spider.name].append(req.callback.__name__)
            else:
                self.crawler.crawl(spider, requests)

        # start checks
        if opts.list:
            for spider, methods in sorted(contract_reqs.iteritems()):
                print spider
                for method in sorted(methods):
                    print '  * %s' % method
        else:
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
