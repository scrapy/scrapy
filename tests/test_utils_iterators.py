import os

from pytest import mark
from twisted.trial import unittest

from scrapy.utils.iterators import csviter, xmliter, _body_or_str, xmliter_lxml
from scrapy.http import XmlResponse, TextResponse, Response
from tests import get_testdata


class XmliterTestCase(unittest.TestCase):

    xmliter = staticmethod(xmliter)

    def test_xmliter(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <products xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                      xsi:noNamespaceSchemaLocation="someschmea.xsd">
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

        response = XmlResponse(url="http://example.com", body=body)
        attrs = []
        for x in self.xmliter(response, 'product'):
            attrs.append((
                x.attrib['id'],
                x.xpath("name/text()").getall(),
                x.xpath("./type/text()").getall()))

        self.assertEqual(attrs,
                         [('001', ['Name 1'], ['Type 1']), ('002', ['Name 2'], ['Type 2'])])

    def test_xmliter_unusual_node(self):
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
            <root>
                <matchme...></matchme...>
                <matchmenot></matchmenot>
            </root>
        """
        response = XmlResponse(url="http://example.com", body=body)
        nodenames = [e.xpath('name()').getall() for e in self.xmliter(response, 'matchme...')]
        self.assertEqual(nodenames, [['matchme...']])

    def test_xmliter_unicode(self):
        # example taken from https://github.com/scrapy/scrapy/issues/1665
        body = """<?xml version="1.0" encoding="UTF-8"?>
            <þingflokkar>
               <þingflokkur id="26">
                  <heiti />
                  <skammstafanir>
                     <stuttskammstöfun>-</stuttskammstöfun>
                     <löngskammstöfun />
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>80</fyrstaþing>
                  </tímabil>
               </þingflokkur>
               <þingflokkur id="21">
                  <heiti>Alþýðubandalag</heiti>
                  <skammstafanir>
                     <stuttskammstöfun>Ab</stuttskammstöfun>
                     <löngskammstöfun>Alþb.</löngskammstöfun>
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>76</fyrstaþing>
                     <síðastaþing>123</síðastaþing>
                  </tímabil>
               </þingflokkur>
               <þingflokkur id="27">
                  <heiti>Alþýðuflokkur</heiti>
                  <skammstafanir>
                     <stuttskammstöfun>A</stuttskammstöfun>
                     <löngskammstöfun>Alþfl.</löngskammstöfun>
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>27</fyrstaþing>
                     <síðastaþing>120</síðastaþing>
                  </tímabil>
               </þingflokkur>
            </þingflokkar>"""

        for r in (
            # with bytes
            XmlResponse(url="http://example.com", body=body.encode('utf-8')),
            # Unicode body needs encoding information
            XmlResponse(url="http://example.com", body=body, encoding='utf-8'),
        ):
            attrs = []
            for x in self.xmliter(r, 'þingflokkur'):
                attrs.append((x.attrib['id'],
                              x.xpath('./skammstafanir/stuttskammstöfun/text()').getall(),
                              x.xpath('./tímabil/fyrstaþing/text()').getall()))

            self.assertEqual(attrs,
                             [('26', ['-'], ['80']),
                              ('21', ['Ab'], ['76']),
                              ('27', ['A'], ['27'])])

    def test_xmliter_text(self):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<products><product>one</product><product>two</product></products>'
        )

        self.assertEqual([x.xpath("text()").getall() for x in self.xmliter(body, 'product')],
                         [['one'], ['two']])

    def test_xmliter_namespaces(self):
        body = b"""
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
        my_iter = self.xmliter(response, 'item')
        node = next(my_iter)
        node.register_namespace('g', 'http://base.google.com/ns/1.0')
        self.assertEqual(node.xpath('title/text()').getall(), ['Item 1'])
        self.assertEqual(node.xpath('description/text()').getall(), ['This is item 1'])
        self.assertEqual(node.xpath('link/text()').getall(), ['http://www.mydummycompany.com/items/1'])
        self.assertEqual(
            node.xpath('g:image_link/text()').getall(),
            ['http://www.mydummycompany.com/images/item1.jpg']
        )
        self.assertEqual(node.xpath('g:id/text()').getall(), ['ITEM_1'])
        self.assertEqual(node.xpath('g:price/text()').getall(), ['400'])
        self.assertEqual(node.xpath('image_link/text()').getall(), [])
        self.assertEqual(node.xpath('id/text()').getall(), [])
        self.assertEqual(node.xpath('price/text()').getall(), [])

    def test_xmliter_namespaced_nodename(self):
        body = b"""
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
        my_iter = self.xmliter(response, 'g:image_link')
        node = next(my_iter)
        node.register_namespace('g', 'http://base.google.com/ns/1.0')
        self.assertEqual(node.xpath('text()').extract(), ['http://www.mydummycompany.com/images/item1.jpg'])

    def test_xmliter_namespaced_nodename_missing(self):
        body = b"""
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
        my_iter = self.xmliter(response, 'g:link_image')
        with self.assertRaises(StopIteration):
            next(my_iter)

    def test_xmliter_exception(self):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<products><product>one</product><product>two</product></products>'
        )

        iter = self.xmliter(body, 'product')
        next(iter)
        next(iter)

        self.assertRaises(StopIteration, next, iter)

    def test_xmliter_objtype_exception(self):
        i = self.xmliter(42, 'product')
        self.assertRaises(TypeError, next, i)

    def test_xmliter_encoding(self):
        body = (
            b'<?xml version="1.0" encoding="ISO-8859-9"?>\n'
            b'<xml>\n'
            b'    <item>Some Turkish Characters \xd6\xc7\xde\xdd\xd0\xdc \xfc\xf0\xfd\xfe\xe7\xf6</item>\n'
            b'</xml>\n\n'
        )
        response = XmlResponse('http://www.example.com', body=body)
        self.assertEqual(
            next(self.xmliter(response, 'item')).get(),
            '<item>Some Turkish Characters \xd6\xc7\u015e\u0130\u011e\xdc \xfc\u011f\u0131\u015f\xe7\xf6</item>'
        )


