import warnings
from typing import Optional

import scrapy
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.request import request_from_dict  # noqa: F401


warnings.warn(
    ("Module scrapy.utils.reqser is deprecated, please use scrapy.Request.to_dict"
     " and/or scrapy.utils.request.request_from_dict instead"),
    category=ScrapyDeprecationWarning,
    stacklevel=2,
)


def request_to_dict(request: "scrapy.Request", spider: Optional["scrapy.Spider"] = None) -> dict:
    return request.to_dict(spider=spider)
