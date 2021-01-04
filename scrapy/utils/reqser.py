import warnings

from scrapy.http.request import Request
from scrapy.exceptions import ScrapyDeprecationWarning


warnings.warn(
    ("Module `scrapy.utils.reqser` is deprecated, please use `scrapy.http.Request.from_dict` "
     "and/or `scrapy.http.Request.to_dict` instead."),
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)


def request_to_dict(request, spider=None):
    return request.to_dict(spider)


def request_from_dict(d, spider=None):
    return Request.from_dict(d, spider)
