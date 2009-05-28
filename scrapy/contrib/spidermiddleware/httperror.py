

class HttpErrorMiddleware(object):
    """Filter out response outside of a range of valid status codes

    This middleware filters out every response with status outside of the range 200<=status<300
    Spiders can add more exceptions using `handle_httpstatus_list` spider attribute.
    """

    def process_spider_input(self, response, spider):
        if not (200 <= response.status < 300 or \
                response.status in getattr(spider, 'handle_httpstatus_list', [])):
            return [] # skip response
