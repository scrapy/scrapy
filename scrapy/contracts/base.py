import re
from functools import wraps

from scrapy.utils.spider import iterate_spider_output

class ContractType(type):
    """ Metaclass for contracts
        - automatically registers contracts in the root `Contract` class
    """

    def __new__(meta, name, bases, dct):
        # only allow single inheritence
        assert len(bases) == 1, 'Multiple inheritance is not allowed'
        base = bases[0]

        # ascend in inheritence chain
        while type(base) not in [type, meta]:
            base = type(base)

        # register this as a valid contract
        cls = type.__new__(meta, name, bases, dct)
        if type(base) != type:
            base.registered[cls.name] = cls
        return cls


class Contract(object):
    """ Abstract class for contracts
        - keeps a reference of all derived classes in `registered`
    """

    __metaclass__ = ContractType
    registered = {}

    def __init__(self, method, *args):
        self.method = method
        self.args = args

    @classmethod
    def from_method(cls, method):
        contracts = []
        for line in method.__doc__.split('\n'):
            line = line.strip()

            if line.startswith('@'):
                name, args = re.match(r'@(\w+)\s*(.*)', line).groups()
                args = re.split(r'[\,\s+]', args)
                args = filter(lambda x:x, args)

                contracts.append(cls.registered[name](method, *args))

        return contracts

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

    def modify_request(self, request):
        return request

    def pre_process(self, response):
        pass

    def post_process(self, output):
        pass
