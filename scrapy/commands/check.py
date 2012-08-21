from functools import wraps

from scrapy.command import ScrapyCommand
from scrapy.http import Request

from scrapy.contracts import Contract

class Command(ScrapyCommand):
    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Check contracts for given spider"

    def run(self, args, opts):
        self.crawler.engine.has_capacity = lambda: True

        for spider in args or self.crawler.spiders.list():
            spider = self.crawler.spiders.create(spider)
            requests = self.get_requests(spider)
            self.crawler.crawl(spider, requests)

        self.crawler.start()

    def get_requests(self, spider):
        requests = []

        for key, value in vars(type(spider)).iteritems():
            if callable(value) and value.__doc__:
                bound_method = value.__get__(spider, type(spider))
                request = Request(url='http://scrapy.org', callback=bound_method)

                # register contract hooks to the request
                contracts = Contract.from_method(value)
                for contract in contracts:
                    request = contract.prepare_request(request)

                # discard anything the request might return
                cb = request.callback
                @wraps(cb)
                def wrapper(response):
                    cb(response)

                request.callback = wrapper

                requests.append(request)

        return requests
