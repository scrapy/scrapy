import hashlib
import unittest

from scrapy.dupefilter import RFPDupeFilter
from scrapy.http import Request


class RFPDupeFilterTest(unittest.TestCase):

    def test_filter(self):
        dupefilter = RFPDupeFilter()
        dupefilter.open()

        r1 = Request('http://scrapytest.org/1')
        r2 = Request('http://scrapytest.org/2')
        r3 = Request('http://scrapytest.org/2')

        assert not dupefilter.request_seen(r1)
        assert dupefilter.request_seen(r1)

        assert not dupefilter.request_seen(r2)
        assert dupefilter.request_seen(r3)

        dupefilter.close('finished')

    def test_request_fingerprint(self):
        """Test if customization of request_fingerprint method will change
        output of request_seen.

        """
        r1 = Request('http://scrapytest.org/index.html')
        r2 = Request('http://scrapytest.org/INDEX.html')

        dupefilter = RFPDupeFilter()
        dupefilter.open()

        assert not dupefilter.request_seen(r1)
        assert not dupefilter.request_seen(r2)

        dupefilter.close('finished')

        class CaseInsensitiveRFPDupeFilter(RFPDupeFilter):

            def request_fingerprint(self, request):
                fp = hashlib.sha1()
                fp.update(request.url.lower())
                return fp.hexdigest()

        case_insensitive_dupefilter = CaseInsensitiveRFPDupeFilter()
        case_insensitive_dupefilter.open()

        assert not case_insensitive_dupefilter.request_seen(r1)
        assert case_insensitive_dupefilter.request_seen(r2)

        case_insensitive_dupefilter.close('finished')
