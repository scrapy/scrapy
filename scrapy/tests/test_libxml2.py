import unittest

import libxml2

from scrapy.http import TextResponse
from scrapy.utils.test import libxml2debug

class Libxml2Test(unittest.TestCase):

    @libxml2debug
    def test_xpath(self):
        #this test will fail in version 2.6.27 but passes on 2.6.29+
        html = "<td>1<b>2</b>3</td>"
        node = libxml2.htmlParseDoc(html, 'utf-8')
        result = [str(r) for r in node.xpathEval('//text()')]
        self.assertEquals(result, ['1', '2', '3'])
        node.freeDoc()

class ResponseLibxml2DocTest(unittest.TestCase):

    @libxml2debug
    def test_getlibxml2doc(self):
        # test to simulate '\x00' char in body of html page
        #this method shouldn't raise TypeError Exception

        # make sure we load the libxml2 extension
        from scrapy.extension import extensions
        extensions.load() # 

        self.body_content = 'test problematic \x00 body'
        response = TextResponse('http://example.com/catalog/product/blabla-123',
                            headers={'Content-Type': 'text/plain; charset=utf-8'}, body=self.body_content)
        response.getlibxml2doc()

if __name__ == "__main__":
    unittest.main()
