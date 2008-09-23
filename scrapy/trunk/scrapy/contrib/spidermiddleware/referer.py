"""
RefererMiddleware: populates Request referer field, based on the Response which
originated it.
"""

from scrapy.http import Request

class RefererMiddleware(object):
    def process_result(self, response, result, spider):
        def _set_referer(r):
            if isinstance(r, Request):
                r.headers.setdefault('Referer', response.url)
            return r
        return (_set_referer(r) for r in result or ())

