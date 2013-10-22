from __future__ import print_function
from collections import defaultdict
from functools import wraps
from unittest import TextTestRunner

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
        parser.add_option("-v", "--verbose", dest="verbose", default=1, action="count",
            help="print all contract hooks")

    def run(self, args, opts):
        # load contracts
        contracts = build_component_list(
            self.settings['SPIDER_CONTRACTS_BASE'],
            self.settings['SPIDER_CONTRACTS'],
        )
        self.conman = ContractsManager([load_object(c) for c in contracts])
        self.results = TextTestRunner(verbosity=opts.verbose)._makeResult()

        # contract requests
        contract_reqs = defaultdict(list)

        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        spiders = spman_cls.from_settings(self.settings)

        for spider in args or spiders.list():
            spider = spiders.create(spider)
            requests = self.get_requests(spider)

            if opts.list:
                for req in requests:
                    contract_reqs[spider.name].append(req.callback.__name__)
            elif requests:
                crawler = self.crawler_process.create_crawler(spider.name)
                crawler.crawl(spider, requests)

        # start checks
        if opts.list:
            for spider, methods in sorted(contract_reqs.iteritems()):
                print(spider)
                for method in sorted(methods):
                    print('  * %s' % method)
        else:
            self.crawler_process.start()
            self.results.printErrors()

    def get_requests(self, spider):
        requests = []

        for key, value in vars(type(spider)).items():
            if callable(value) and value.__doc__:
                bound_method = value.__get__(spider, type(spider))
                request = self.conman.from_method(bound_method, self.results)

                if request:
                    request.callback = _generate(request.callback)
                    requests.append(request)

        return requests
