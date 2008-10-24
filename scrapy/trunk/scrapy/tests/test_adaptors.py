# -*- coding: utf8 -*-
import unittest
from scrapy.item import adaptors
from scrapy.xpath.selector import XmlXPathSelector
from scrapy.http import Response, ResponseBody

class AdaptorsTestCase(unittest.TestCase):
    def test_extract(self):
        sample_xsel = XmlXPathSelector(text='<xml id="2"><tag1>foo<tag2>bar</tag2></tag1><tag3 value="mytag">test</tag3></xml>')
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('/')),
                         ['<xml id="2"><tag1>foo<tag2>bar</tag2></tag1><tag3 value="mytag">test</tag3></xml>'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('xml/*')),
                         ['<tag1>foo<tag2>bar</tag2></tag1>', '<tag3 value="mytag">test</tag3>'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('xml/@id')), ['2'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('//tag1')), ['<tag1>foo<tag2>bar</tag2></tag1>'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('//tag1//text()')),
                         ['foo', 'bar'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('//text()')),
                         ['foo', 'bar', 'test'])
        self.assertEqual(adaptors.ExtractAdaptor()(sample_xsel.x('//tag3/@value')), ['mytag'])
        
    def test_extract_links(self):
        test_data = """<html><body>
                         <div>
                           <a href="lala1.html">lala1</a>
                           <a href="/lala2.html">lala2</a>
                           <a href="http://foobar.com/lala3.html">lala3</a>
                           <a href="lala4.html"><img src="lala4.jpg" /></a>
                           <a onclick="javascript: opensomething('/my_html1.html');">something1</a>
                           <a onclick="javascript: opensomething('my_html2.html');">something2</a>
                         </div>
                       </body></html>"""
        sample_response = Response('foobar.com', 'http://foobar.com/dummy', body=ResponseBody(test_data))
        sample_xsel = XmlXPathSelector(sample_response)
        sample_adaptor = adaptors.ExtractImagesAdaptor({'response': sample_response})

        self.assertEqual(sample_adaptor(sample_xsel.x('//@href')),
                         [u'http://foobar.com/dummy/lala1.html', u'http://foobar.com/lala2.html',
                          u'http://foobar.com/lala3.html', u'http://foobar.com/dummy/lala4.html'])
        self.assertEqual(sample_adaptor(sample_xsel.x('//a')),
                         [u'http://foobar.com/dummy/lala1.html', u'http://foobar.com/lala2.html',
                          u'http://foobar.com/lala3.html', u'http://foobar.com/dummy/lala4.jpg'])
        self.assertEqual(sample_adaptor(sample_xsel.x('//a[@onclick]').re(r'opensomething\(\'(.*?)\'\)')),
                         [u'http://foobar.com/my_html1.html', u'http://foobar.com/dummy/my_html2.html'])
        
    def test_to_unicode(self):
        self.assertEqual(adaptors.ToUnicodeAdaptor()(['lala', 'lele', 'luluñ', 1, 'áé']),
                         [u'lala', u'lele', u'lulu\xf1', u'1', u'\xe1\xe9'])
        
    def test_regex(self):
        adaptor = adaptors.RegexAdaptor({'regex': r'href="(.*?)"'})
        self.assertEqual(adaptor(['<a href="lala.com">dsa</a><a href="pepe.co.uk"></a>',
                                  '<a href="das.biz">href="lelelel.net"</a>']),
                                  ['lala.com', 'pepe.co.uk', 'das.biz', 'lelelel.net'])
        
    def test_unquote_all(self):
        self.assertEqual(adaptors.UnquoteAdaptor({'keep': []})([u'hello&copy;&amp;welcome', u'&lt;br /&gt;&amp;']), [u'hello\xa9&welcome', u'<br />&'])
        
    def test_unquote(self):
        self.assertEqual(adaptors.UnquoteAdaptor()([u'hello&copy;&amp;welcome', u'&lt;br /&gt;&amp;']), [u'hello\xa9&amp;welcome', u'&lt;br />&amp;'])
        
    def test_remove_tags(self):
        test_data = ['<a href="lala">adsaas<br /></a>', '<div id="1"><table>dsadasf</table></div>']
        self.assertEqual(adaptors.RemoveTagsAdaptor()(test_data), ['adsaas', 'dsadasf'])
        
    def test_remove_root(self):
        self.assertEqual(adaptors.RemoveRootAdaptor()(['<div>lallaa<a href="coso">dsfsdfds</a>pepepep<br /></div>']),
                         ['lallaa<a href="coso">dsfsdfds</a>pepepep<br />'])
        
    def test_remove_multispaces(self):
        self.assertEqual(adaptors.CleanSpacesAdaptor()(['  hello,  whats     up?', 'testing testingtesting      testing']),
                         [' hello, whats up?', 'testing testingtesting testing'])
        
    def test_strip(self):
        self.assertEqual(adaptors.StripAdaptor()([' hi there, sweety ;D ', ' I CAN HAZ TEST??    ']),
                         ['hi there, sweety ;D', 'I CAN HAZ TEST??'])
        
    def test_drop_empty_elements(self):
        self.assertEqual(adaptors.DropEmptyAdaptor()([1, 2, None, 5, None, 6, None, 'hi']),
                         [1, 2, 5, 6, 'hi'])
        
    def test_delist(self):
        self.assertEqual(adaptors.DelistAdaptor()(['hi', 'there', 'fellas.', 'this', 'is', 'my', 'test.']),
                         'hi there fellas. this is my test.')
        
    
