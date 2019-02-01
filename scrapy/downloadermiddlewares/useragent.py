"""Set User-Agent header per spider or use a default value from settings"""

from scrapy import signals


class UserAgentMiddleware(object):
    """Middleware that allows spiders to override the default user agent.

    In order for a spider to override the default user agent, its `user_agent`
    attribute must be set.
    """

    def __init__(self, user_agent='Scrapy'):
        self.user_agent = user_agent

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings['USER_AGENT'])
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        self.user_agent = getattr(spider, 'user_agent', self.user_agent)

    def process_request(self, request, spider):
        if self.user_agent:
            request.headers.setdefault(b'User-Agent', self.user_agent)
