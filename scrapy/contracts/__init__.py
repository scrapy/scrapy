import re
from functools import wraps

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.python import get_spec
from scrapy.exceptions import ContractFail


class ContractsManager(object):
    contracts = {}

    def __init__(self, contracts):
        for contract in contracts:
            self.contracts[contract.name] = contract

    def extract_contracts(self, method):
        contracts = []
        for line in method.__doc__.split('\n'):
            line = line.strip()

            if line.startswith('@'):
                name, args = re.match(r'@(\w+)\s*(.*)', line).groups()
                args = re.split(r'\s+', args)

                contracts.append(self.contracts[name](method, *args))

        return contracts

    def from_method(self, method, fail=False):
        contracts = self.extract_contracts(method)
        if contracts:
            # calculate request args
            args, kwargs = get_spec(Request.__init__)
            kwargs['callback'] = method
            for contract in contracts:
                kwargs = contract.adjust_request_args(kwargs)

            # create and prepare request
            args.remove('self')
            if set(args).issubset(set(kwargs)):
                request = Request(**kwargs)

                # execute pre and post hooks in order
                for contract in reversed(contracts):
                    request = contract.add_pre_hook(request, fail)
                for contract in contracts:
                    request = contract.add_post_hook(request, fail)

                return request


class Contract(object):
    """ Abstract class for contracts """

    def __init__(self, method, *args):
        self.method = method
        self.args = args

    def add_pre_hook(self, request, fail=False):
        cb = request.callback

        @wraps(cb)
        def wrapper(response):
            try:
                self.pre_process(response)
            except ContractFail as e:
                if fail:
                    raise
                else:
                    print e.format(self.method)
            return list(iterate_spider_output(cb(response)))

        request.callback = wrapper
        return request

    def add_post_hook(self, request, fail=False):
        cb = request.callback

        @wraps(cb)
        def wrapper(response):
            output = list(iterate_spider_output(cb(response)))
            try:
                self.post_process(output)
            except ContractFail as e:
                if fail:
                    raise
                else:
                    print e.format(self.method)
            return output

        request.callback = wrapper
        return request

    def adjust_request_args(self, args):
        return args

    def pre_process(self, response):
        pass

    def post_process(self, output):
        pass