class LxmlXmliterTestCase(XmliterTestCase):
    xmliter = staticmethod(xmliter_lxml)

    @mark.xfail(reason='known bug of the current implementation')
    def test_xmliter_namespaced_nodename(self):
        super().test_xmliter_namespaced_nodename()

    def test_xmliter_iterate_namespace(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <image_link>http://www.mydummycompany.com/images/item1.jpg</image_link>
                    <image_link>http://www.mydummycompany.com/images/item2.jpg</image_link>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url='http://mydummycompany.com', body=body)

        no_namespace_iter = self.xmliter(response, 'image_link')
        self.assertEqual(len(list(no_namespace_iter)), 0)

        namespace_iter = self.xmliter(response, 'image_link', 'http://base.google.com/ns/1.0')
        node = next(namespace_iter)
        self.assertEqual(node.xpath('text()').getall(), ['http://www.mydummycompany.com/images/item1.jpg'])
        node = next(namespace_iter)
        self.assertEqual(node.xpath('text()').getall(), ['http://www.mydummycompany.com/images/item2.jpg'])

    def test_xmliter_namespaces_prefix(self):
        body = b"""
        <?xml version="1.0" encoding="UTF-8"?>
        <root>
            <h:table xmlns:h="http://www.w3.org/TR/html4/">
              <h:tr>
                <h:td>Apples</h:td>
                <h:td>Bananas</h:td>
              </h:tr>
            </h:table>

            <f:table xmlns:f="http://www.w3schools.com/furniture">
              <f:name>African Coffee Table</f:name>
              <f:width>80</f:width>
              <f:length>120</f:length>
            </f:table>

        </root>
        """
        response = XmlResponse(url='http://mydummycompany.com', body=body)
        my_iter = self.xmliter(response, 'table', 'http://www.w3.org/TR/html4/', 'h')

        node = next(my_iter)
        self.assertEqual(len(node.xpath('h:tr/h:td').getall()), 2)
        self.assertEqual(node.xpath('h:tr/h:td[1]/text()').getall(), ['Apples'])
        self.assertEqual(node.xpath('h:tr/h:td[2]/text()').getall(), ['Bananas'])

        my_iter = self.xmliter(response, 'table', 'http://www.w3schools.com/furniture', 'f')

        node = next(my_iter)
        self.assertEqual(node.xpath('f:name/text()').getall(), ['African Coffee Table'])

    def test_xmliter_objtype_exception(self):
        i = self.xmliter(42, 'product')
        self.assertRaises(TypeError, next, i)


class UtilsCsvTestCase(unittest.TestCase):
    sample_feeds_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data', 'feeds')
    sample_feed_path = os.path.join(sample_feeds_dir, 'feed-sample3.csv')
    sample_feed2_path = os.path.join(sample_feeds_dir, 'feed-sample4.csv')
    sample_feed3_path = os.path.join(sample_feeds_dir, 'feed-sample5.csv')

    def test_csviter_defaults(self):
        body = get_testdata('feeds', 'feed-sample3.csv')
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        result = [row for row in csv]
        self.assertEqual(result,
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

        # explicit type check cuz' we no like stinkin' autocasting! yarrr
        for result_row in result:
            self.assertTrue(all((isinstance(k, str) for k in result_row.keys())))
            self.assertTrue(all((isinstance(v, str) for v in result_row.values())))

    def test_csviter_delimiter(self):
        body = get_testdata('feeds', 'feed-sample3.csv').replace(b',', b'\t')
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, delimiter='\t')

        self.assertEqual([row for row in csv],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

    def test_csviter_quotechar(self):
        body1 = get_testdata('feeds', 'feed-sample6.csv')
        body2 = get_testdata('feeds', 'feed-sample6.csv').replace(b',', b'|')

        response1 = TextResponse(url="http://example.com/", body=body1)
        csv1 = csviter(response1, quotechar="'")

        self.assertEqual([row for row in csv1],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

        response2 = TextResponse(url="http://example.com/", body=body2)
        csv2 = csviter(response2, delimiter="|", quotechar="'")

        self.assertEqual([row for row in csv2],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

    def test_csviter_wrong_quotechar(self):
        body = get_testdata('feeds', 'feed-sample6.csv')
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        self.assertEqual([row for row in csv],
                         [{"'id'": "1", "'name'": "'alpha'", "'value'": "'foobar'"},
                          {"'id'": "2", "'name'": "'unicode'", "'value'": "'\xfan\xedc\xf3d\xe9\u203d'"},
                          {"'id'": "'3'", "'name'": "'multi'", "'value'": "'foo"},
                          {"'id'": "4", "'name'": "'empty'", "'value'": ""}])

    def test_csviter_delimiter_binary_response_assume_utf8_encoding(self):
        body = get_testdata('feeds', 'feed-sample3.csv').replace(b',', b'\t')
        response = Response(url="http://example.com/", body=body)
        csv = csviter(response, delimiter='\t')

        self.assertEqual([row for row in csv],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

    def test_csviter_headers(self):
        sample = get_testdata('feeds', 'feed-sample3.csv').splitlines()
        headers, body = sample[0].split(b','), b'\n'.join(sample[1:])

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, headers=[h.decode('utf-8') for h in headers])

        self.assertEqual([row for row in csv],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': 'foo\nbar'},
                          {'id': '4', 'name': 'empty', 'value': ''}])

    def test_csviter_falserow(self):
        body = get_testdata('feeds', 'feed-sample3.csv')
        body = b'\n'.join((body, b'a,b', b'a,b,c,d'))

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        self.assertEqual([row for row in csv],
                         [{'id': '1', 'name': 'alpha', 'value': 'foobar'},
                          {'id': '2', 'name': 'unicode', 'value': '\xfan\xedc\xf3d\xe9\u203d'},
                          {'id': '3', 'name': 'multi', 'value': "foo\nbar"},
                          {'id': '4', 'name': 'empty', 'value': ''}])

    def test_csviter_exception(self):
        body = get_testdata('feeds', 'feed-sample3.csv')

        response = TextResponse(url="http://example.com/", body=body)
        iter = csviter(response)
        next(iter)
        next(iter)
        next(iter)
        next(iter)

        self.assertRaises(StopIteration, next, iter)

    def test_csviter_encoding(self):
        body1 = get_testdata('feeds', 'feed-sample4.csv')
        body2 = get_testdata('feeds', 'feed-sample5.csv')

        response = TextResponse(url="http://example.com/", body=body1, encoding='latin1')
        csv = csviter(response)
        self.assertEqual(
            list(csv),
            [
                {'id': '1', 'name': 'latin1', 'value': 'test'},
                {'id': '2', 'name': 'something', 'value': '\xf1\xe1\xe9\xf3'},
            ]
        )

        response = TextResponse(url="http://example.com/", body=body2, encoding='cp852')
        csv = csviter(response)
        self.assertEqual(
            list(csv),
            [
                {'id': '1', 'name': 'cp852', 'value': 'test'},
                {'id': '2', 'name': 'something', 'value': '\u255a\u2569\u2569\u2569\u2550\u2550\u2557'},
            ]
        )


class TestHelper(unittest.TestCase):
    bbody = b'utf8-body'
    ubody = bbody.decode('utf8')
    txtresponse = TextResponse(url='http://example.org/', body=bbody, encoding='utf-8')
    response = Response(url='http://example.org/', body=bbody)

    def test_body_or_str(self):
        for obj in (self.bbody, self.ubody, self.txtresponse, self.response):
            r1 = _body_or_str(obj)
            self._assert_type_and_value(r1, self.ubody, obj)
            r2 = _body_or_str(obj, unicode=True)
            self._assert_type_and_value(r2, self.ubody, obj)
            r3 = _body_or_str(obj, unicode=False)
            self._assert_type_and_value(r3, self.bbody, obj)
            self.assertTrue(type(r1) is type(r2))
            self.assertTrue(type(r1) is not type(r3))

    def _assert_type_and_value(self, a, b, obj):
        self.assertTrue(type(a) is type(b),
                        f'Got {type(a)}, expected {type(b)} for { obj!r}')
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
