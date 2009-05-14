import os
import unittest
import libxml2

from scrapy.utils.iterators import csviter, xmliter
from scrapy.http import XmlResponse, TextResponse

class UtilsIteratorsTestCase(unittest.TestCase):
    ### NOTE: Encoding issues have been found with BeautifulSoup for utf-16 files, utf-16 test removed ###
    # pablo: Tests shouldn't be removed, but commented with proper steps on how
    # to reproduce the missing functionality
    def test_xmliter(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>\
            <products xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="someschmea.xsd">\
              <product id="001">\
                <type>Type 1</type>\
                <name>Name 1</name>\
              </product>\
              <product id="002">\
                <type>Type 2</type>\
                <name>Name 2</name>\
              </product>\
            </products>"""

        response = XmlResponse(url="http://example.com", body=body)
        attrs = []
        for x in xmliter(response, 'product'):
            attrs.append((x.x("@id").extract(), x.x("name/text()").extract(), x.x("./type/text()").extract()))

        self.assertEqual(attrs, 
                         [(['001'], ['Name 1'], ['Type 1']), (['002'], ['Name 2'], ['Type 2'])])

    def test_xmliter_text(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        self.assertEqual([x.x("text()").extract() for x in xmliter(body, 'product')],
                         [[u'one'], [u'two']])

    def test_xmliter_namespaces(self):
        body = """\
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <g:image_link>http://www.mydummycompany.com/images/item1.jpg</g:image_link>
                    <g:id>ITEM_1</g:id>
                    <g:price>400</g:price>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url='http://mydummycompany.com', body=body)
        my_iter = xmliter(response, 'item')

        node = my_iter.next()
        node.register_namespace('g', 'http://base.google.com/ns/1.0')
        self.assertEqual(node.x('title/text()').extract(), ['Item 1'])
        self.assertEqual(node.x('description/text()').extract(), ['This is item 1'])
        self.assertEqual(node.x('link/text()').extract(), ['http://www.mydummycompany.com/items/1'])
        self.assertEqual(node.x('g:image_link/text()').extract(), ['http://www.mydummycompany.com/images/item1.jpg'])
        self.assertEqual(node.x('g:id/text()').extract(), ['ITEM_1'])
        self.assertEqual(node.x('g:price/text()').extract(), ['400'])
        self.assertEqual(node.x('image_link/text()').extract(), [])
        self.assertEqual(node.x('id/text()').extract(), [])
        self.assertEqual(node.x('price/text()').extract(), [])

    def test_xmliter_exception(self):
        body = u"""<?xml version="1.0" encoding="UTF-8"?><products><product>one</product><product>two</product></products>"""
        
        iter = xmliter(body, 'product')
        iter.next()
        iter.next()

        self.assertRaises(StopIteration, iter.next)

    def test_xmliter_encoding(self):
        body = '<?xml version="1.0" encoding="ISO-8859-9"?>\n<xml>\n    <item>Some Turkish Characters \xd6\xc7\xde\xdd\xd0\xdc \xfc\xf0\xfd\xfe\xe7\xf6</item>\n</xml>\n\n'
        response = XmlResponse('http://www.example.com', body=body)
        self.assertEqual(
            xmliter(response, 'item').next().extract(),
            u'<item>Some Turkish Characters \xd6\xc7\u015e\u0130\u011e\xdc \xfc\u011f\u0131\u015f\xe7\xf6</item>'
        )

class UtilsCsvTestCase(unittest.TestCase):
    sample_feeds_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data', 'feeds')
    sample_feed_path = os.path.join(sample_feeds_dir, 'feed-sample3.csv')
    sample_feed2_path = os.path.join(sample_feeds_dir, 'feed-sample4.csv')
    sample_feed3_path = os.path.join(sample_feeds_dir, 'feed-sample5.csv')

    def test_csviter_defaults(self):
        body = open(self.sample_feed_path).read()

        response = TextResponse(url="http://example.com/", body=body)
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

    def test_csviter_delimiter(self):
        body = open(self.sample_feed_path).read().replace(',', '\t')

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, delimiter='\t')

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_csviter_headers(self):
        sample = open(self.sample_feed_path).read().splitlines()
        headers, body = sample[0].split(','), '\n'.join(sample[1:])

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, headers=headers)

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_csviter_falserow(self):
        body = open(self.sample_feed_path).read()
        body = '\n'.join((body, 'a,b', 'a,b,c,d'))

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        self.assertEqual([row for row in csv],
                         [{u'id': u'1', u'name': u'alpha',   u'value': u'foobar'},
                          {u'id': u'2', u'name': u'unicode', u'value': u'\xfan\xedc\xf3d\xe9\u203d'},
                          {u'id': u'3', u'name': u'multi',   u'value': u'foo\nbar'},
                          {u'id': u'4', u'name': u'empty',   u'value': u''}])

    def test_csviter_exception(self):
        body = open(self.sample_feed_path).read()

        response = TextResponse(url="http://example.com/", body=body)
        iter = csviter(response)
        iter.next()
        iter.next()
        iter.next()
        iter.next()

        self.assertRaises(StopIteration, iter.next)

    def test_csviter_encoding(self):
        body1 = open(self.sample_feed2_path).read()
        body2 = open(self.sample_feed3_path).read()

        response = TextResponse(url="http://example.com/", body=body1, encoding='latin1')
        csv = csviter(response)
        self.assertEqual([row for row in csv],
            [{u'id': u'1', u'name': u'latin1', u'value': u'test'},
             {u'id': u'2', u'name': u'something', u'value': u'\xf1\xe1\xe9\xf3'}])

        response = TextResponse(url="http://example.com/", body=body2, encoding='cp852')
        csv = csviter(response)
        self.assertEqual([row for row in csv],
            [{u'id': u'1', u'name': u'cp852', u'value': u'test'},
             {u'id': u'2', u'name': u'something', u'value': u'\u255a\u2569\u2569\u2569\u2550\u2550\u2557'}])


if __name__ == "__main__":
    unittest.main()
