"""Set User-Agent header per spider or use a default value from settings"""


class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""

    def __init__(self, user_agent='Scrapy'):
        self.user_agent = user_agent

    @classmethod
    def from_settings(cls, settings):
        return cls(settings['USER_AGENT'])

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_request(self, request, spider):
        user_agent = getattr(spider, 'user_agent', self.user_agent)
        if user_agent:
            request.headers.setdefault('User-Agent', user_agent)
