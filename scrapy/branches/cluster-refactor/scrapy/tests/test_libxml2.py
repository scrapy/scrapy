from unittest import TestCase, main
import libxml2
from scrapy.http import ResponseBody,  Response

class Libxml2Test(TestCase):
    def setUp(self):
        libxml2.debugMemory(1)

    def tearDown(self):
        libxml2.cleanupParser()
        leaked_bytes = libxml2.debugMemory(0)
        assert leaked_bytes == 0, "libxml2 memory leak detected: %d bytes" % leaked_bytes

    def test_xpath(self):
        #this test will fail in version 2.6.27 but passes on 2.6.29+
        html = "<td>1<b>2</b>3</td>"
        node = libxml2.htmlParseDoc(html, 'utf-8')
        result = [str(r) for r in node.xpathEval('//text()')]
        self.assertEquals(result, ['1', '2', '3'])
        node.freeDoc()

class ResponseLibxml2DocTest(TestCase):
    def setUp(self):
        libxml2.debugMemory(1)

    def tearDown(self):
        libxml2.cleanupParser()
        leaked_bytes = libxml2.debugMemory(0)
        assert leaked_bytes == 0, "libxml2 memory leak detected: %d bytes" % leaked_bytes

    def test_getlibxml2doc(self):
        # test to simulate '\x00' char in body of html page
        #this method don't should raise TypeError Exception
        from scrapy.core.manager import scrapymanager
        scrapymanager.configure()

        self.body_content = 'test problematic \x00 body'
        self.problematic_body = ResponseBody(self.body_content, 'utf-8')
        response = Response('example.com', 'http://example.com/catalog/product/blabla-123', body=self.problematic_body)
        response.getlibxml2doc()

if __name__ == "__main__":
    main()
