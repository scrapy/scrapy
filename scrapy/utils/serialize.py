import datetime
import decimal
import json

from itemadapter import ItemAdapter, is_item
from twisted.internet import defer

from scrapy.http import Request, Response


class ScrapyJSONEncoder(json.JSONEncoder):

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o):
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
        if is_item(o):
            return ItemAdapter(o).asdict()
        if isinstance(o, Request):
            return f"<{type(o).__name__} {o.method} {o.url}>"
        if isinstance(o, Response):
            return f"<{type(o).__name__} {o.status} {o.url}>"
        return super().default(o)


class ScrapyJSONDecoder(json.JSONDecoder):
    pass
