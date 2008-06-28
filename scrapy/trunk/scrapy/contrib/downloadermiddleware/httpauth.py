class HttpAuthMiddleware(object):
    """This middleware allows spiders to use HTTP auth in a cleaner way
    (http_user and http_pass spider class attributes)"""

    def process_request(self, request, spider):
        if getattr(spider, 'http_user', None) or getattr(spider, 'http_pass', None):
            request.httpauth(spider.http_user, spider.http_pass)

