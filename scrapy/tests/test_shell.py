from twisted.trial import unittest

from scrapy.spider import Spider
from scrapy.shell import Shell
from scrapy.http import Response, TextResponse, XmlResponse, HtmlResponse
from scrapy.utils.test import get_crawler

class ShellTest(unittest.TestCase):

    def setUp(self):
        self.crawler = get_crawler()
        self.spider = Spider('foo')

    def test_inspect_response_html(self):
        response = HtmlResponse(url='http://example.com/', body='''
            <!doctype html>
            <html>
                <p>Testing</p>
            </html>
        ''')
        shell = Shell(self.crawler, code='None')
        shell.start(response=response, spider=self.spider)

        self.assertIn('sel', shell.vars)

    def test_inspect_response_xml(self):
        response = XmlResponse(url='http://example.com/', body='''
            <?xml version="1.0" encoding="UTF-8"?>
            <foo>Testing</foo>
        ''')
        shell = Shell(self.crawler, code='None')
        shell.start(response=response, spider=self.spider)

        self.assertIn('sel', shell.vars)

    def test_inspect_response_text(self):
        response = TextResponse(url='http://example.com/', body='''
            {"hello": "world"}
        ''')
        shell = Shell(self.crawler, code='None')
        shell.start(response=response, spider=self.spider)

        self.assertNotIn('sel', shell.vars)

    def test_inspect_response_binary(self):
        response = Response(url='http://example.com/', body='''
            '{\xcc\xe8\x92\xe6\xb8\xa21\xb2\xe5O6\xc9\x84\xba8
            \xa3\x877\xa8v\xee9p.UJ\xa1m\x8a"H\xb3\xcc\x08\xff
            \x87d\x00i\xce\xb7a\xff\x8c\xd8NX\xae\xc2'
        ''')
        shell = Shell(self.crawler, code='None')
        shell.start(response=response, spider=self.spider)

        self.assertNotIn('sel', shell.vars)

if __name__ == "__main__":
    unittest.main()
