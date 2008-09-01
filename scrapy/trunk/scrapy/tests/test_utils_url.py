import unittest
from scrapy.utils.url import url_is_from_any_domain, safe_url_string, safe_download_url, url_query_parameter, add_or_replace_parameter, url_query_cleaner

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

    def test_url_query_parameter(self):
        self.assertEqual(url_query_parameter("product.html?id=200&foo=bar", "id"),
                         '200')
        self.assertEqual(url_query_parameter("product.html?id=200&foo=bar", "notthere", "mydefault"),
                         'mydefault')
        self.assertEqual(url_query_parameter("product.html?id=", "id"),
                         None)
        self.assertEqual(url_query_parameter("product.html?id=", "id", keep_blank_values=1),
                         '')

    def test_add_or_replace_parameter(self):
        url = 'http://domain/test'
        self.assertEqual(add_or_replace_parameter(url, 'arg', 'v'),
                         'http://domain/test?arg=v')
        url = 'http://domain/test?arg1=v1&arg2=v2&arg3=v3'
        self.assertEqual(add_or_replace_parameter(url, 'arg4', 'v4'),
                         'http://domain/test?arg1=v1&arg2=v2&arg3=v3&arg4=v4')
        self.assertEqual(add_or_replace_parameter(url, 'arg3', 'nv3'),
                         'http://domain/test?arg1=v1&arg2=v2&arg3=nv3')
        url = 'http://domain/test?arg1=v1'
        self.assertEqual(add_or_replace_parameter(url, 'arg2', 'v2', sep=';'),
                         'http://domain/test?arg1=v1;arg2=v2')
        self.assertEqual(add_or_replace_parameter("http://domain/moreInfo.asp?prodID=", 'prodID', '20'),
                         'http://domain/moreInfo.asp?prodID=20')

    def test_url_query_cleaner(self):
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired", 'id'),
                         'product.html?id=200')
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired", ['id', 'name']),
                         'product.html?id=200&name=wired')

if __name__ == "__main__":
    unittest.main()

