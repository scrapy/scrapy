import datetime
import decimal
import json
import warnings
from typing import Any

from itemadapter import ItemAdapter, is_item
from twisted.internet import defer

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response


class ScrapyJSONEncoder(json.JSONEncoder):
    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o: Any) -> Any:
        if isinstance(o, set):
            return list(o)
        if isinstance(o, datetime.datetime):
            return o.strftime(f"{self.DATE_FORMAT} {self.TIME_FORMAT}")
        if isinstance(o, datetime.date):
            return o.strftime(self.DATE_FORMAT)
        if isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        if isinstance(o, decimal.Decimal):
            return str(o)
        if isinstance(o, defer.Deferred):
            return str(o)
        if isinstance(o, Request):
            return f"<{type(o).__name__} {o.method} {o.url}>"
        if isinstance(o, Response):
            return f"<{type(o).__name__} {o.status} {o.url}>"
        if is_item(o):
            return ItemAdapter(o).asdict()
        return super().default(o)


class ScrapyJSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "The ScrapyJSONDecoder class is deprecated and will be removed in a future version of Scrapy.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
