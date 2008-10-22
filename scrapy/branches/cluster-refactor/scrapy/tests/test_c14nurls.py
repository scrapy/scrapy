import unittest
from scrapy.utils.c14n import canonicalize

class C14nTest(unittest.TestCase):
    """ c14n comparison functions """
        
    def test_canonicalize(self):
        """Test URL canonicalization function"""
        urls = [
            ('http://www.maddiebrown.co.uk//cgi-bin//html_parser.cgi?web_page_id=12&template_file=catalogue_list_items_template&category-id=1000070&category-type=1&page=3&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2&page=2',
            'http://www.maddiebrown.co.uk//cgi-bin//html_parser.cgi?web_page_id=12&template_file=catalogue_list_items_template&category-id=1000070&category-type=1&page=3&page=2'),
             

            ('http://www.mfi.co.uk/mfi/productinfo.asp?CT=/1010/YourHomeOffice&CT=/1025/YourHomeOffice/Packages',
             'http://www.mfi.co.uk/mfi/productinfo.asp?CT=/1010/YourHomeOffice&CT=/1025/YourHomeOffice/Packages'),

            ('http://www.test-nice-url.com/index.html',
             'http://www.test-nice-url.com/index.html'),

            ('http://www.homebase.co.uk/webapp/wcs/stores/servlet/ProductDisplay?storeId=20001&langId=-1&catalogId=10701&productId=729482&Trail=C$cip=50704&categoryId=50704',
             'http://www.homebase.co.uk/webapp/wcs/stores/servlet/ProductDisplay?storeId=20001&langId=-1&catalogId=10701&productId=729482&Trail=C$cip=50704&categoryId=50704'),
        ]
        for origurl, c14nurl in urls:
            self.assertEqual(canonicalize(origurl), c14nurl)
        
if __name__ == "__main__":
    unittest.main()
        
