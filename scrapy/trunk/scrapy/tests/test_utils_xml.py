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

    def test_iterator_text(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        self.assertEqual([x.x("text()").extract() for x in xpathselector_iternodes(body, 'product')],
                         [[u'one'], [u'two']])

if __name__ == "__main__":
    unittest.main()   
