import datetime
import decimal
import json
from typing import Any

from itemadapter import ItemAdapter, is_item
from twisted.internet import defer

from scrapy.http import Request, Response


class ScrapyJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, set):
            return list(o)
        if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
            return o.isoformat()
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
