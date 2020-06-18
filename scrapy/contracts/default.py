import json

from itemadapter import is_item, ItemAdapter

from scrapy.contracts import Contract
from scrapy.exceptions import ContractFail
from scrapy.http import Request


# contracts
class UrlContract(Contract):
    """ Contract to set the url of the request (mandatory)
        @url http://scrapy.org
    """

    name = 'url'

    def adjust_request_args(self, args):
        args['url'] = self.args[0]
        return args


class CallbackKeywordArgumentsContract(Contract):
    """ Contract to set the keyword arguments for the request.
        The value should be a JSON-encoded dictionary, e.g.:

        @cb_kwargs {"arg1": "some value"}
    """

    name = 'cb_kwargs'

    def adjust_request_args(self, args):
        args['cb_kwargs'] = json.loads(' '.join(self.args))
        return args


class ReturnsContract(Contract):
    """ Contract to check the output of a callback

        general form:
        @returns request(s)/item(s) [min=1 [max]]

        e.g.:
        @returns request
        @returns request 2
        @returns request 2 10
        @returns request 0 10
    """

    name = 'returns'
    object_type_verifiers = {
        'request': lambda x: isinstance(x, Request),
        'requests': lambda x: isinstance(x, Request),
        'item': is_item,
        'items': is_item,
    }

    def __init__(self, *args, **kwargs):
        super(ReturnsContract, self).__init__(*args, **kwargs)

        if len(self.args) not in [1, 2, 3]:
            raise ValueError(
                "Incorrect argument quantity: expected 1, 2 or 3, got %i"
                % len(self.args)
            )
        self.obj_name = self.args[0] or None
        self.obj_type_verifier = self.object_type_verifiers[self.obj_name]

        try:
            self.min_bound = int(self.args[1])
        except IndexError:
            self.min_bound = 1

        try:
            self.max_bound = int(self.args[2])
        except IndexError:
            self.max_bound = float('inf')

    def post_process(self, output):
        occurrences = 0
        for x in output:
            if self.obj_type_verifier(x):
                occurrences += 1

        assertion = (self.min_bound <= occurrences <= self.max_bound)

        if not assertion:
            if self.min_bound == self.max_bound:
                expected = self.min_bound
            else:
                expected = '%s..%s' % (self.min_bound, self.max_bound)

            raise ContractFail("Returned %s %s, expected %s" %
                               (occurrences, self.obj_name, expected))


class ScrapesContract(Contract):
    """ Contract to check presence of fields in scraped items
        @scrapes page_name page_body
    """

    name = 'scrapes'

    def post_process(self, output):
        for x in output:
            if is_item(x):
                missing = [arg for arg in self.args if arg not in ItemAdapter(x)]
                if missing:
                    missing_str = ", ".join(missing)
                    raise ContractFail("Missing fields: %s" % missing_str)
