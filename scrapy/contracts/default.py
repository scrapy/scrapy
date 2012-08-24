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
        @returns items, 1
        @returns requests, 1+
    """

    name = 'returns'
    objects = {
        'requests': Request,
        'items': BaseItem,
    }

    def __init__(self, *args, **kwargs):
        super(ReturnsContract, self).__init__(*args, **kwargs)

        if len(self.args) != 2:
            raise ContractError("Returns Contract must have two arguments")
        self.obj_name, self.raw_num = self.args

        # validate input
        self.obj_type = self.objects[self.obj_name]

        self.modifier = self.raw_num[-1]
        if self.modifier in ['+', '-']:
            self.num = int(self.raw_num[:-1])
        else:
            self.num = int(self.raw_num)
            self.modifier = None

    def post_process(self, output):
        occurences = 0
        for x in output:
            if isinstance(x, self.obj_type):
                occurences += 1

        if self.modifier == '+':
            assertion = (occurences >= self.num)
        elif self.modifier == '-':
            assertion = (occurences <= self.num)
        else:
            assertion = (occurences == self.num)

        if not assertion:
            raise ContractFail("Returned %s %s, expected %s" % \
                (occurences, self.obj_name, self.raw_num))

class ScrapesContract(Contract):
    """ Contract to check presence of fields in scraped items
        @scrapes page_name, page_body
    """
    name = 'scrapes'

    def post_process(self, output):
        for x in output:
            if isinstance(x, BaseItem):
                for arg in self.args:
                    if not arg in x:
                        raise ContractFail('%r field is missing' % arg)
