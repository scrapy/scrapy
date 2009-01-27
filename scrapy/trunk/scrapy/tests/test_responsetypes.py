import unittest
from scrapy.core.downloader.responsetypes import responsetypes

from scrapy.http import Response, TextResponse, XmlResponse, HtmlResponse, Headers

class ResponseTypesTest(unittest.TestCase):

    def test_from_filename(self):
        mappings = [
            ('data.bin', Response),
            ('file.txt', TextResponse),
            ('file.xml.gz', Response),
            ('file.xml', XmlResponse),
            ('file.html', HtmlResponse),
            ('file.unknownext', Response),
        ]
        for source, cls in mappings:
            retcls = responsetypes.from_filename(source)
            assert retcls is cls, "%s ==> %s != %s" % (source, retcls, cls)

    def test_from_content_disposition(self):
        mappings = [
            ('attachment; filename="data.xml"', XmlResponse),
            ('attachment; filename=data.xml', XmlResponse),
        ]
        for source, cls in mappings:
            retcls = responsetypes.from_content_disposition(source)
            assert retcls is cls, "%s ==> %s != %s" % (source, retcls, cls)

    def test_from_content_type(self):
        mappings = [
            ('text/html; charset=UTF-8', HtmlResponse),
            ('text/xml; charset=UTF-8', XmlResponse),
            ('application/xml; charset=UTF-8', XmlResponse),
            ('application/octet-stream', Response),
        ]
        for source, cls in mappings:
            retcls = responsetypes.from_content_type(source)
            assert retcls is cls, "%s ==> %s != %s" % (source, retcls, cls)

    def test_from_body(self):
        mappings = [
            ('\x03\x02\xdf\xdd\x23', Response),
            ('Some plain text\ndata with tabs\t and null bytes\0', TextResponse),
            ('<html><head><title>Hello</title></head>', HtmlResponse),
            ('<?xml version="1.0" encoding="utf-8"', XmlResponse),
        ]
        for source, cls in mappings:
            retcls = responsetypes.from_body(source)
            assert retcls is cls, "%s ==> %s != %s" % (source, retcls, cls)
        
    def test_from_headers(self):
        mappings = [
            ({'Content-Type': ['text/html; charset=utf-8']}, HtmlResponse),
            ({'Content-Type': ['application/octet-stream'], 'Content-Disposition': ['attachment; filename=data.txt']}, TextResponse),
        ]
        for source, cls in mappings:
            source = Headers(source)
            retcls = responsetypes.from_headers(source)
            assert retcls is cls, "%s ==> %s != %s" % (source, retcls, cls)

if __name__ == "__main__":
    unittest.main()
