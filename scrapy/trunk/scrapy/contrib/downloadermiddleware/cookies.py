from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.core.engine import scrapyengine
from scrapy.utils.misc import dict_updatedefault

class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""

    def __init__(self):
        self.cookies = {}
        dispatcher.connect(self.domain_open, signals.domain_open)
        dispatcher.connect(self.domain_closed, signals.domain_closed)

    def process_request(self, request, spider):
        dict_updatedefault(request.cookies, self.cookies[spider.domain_name])

    def process_response(self, request, response, spider):
        cookies = self.cookies[spider.domain_name]
        cookies.update(request.cookies)
        return response

    def domain_open(self, domain):
        self.cookies[domain] = {}

    def domain_closed(self, domain):
        del self.cookies[domain]
