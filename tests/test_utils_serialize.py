import unittest
import datetime
import json
from decimal import Decimal

from twisted.internet import defer

from scrapy.utils.serialize import SpiderReferencer, ScrapyJSONEncoder, ScrapyJSONDecoder
from scrapy.spider import Spider
from scrapy.http import Request, Response


class _EngineMock(object):
    def __init__(self, open_spiders):
        self.open_spiders = open_spiders

class CrawlerMock(object):
    def __init__(self, open_spiders):
        self.engine = _EngineMock(open_spiders)

class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.spider1 = Spider('name1')
        self.spider2 = Spider('name2')
        open_spiders = set([self.spider1, self.spider2])
        crawler = CrawlerMock(open_spiders)
        self.spref = SpiderReferencer(crawler)
        self.encoder = ScrapyJSONEncoder(spref=self.spref)
        self.decoder = ScrapyJSONDecoder(spref=self.spref)

class SpiderReferencerTestCase(BaseTestCase):

    def test_spiders_and_references(self):
        ref1 = self.spref.get_reference_from_spider(self.spider1)
        assert isinstance(ref1, str)
        assert self.spider1.name in ref1
        ref2 = self.spref.get_reference_from_spider(self.spider2)
        ref1_ = self.spref.get_reference_from_spider(self.spider1)
        assert ref1 == ref1_
        assert ref1 != ref2

        sp1 = self.spref.get_spider_from_reference(ref1)
        sp2 = self.spref.get_spider_from_reference(ref2)
        sp1_ = self.spref.get_spider_from_reference(ref1)
        assert isinstance(sp1, Spider)
        assert sp1 is not sp2
        assert sp1 is sp1_

        # referring to spiders by name
        assert sp1 is self.spref.get_spider_from_reference('spider::name1')
        assert sp2 is self.spref.get_spider_from_reference('spider::name2')

        # must return string as-is if spider id not found
        assert 'lala' == self.spref.get_spider_from_reference('lala')
        # must raise RuntimeError if spider id is not found and spider is not running
        self.assertRaises(RuntimeError, self.spref.get_spider_from_reference, 'spider:fffffff')

    def test_encode_decode(self):
        sr = self.spref
        sp1 = self.spider1
        sp2 = self.spider2
        ref1 = sr.get_reference_from_spider(sp1)
        ref2 = sr.get_reference_from_spider(sp2)

        examples = [
            ('lala', 'lala'),
            (sp1, ref1),
            (['lala', sp1], ['lala', ref1]),
            ({'lala': sp1}, {'lala': ref1}),
            ({sp1: sp2}, {ref1: ref2}),
            ({sp1: {sp2: ['lala', sp1]}}, {ref1: {ref2: ['lala', ref1]}})
        ]
        for spiders, refs in examples:
            self.assertEqual(sr.encode_references(spiders), refs)
            self.assertEqual(sr.decode_references(refs), spiders)

class JsonEncoderTestCase(BaseTestCase):
    
    def test_encode_decode(self):
        sr = self.spref
        sp1 = self.spider1
        sp2 = self.spider2
        ref1 = sr.get_reference_from_spider(sp1)
        ref2 = sr.get_reference_from_spider(sp2)
        dt = datetime.datetime(2010, 1, 2, 10, 11, 12)
        dts = "2010-01-02 10:11:12"
        d = datetime.date(2010, 1, 2)
        ds = "2010-01-02"
        t = datetime.time(10, 11, 12)
        ts = "10:11:12"
        dec = Decimal("1000.12")
        decs = "1000.12"

        examples_encode_decode = [
            ('lala', 'lala'),
            (sp1, ref1),
            (['lala', sp1], ['lala', ref1]),
            ({'lala': sp1}, {'lala': ref1}),
            ({sp1: sp2}, {ref1: ref2}),
            ({sp1: {sp2: ['lala', sp1]}}, {ref1: {ref2: ['lala', ref1]}})
        ]
        for spiders, refs in examples_encode_decode:
            self.assertEqual(self.encoder.encode(spiders), json.dumps(refs))
            self.assertEqual(self.decoder.decode(json.dumps(refs)), spiders)

        examples_encode_only = [
            ({sp1: dt}, {ref1: dts}),
            ({sp1: d}, {ref1: ds}),
            ({sp1: t}, {ref1: ts}),
            ({sp1: dec}, {ref1: decs}),
        ]
        for spiders, refs in examples_encode_only:
            self.assertEqual(self.encoder.encode(spiders), json.dumps(refs))

        assert 'Deferred' in self.encoder.encode(defer.Deferred())

    def test_encode_request(self):
        r = Request("http://www.example.com/lala")
        rs = self.encoder.encode(r)
        assert r.method in rs
        assert r.url in rs

    def test_encode_response(self):
        r = Response("http://www.example.com/lala")
        rs = self.encoder.encode(r)
        assert r.url in rs
        assert str(r.status) in rs


if __name__ == "__main__":
    unittest.main()

