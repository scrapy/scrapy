"""
HttpError Spider Middleware

See documentation in docs/ref/spider-middleware.rst
"""

class HttpErrorMiddleware(object):

    def process_spider_input(self, response, spider):
        if 200 <= response.status < 300: # common case
            return
        if 'handle_httpstatus_list' in response.request.meta:
            allowed_statuses = response.request.meta['handle_httpstatus_list']
        else:
            allowed_statuses = getattr(spider, 'handle_httpstatus_list', ())
        if response.status in allowed_statuses:
            return
        return []
