import re
import datetime
import decimal
import json

from twisted.internet import defer

from scrapy.spider import Spider
from scrapy.http import Request, Response
from scrapy.item import BaseItem


class SpiderReferencer(object):
    """Class to serialize (and deserialize) objects (typically dicts)
    containing references to running spiders (ie. Spider objects). This is
    required because json library fails to serialize dicts containing
    non-primitive types as keys, even when you override
    ScrapyJSONEncoder.default() with a custom encoding mechanism.
    """

    spider_ref_re = re.compile('^spider:([0-9a-f]+)?:?(.+)?$')

    def __init__(self, crawler):
        self.crawler = crawler

    def get_reference_from_spider(self, spider):
        return 'spider:%x:%s' % (id(spider), spider.name)

    def get_spider_from_reference(self, ref):
        """Returns the Spider referenced by text, if text is a spider
        reference. Otherwise it returns the text itself. If the text references
        a non-running spider it raises a RuntimeError.
        """
        m = self.spider_ref_re.search(ref)
        if m:
            spid, spname = m.groups()
            for spider in self.crawler.engine.open_spiders:
                if "%x" % id(spider) == spid or spider.name == spname:
                    return spider
            raise RuntimeError("Spider not running: %s" % ref)
        return ref

    def encode_references(self, obj):
        """Look for Spider objects and replace them with spider references"""
        if isinstance(obj, Spider):
            return self.get_reference_from_spider(obj)
        elif isinstance(obj, dict):
            d = {}
            for k, v in obj.items():
                k = self.encode_references(k)
                v = self.encode_references(v)
                d[k] = v
            return d
        elif isinstance(obj, (list, tuple)):
            return [self.encode_references(x) for x in obj]
        else:
            return obj

    def decode_references(self, obj):
        """Look for spider references and replace them with Spider objects"""
        if isinstance(obj, basestring):
            return self.get_spider_from_reference(obj)
        elif isinstance(obj, dict):
            d = {}
            for k, v in obj.items():
                k = self.decode_references(k)
                v = self.decode_references(v)
                d[k] = v
            return d
        elif isinstance(obj, (list, tuple)):
            return [self.decode_references(x) for x in obj]
        else:
            return obj


class ScrapyJSONEncoder(json.JSONEncoder):

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def __init__(self, *a, **kw):
        crawler = kw.pop('crawler', None)
        self.spref = kw.pop('spref', None) or SpiderReferencer(crawler)
        super(ScrapyJSONEncoder, self).__init__(*a, **kw)

    def encode(self, o):
        if self.spref:
            o = self.spref.encode_references(o)
        return super(ScrapyJSONEncoder, self).encode(o)

    def default(self, o):
        if isinstance(o, datetime.datetime):
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

    def __init__(self, *a, **kw):
        crawler = kw.pop('crawler', None)
        self.spref = kw.pop('spref', None) or SpiderReferencer(crawler)
        super(ScrapyJSONDecoder, self).__init__(*a, **kw)

    def decode(self, s):
        o = super(ScrapyJSONDecoder, self).decode(s)
        if self.spref:
            o = self.spref.decode_references(o)
        return o
