from scrapy.item import BaseItem

from .base import Contract


# contracts
class UrlContract(Contract):
    name = 'url'

    def modify_request(self, request):
        return request.replace(url=self.args[0])

class ReturnsRequestContract(Contract):
    name = 'returns_request'

class ScrapesContract(Contract):
    name = 'scrapes'

    def post_process(self, output):
        for x in output:
            if isinstance(x, BaseItem):
                for arg in self.args:
                    assert arg in x, '%r field is missing' % arg
