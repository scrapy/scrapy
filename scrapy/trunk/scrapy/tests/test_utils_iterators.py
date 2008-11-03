import os
import unittest

from scrapy.utils.iterators import csviter, xmliter
from scrapy.http import Response

class UtilsXmlTestCase(unittest.TestCase):
    ### NOTE: Encoding issues have been found with BeautifulSoup for utf-16 files, utf-16 test removed ###
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
        for x in xmliter(response, 'product'):
            attrs.append((x.x("@id").extract(), x.x("name/text()").extract(), x.x("./type/text()").extract()))

        self.assertEqual(attrs, 
                         [(['001'], ['Name 1'], ['Type 1']), (['002'], ['Name 2'], ['Type 2'])])

    def test_iterator_text(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        self.assertEqual([x.x("text()").extract() for x in xmliter(body, 'product')],
                         [[u'one'], [u'two']])

    def test_iterator_exception(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        iter = xmliter(body, 'product')
        iter.next()
        iter.next()

        self.assertRaises(StopIteration, iter.next)

class UtilsCsvTestCase(unittest.TestCase):
    sample_feed_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data', 'feeds', 'feed-sample3.csv')

    def test_iterator_defaults(self):
        body = open(self.sample_feed_path).read()

        response = Response(domain="example.com", url="http://example.com/", body=body)
        csv = csviter(response)

        result = [row for row in csv]
        self.assertEqual(result,
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

        # explicit type check cuz' we no like stinkin' autocasting! yarrr
        for result_row in result:
            self.assert_(all((isinstance(k, unicode) for k in result_row.keys())))
            self.assert_(all((isinstance(v, unicode) for v in result_row.values())))

    def test_iterator_delimiter(self):
        body = open(self.sample_feed_path).read().replace(',', '\t')

        response = Response(domain="example.com", url="http://example.com/", body=body)
        csv = csviter(response, delimiter='\t')

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_iterator_headers(self):
        sample = open(self.sample_feed_path).read().splitlines()
        headers, body = sample[0].split(','), '\n'.join(sample[1:])

        response = Response(domain="example.com", url="http://example.com/", body=body)
        csv = csviter(response, headers=headers)

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_iterator_falserow(self):
        body = open(self.sample_feed_path).read()
        body = '\n'.join((body, 'a,b', 'a,b,c,d'))

        response = Response(domain="example.com", url="http://example.com/", body=body)
        csv = csviter(response)

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_iterator_exception(self):
        body = open(self.sample_feed_path).read()

        response = Response(domain="example.com", url="http://example.com/", body=body)
        iter = csviter(response)
        iter.next()
        iter.next()
        iter.next()
        iter.next()

        self.assertRaises(StopIteration, iter.next)

if __name__ == "__main__":
    unittest.main()
