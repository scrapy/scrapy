"""
htmlpage.py tests
"""
import os
from gzip import GzipFile
from unittest import TestCase

from scrapy.utils.py26 import json
from scrapy.tests.test_contrib_ibl import path
from scrapy.contrib.ibl.htmlpage import parse_html, HtmlTag, HtmlDataFragment
from scrapy.tests.test_contrib_ibl.test_htmlpage_data import *

SAMPLES_FILE = "samples_htmlpage.json.gz"

def _encode_element(el):
    """
    jsonize parse element
    """
    if isinstance(el, HtmlTag):
        return {"tag": el.tag, "attributes": el.attributes,
            "start": el.start, "end": el.end, "tag_type": el.tag_type}
    if isinstance(el, HtmlDataFragment):
        return {"start": el.start, "end": el.end}
    raise TypeError

def _decode_element(dct):
    """
    dejsonize parse element
    """
    if "tag" in dct:
        return HtmlTag(dct["tag_type"], dct["tag"], \
            dct["attributes"], dct["start"], dct["end"])
    if "start" in dct:
        return HtmlDataFragment(dct["start"], dct["end"])
    return dct

def add_sample(source):
    """
    Method for adding samples to test samples file
    (use from console)
    """
    samples = []
    if os.path.exists(SAMPLES_FILE):
        for line in GzipFile(os.path.join(path, SAMPLES_FILE), "r").readlines():
            samples.append(json.loads(line))
    
    new_sample = {"source": source}
    new_sample["parsed"] = list(parse_html(source))
    samples.append(new_sample)
    samples_file = GzipFile(os.path.join(path, SAMPLES_FILE), "wb")
    for sample in samples:
        samples_file.write(json.dumps(sample, default=_encode_element) + "\n")
    samples_file.close()

class TestParseHtml(TestCase):
    """Test for parse_html"""
    def _test_sample(self, sample):
        source = sample["source"]
        expected_parsed = sample["parsed"]
        parsed = parse_html(source)
        count_element = 0
        count_expected = 0
        for element in parsed:
            if type(element) == HtmlTag:
                count_element += 1
            expected = expected_parsed.pop(0)
            if type(expected) == HtmlTag:
                count_expected += 1
            element_text = source[element.start:element.end]
            expected_text = source[expected.start:expected.end]
            if element.start != expected.start or element.end != expected.end:
                assert False, "[%s,%s] %s != [%s,%s] %s" % (element.start, \
                    element.end, element_text, expected.start, \
                    expected.end, expected_text)
            if type(element) != type(expected):
                assert False, "(%s) %s != (%s) %s for text\n%s" % (count_element, \
                    repr(type(element)), count_expected, repr(type(expected)), element_text)
            if type(element) == HtmlTag:
                self.assertEqual(element.tag, expected.tag)
                self.assertEqual(element.attributes, expected.attributes)

    def test_parse(self):
        """simple parse_html test"""
        parsed = [_decode_element(d) for d in PARSED]
        sample = {"source": PAGE, "parsed": parsed}
        self._test_sample(sample)
        
    def test_site_samples(self):
        """test parse_html from real cases"""
        samples = []
        for line in GzipFile(os.path.join(path, SAMPLES_FILE), "r").readlines():
            samples.append(json.loads(line, object_hook=_decode_element))
        for sample in samples:
            self._test_sample(sample)
    
    def test_bad(self):
        """test parsing of bad html layout"""
        parsed = [_decode_element(d) for d in PARSED2]
        sample = {"source": PAGE2, "parsed": parsed}
        self._test_sample(sample)

    def test_comments(self):
        """test parsing of tags inside comments"""
        parsed = [_decode_element(d) for d in PARSED3]
        sample = {"source": PAGE3, "parsed": parsed}
        self._test_sample(sample)

    def test_script_text(self):
        """test parsing of tags inside scripts"""
        parsed = [_decode_element(d) for d in PARSED4]
        sample = {"source": PAGE4, "parsed": parsed}
        self._test_sample(sample)
        
    def test_sucessive(self):
        """test parsing of sucesive cleaned elements"""
        parsed = [_decode_element(d) for d in PARSED5]
        sample = {"source": PAGE5, "parsed": parsed}
        self._test_sample(sample)
        
    def test_sucessive2(self):
        """test parsing of sucesive cleaned elements (variant 2)"""
        parsed = [_decode_element(d) for d in PARSED6]
        sample = {"source": PAGE6, "parsed": parsed}
        self._test_sample(sample)
    
    def test_special_cases(self):
        """some special cases tests"""
        parsed = list(parse_html("<meta http-equiv='Pragma' content='no-cache' />"))
        self.assertEqual(parsed[0].attributes, {'content': 'no-cache', 'http-equiv': 'Pragma'})
        parsed = list(parse_html("<html xmlns='http://www.w3.org/1999/xhtml' xml:lang='en' lang='en'>"))
        self.assertEqual(parsed[0].attributes, {'xmlns': 'http://www.w3.org/1999/xhtml', 'xml:lang': 'en', 'lang': 'en'})
        parsed = list(parse_html("<IMG SRC='http://images.play.com/banners/SAM550a.jpg' align='left' / hspace=5>"))
        self.assertEqual(parsed[0].attributes, {'src': 'http://images.play.com/banners/SAM550a.jpg', \
                                                'align': 'left', 'hspace': '5', '/': None})
