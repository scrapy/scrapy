# -*- coding: utf8 -*-
import unittest
from decimal import Decimal

from decobot.utils.text_extraction import clean_markup, unquote_html, read_decimal, read_price

class TextExtractionTest(unittest.TestCase):
    def test_clean_markup(self):
        
        #with html tags
        
        html = u" <p> \xa0 <!-- comment --> <span>small</span> test </p> "

        self.assertEqual(clean_markup(html),
                         u'small test')
        self.assertEqual(clean_markup(html, remove_tags=False, remove_root=False, remove_spaces=False, strip=False),
                         u' <p> \xa0 <!-- comment --> <span>small</span> test </p> ')
        self.assertEqual(clean_markup(html, remove_tags=False, remove_root=True, strip=False),
                         u' <!-- comment --> <span>small</span> test ')
        self.assertEqual(clean_markup(html, remove_tags=False, remove_root=False, remove_spaces=False, strip=True),
                         u'<p> \xa0 <!-- comment --> <span>small</span> test </p>')
        self.assertEqual(clean_markup(html, remove_tags=False, remove_spaces=True, strip=False),
                         u' <!-- comment --> <span>small</span> test ')
        self.assertEqual(clean_markup(html, remove_tags=True, remove_spaces=False, strip=False),
                         u'   \xa0    small  test   ')
        self.assertEqual(clean_markup(html, remove_tags=True, remove_spaces=True, strip=False),
                         u' small test ')
        self.assertEqual(clean_markup(html, remove_tags=True, remove_root=True, remove_spaces=True, strip=True),
                         u'small test')
                         
        #with xml tags
                
        self.assertEqual(clean_markup(u'<description/>', xml_doc=True),
                         u'')
                         
        self.assertEqual(clean_markup(u'<description/>', xml_doc=True, remove_tags=False),
                         u'<description/>')

        self.assertEqual(clean_markup(u'<value>http://stephen.digivate2:8080/uploads/suppliers/4/11931_Picture 001.jpg</value>', xml_doc=True),
                         u'http://stephen.digivate2:8080/uploads/suppliers/4/11931_Picture 001.jpg')
        self.assertEqual(clean_markup(u'<material> wood </material>', xml_doc=True),
                         u'wood')
        self.assertEqual(clean_markup(u'<material> wood </material>', strip=False, xml_doc=True),
                         u' wood ')
        self.assertEqual(clean_markup(u'<material><value>wood</value><value>iron</value></material>', xml_doc=True),
                        u'wood iron')
                        
        self.assertEqual(clean_markup(u'<data><description>hi</description><![CDATA[This is a <tag> inside cdata </tag> <g>]]><nothing/><![CDATA[Another CDATA with tags <inside>]]></data>', xml_doc=True),
                        u'hi This is a inside cdata Another CDATA with tags')
                        
        self.assertEqual(clean_markup(u'<data><description>hi</description><![CDATA[This is a <tag> inside cdata </tag> <g>]]><nothing/><![CDATA[Another CDATA with tags <inside>]]></data>', xml_doc=True, remove_tags=False),
                        u'<description>hi</description>This is a <tag> inside cdata </tag> <g><nothing/>Another CDATA with tags <inside>')
                        
        self.assertEqual(clean_markup(u'<data><description>hi</description><![CDATA[This is a <tag> inside cdata </tag> <g>]]><nothing/><![CDATA[Another CDATA with tags <inside>]]></data>', remove_cdata=False, xml_doc=True,remove_tags=False),
                        u'<description>hi</description><![CDATA[This is a <tag> inside cdata </tag> <g>]]><nothing/><![CDATA[Another CDATA with tags <inside>]]>')
                        
        self.assertEqual(clean_markup(u'<data><description>hi</description><![CDATA[This is a <tag> inside cdata </tag> <g>]]><nothing/><![CDATA[Another CDATA with tags <inside>]]></data>', remove_cdata=False, xml_doc=True),
                        u'hi <![CDATA[This is a <tag> inside cdata </tag> <g>]]> <![CDATA[Another CDATA with tags <inside>]]>')
                        
        self.assertEqual(clean_markup(u'<![CDATA[This is a <tag> inside cdata </tag> <g>]]>', remove_cdata=False, xml_doc=True),
                        u'<![CDATA[This is a <tag> inside cdata </tag> <g>]]>')

    def test_unquote_html(self):
        self.assertEqual(unquote_html(u'As low as &#163;534,456.34!'),
                         'As low as £534,456.34!')
        self.assertEqual(unquote_html('As low as &pound;534,456.34!'),
                         'As low as £534,456.34!')

    def test_read_decimal(self):
        self.assertEqual(read_decimal('asdf 234,234.45sdf '),
                         Decimal("234234.45"))
        self.assertEqual(read_decimal('asdf 2234 sdf '),
                         Decimal("2234"))
        self.assertEqual(read_decimal('947'),
                         Decimal("947"))
        self.assertEqual(read_decimal('adsfg'), 
                         None)
        self.assertEqual(read_decimal('''stained, linseed oil finish, clear glas doors'''),
                         None)

    def test_read_price(self):
        self.assertEqual(read_price(u'£549.97'),
                         Decimal("549.97"))
        self.assertEqual(read_price(u'£5,499.97'),
                         Decimal("5499.97"))
        self.assertEqual(read_price(u'Now: £5,499.97 for the last time'),
                         Decimal("5499.97"))
        self.assertEqual(read_price(u'As low as 534,456.34!'),
                         Decimal("534456.34"))
        self.assertEqual(read_price(u'As low as &#163;534,456.34!'),
                         Decimal("534456.34"))
        self.assertEqual(read_price(u'As low as &pound;534,456.34!'),
                         Decimal("534456.34"))
        self.assertEqual(read_price('asdf asdfg asdfg '),
                         None)
        self.assertEqual(read_price('wrweq qewr -&pound;12', True),
                         Decimal("-12"))
        self.assertEqual(read_price('wrweq qewr &pound;12', True),
                         Decimal("12"))
        self.assertEqual(read_price('qwe ewqeq -12', True),
                         Decimal("0"))
        self.assertEqual(read_price('qwe ewqeq 12', True),
                         Decimal("0"))
        self.assertEqual(read_price('qwe ewqeq 12'),
                         Decimal("12"))
        self.assertEqual(read_price('117.54 £'),
                         Decimal("117.54"))


if __name__ == "__main__":
    unittest.main()
