"""
HttpError Spider Middleware

See documentation in docs/ref/spider-middleware.rst
"""

class HttpErrorMiddleware(object):

    def process_spider_input(self, response, spider):
        if not (200 <= response.status < 300 or \
                response.status in getattr(spider, 'handle_httpstatus_list', [])):
            return []
