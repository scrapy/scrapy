import warnings
from typing import Optional

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.request import request_from_dict as _from_dict


warnings.warn(
    ("Module scrapy.utils.reqser is deprecated, please use request.to_dict method"
     " and/or scrapy.utils.request.request_from_dict instead"),
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)


def request_to_dict(request: "scrapy.Request", spider: Optional["scrapy.Spider"] = None) -> dict:
    return request.to_dict(spider=spider)


def request_from_dict(d: dict, spider: Optional["scrapy.Spider"] = None) -> "scrapy.Request":
    return _from_dict(d, spider=spider)
