# -*- coding: utf-8 -*-
from unittest import TestCase, main
import libxml2
from scrapy.http import ResponseBody

class ResponseTest(TestCase):
    def test_responsebodyencoding(self):
        string = 'кириллический текст'
        unicode_string = unicode(string, 'utf-8')
        body_cp1251 = unicode_string.encode('cp1251')
        body = ResponseBody(body_cp1251, 'cp1251')
        self.assertEqual(body.to_unicode(), unicode_string)
        self.assertEqual(isinstance(body.to_unicode(), unicode), True)
        self.assertEqual(body.to_string('utf-8'), string)
        self.assertEqual(isinstance(body.to_string('utf-8'), str), True)
        self.assertEqual(body.to_string(), body_cp1251)
        self.assertEqual(isinstance(body.to_string('utf-8'), str), True)

if __name__ == "__main__":
    main()
