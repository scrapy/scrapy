from scrapy.item import BaseItem
from scrapy.http import Request
from scrapy.exceptions import ContractFail

from . import Contract


# contracts
class UrlContract(Contract):
    """ Contract to set the url of the request (mandatory)
        @url http://scrapy.org
    """

    name = 'url'

    def adjust_request_args(self, args):
        args['url'] = self.args[0]
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
    objects = {
        'request': Request,
        'requests': Request,
        'item': BaseItem,
        'items': BaseItem,
    }

    def __init__(self, *args, **kwargs):
        super(ReturnsContract, self).__init__(*args, **kwargs)

        assert len(self.args) in [1, 2, 3]
        self.obj_name = self.args[0] or None
        self.obj_type = self.objects[self.obj_name]

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
            if isinstance(x, self.obj_type):
                occurrences += 1

        assertion = (self.min_bound <= occurrences <= self.max_bound)

        if not assertion:
            if self.min_bound == self.max_bound:
                expected = self.min_bound
            else:
                expected = '%s..%s' % (self.min_bound, self.max_bound)

            raise ContractFail("Returned %s %s, expected %s" % \
                (occurrences, self.obj_name, expected))


class ScrapesContract(Contract):
    """ Contract to check presence of fields in scraped items
        @scrapes page_name page_body
    """

    name = 'scrapes'

    def post_process(self, output):
        for x in output:
            if isinstance(x, BaseItem):
                missing = [arg for arg in self.args if arg not in x]
                if missing:
                    raise ContractFail("'%s' field is missing" % " ".join(missing))
