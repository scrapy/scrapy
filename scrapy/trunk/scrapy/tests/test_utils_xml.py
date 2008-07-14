import os
import unittest

from scrapy.utils.xml import xpathselector_iternodes
from scrapy.http import Response

class UtilsXmlTestCase(unittest.TestCase):

    def test_iterator(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<products xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="someschmea.xsd">
  <product id="001">
    <type>Type 1</type>
    <name>Name 1</name>
  </product>
  <product id="002">
    <type>Type 2</type>
    <name>Name 2</name>
  </product>
</products>
        """
        response = Response(domain="example.com", url="http://example.com", body=body)
        attrs = []
        for x in xpathselector_iternodes(response, 'product'):
            attrs.append((x.x("@id").extract(), x.x("name/text()").extract(), x.x("./type/text()").extract()))

        self.assertEqual(attrs, 
                         [(['001'], ['Name 1'], ['Type 1']), (['002'], ['Name 2'], ['Type 2'])])

    def test_iterator_utf16(self):
        samplefile = os.path.join(os.path.abspath(os.path.dirname(__file__)), "sample_data", "feeds", "feed-sample3.xml")
        body = open(samplefile).read()
        response = Response(domain="example.com", url="http://example.com", headers={"Content-type": "text/xml; encoding=UTF-16"}, body=body)
        self.assertEqual([x.x("@id").extract() for x in xpathselector_iternodes(response, 'product')],
                         [['34017532'], ['34017557'], ['34017563'], ['34018057'], ['34018313'], ['34018599']])

    def test_iterator_text(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        self.assertEqual([x.x("text()").extract() for x in xpathselector_iternodes(body, 'product')],
                         [[u'one'], [u'two']])

if __name__ == "__main__":
    unittest.main()   
