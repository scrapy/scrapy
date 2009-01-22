import unittest
from scrapy.http.response import Response
from scrapy.utils.response import body_or_str, get_base_url

class ResponseUtilsTest(unittest.TestCase):
    dummy_response = Response(url='http://example.org/', body='dummy_response')

    def test_body_or_str_input(self):
        self.assertTrue(isinstance(body_or_str(self.dummy_response), basestring))
        self.assertTrue(isinstance(body_or_str('text'), basestring))
        self.assertRaises(Exception, body_or_str, 2)

    def test_body_or_str_extraction(self):
        self.assertEqual(body_or_str(self.dummy_response), 'dummy_response')
        self.assertEqual(body_or_str('text'), 'text')

    def test_body_or_str_encoding(self):
        self.assertTrue(isinstance(body_or_str(self.dummy_response, unicode=False), str))
        self.assertTrue(isinstance(body_or_str(self.dummy_response, unicode=True), unicode))

        self.assertTrue(isinstance(body_or_str('text', unicode=False), str))
        self.assertTrue(isinstance(body_or_str('text', unicode=True), unicode))

        self.assertTrue(isinstance(body_or_str(u'text', unicode=False), str))
        self.assertTrue(isinstance(body_or_str(u'text', unicode=True), unicode))

    def test_get_base_url(self):
        response = Response(url='http://example.org', body="""\
            <html>\
            <head><title>Dummy</title><base href='http://example.org/something' /></head>\
            <body>blahablsdfsal&amp;</body>\
            </html>""")
        self.assertEqual(get_base_url(response), 'http://example.org/something')


if __name__ == "__main__":
    unittest.main()
