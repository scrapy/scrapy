class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""

    def process_request(self, request, spider):
        if getattr(spider, 'user_agent', None):
            request.headers.setdefault('User-Agent', spider.user_agent)

