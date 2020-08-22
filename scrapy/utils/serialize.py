import json
import datetime
import decimal

from itemadapter import is_item, ItemAdapter
from twisted.internet import defer

from scrapy.http import Request, Response


class ScrapyJSONEncoder(json.JSONEncoder):

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o):
        if isinstance(o, set):
            return list(o)
        elif isinstance(o, datetime.datetime):
            return o.strftime(f"{self.DATE_FORMAT} {self.TIME_FORMAT}")
        elif isinstance(o, datetime.date):
            return o.strftime(self.DATE_FORMAT)
        elif isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        elif isinstance(o, decimal.Decimal):
            return str(o)
        elif isinstance(o, defer.Deferred):
            return str(o)
        elif is_item(o):
            return ItemAdapter(o).asdict()
        elif isinstance(o, Request):
            return f"<{type(o).__name__} {o.method} {o.url}>"
        elif isinstance(o, Response):
            return f"<{type(o).__name__} {o.status} {o.url}>"
        else:
            return super().default(o)


class ScrapyJSONDecoder(json.JSONDecoder):
    pass
