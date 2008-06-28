import unittest
from scrapy.utils.url import url_is_from_any_domain, safe_url_string, safe_download_url

class UrlUtilsTest(unittest.TestCase):

    def test_url_is_from_any_domain(self):
        url = 'http://www.wheele-bin-art.co.uk/get/product/123'
        self.assertTrue(url_is_from_any_domain(url, ['wheele-bin-art.co.uk']))
        self.assertFalse(url_is_from_any_domain(url, ['art.co.uk']))

        url = 'http://wheele-bin-art.co.uk/get/product/123'
        self.assertTrue(url_is_from_any_domain(url, ['wheele-bin-art.co.uk']))
        self.assertFalse(url_is_from_any_domain(url, ['art.co.uk']))

        url = 'javascript:%20document.orderform_2581_1190810811.mode.value=%27add%27;%20javascript:%20document.orderform_2581_1190810811.submit%28%29'
        self.assertFalse(url_is_from_any_domain(url, ['testdomain.com']))
        self.assertFalse(url_is_from_any_domain(url+'.testdomain.com', ['testdomain.com']))

    def test_safe_url_string(self):
        # Motoko Kusanagi (Cyborg from Ghost in the Shell)
        motoko = u'\u8349\u8599 \u7d20\u5b50'
        self.assertEqual(safe_url_string(motoko),  # note the %20 for space
                        '%E8%8D%89%E8%96%99%20%E7%B4%A0%E5%AD%90')
        self.assertEqual(safe_url_string(motoko),
                         safe_url_string(safe_url_string(motoko)))
        self.assertEqual(safe_url_string(u'\xa9'), # copyright symbol
                         '%C2%A9')
        self.assertEqual(safe_url_string(u'\xa9', 'iso-8859-1'),
                         '%A9')
        self.assertEqual(safe_url_string("http://www.scrapy.org/"),
                        'http://www.scrapy.org/')

        alessi = u'/ecommerce/oggetto/Te \xf2/tea-strainer/1273'

        self.assertEqual(safe_url_string(alessi),
                         '/ecommerce/oggetto/Te%20%C3%B2/tea-strainer/1273')

    def test_safe_download_url(self):
        self.assertEqual(safe_download_url('http://www.scrapy.org/../'),
                         'http://www.scrapy.org/')
        self.assertEqual(safe_download_url('http://www.scrapy.org/../../images/../image'),
                         'http://www.scrapy.org/image')
        self.assertEqual(safe_download_url('http://www.scrapy.org/dir/'),
                         'http://www.scrapy.org/dir/')

if __name__ == "__main__":
    unittest.main()

