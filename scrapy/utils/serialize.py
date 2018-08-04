import json
import datetime
import decimal

from twisted.internet import defer

from scrapy.http import Request, Response
from scrapy.item import BaseItem


class ScrapyJSONEncoder(json.JSONEncoder):

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o):
        if isinstance(o, set):
            return list(o)
        elif isinstance(o, datetime.datetime):
            return o.strftime("%s %s" % (self.DATE_FORMAT, self.TIME_FORMAT))
        elif isinstance(o, datetime.date):
            return o.strftime(self.DATE_FORMAT)
        elif isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        elif isinstance(o, decimal.Decimal):
            return str(o)
        elif isinstance(o, defer.Deferred):
            return str(o)
        elif isinstance(o, BaseItem):
            return dict(o)
        elif isinstance(o, Request):
            return "<%s %s %s>" % (type(o).__name__, o.method, o.url)
        elif isinstance(o, Response):
            return "<%s %s %s>" % (type(o).__name__, o.status, o.url)
        else:
            return super(ScrapyJSONEncoder, self).default(o)


class ScrapyJSONDecoder(json.JSONDecoder):
    pass
