import re
import inspect
from functools import wraps

from scrapy.http import Request
from scrapy.utils.spider import iterate_spider_output
from scrapy.utils.misc import get_spec
from scrapy.exceptions import ContractFail

class ContractsManager(object):
    registered = {}

    def register(self, contract):
        self.registered[contract.name] = contract

    def extract_contracts(self, method):
        contracts = []
        for line in method.__doc__.split('\n'):
            line = line.strip()

            if line.startswith('@'):
                name, args = re.match(r'@(\w+)\s*(.*)', line).groups()
                args = re.split(r'\s*\,\s*', args)

                contracts.append(self.registered[name](method, *args))

        return contracts

    def from_method(self, method):
        contracts = self.extract_contracts(method)
        if contracts:
            # calculate request args
            args = get_spec(Request.__init__)[1]
            args['callback'] = method
            for contract in contracts:
                args = contract.adjust_request_args(args)

            # create and prepare request
            assert 'url' in args, "Method '%s' does not have an url contract" % method.__name__
            request = Request(**args)
            for contract in contracts:
                request = contract.prepare_request(request)

            return request

class Contract(object):
    """ Abstract class for contracts """

    def __init__(self, method, *args):
        self.method = method
        self.args = args

    def prepare_request(self, request):
        cb = request.callback
        @wraps(cb)
        def wrapper(response):
            self.pre_process(response)
            output = list(iterate_spider_output(cb(response)))
            self.post_process(output)
            return output

        request.callback = wrapper
        request = self.modify_request(request)
        return request

    def adjust_request_args(self, args):
        return args

    def modify_request(self, request):
        return request

    def pre_process(self, response):
        pass

    def post_process(self, output):
        pass
