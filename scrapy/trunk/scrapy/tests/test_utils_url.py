import unittest
from scrapy.utils.url import url_is_from_any_domain, safe_url_string, safe_download_url, url_query_parameter, add_or_replace_parameter, url_query_cleaner, canonicalize_url, check_valid_urlencode

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

        self.assertEqual(safe_url_string("http://www.example.com/test?p(29)url(http://www.another.net/page)"),
                                         "http://www.example.com/test?p(29)url(http://www.another.net/page)")
        self.assertEqual(safe_url_string("http://www.example.com/Brochures_&_Paint_Cards&PageSize=200"),
                                         "http://www.example.com/Brochures_&_Paint_Cards&PageSize=200")
                  
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
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired#id20", ['id', 'foo']),
                         'product.html?id=200&foo=bar')

    def test_canonicalize_url(self):
        # no query arguments
        self.assertEqual(canonicalize_url("http://www.example.com"),
                         "http://www.example.com")

        # typical usage
        self.assertEqual(canonicalize_url("http://www.example.com/do?a=1&b=2&c=3"),
                                          "http://www.example.com/do?a=1&b=2&c=3")
        self.assertEqual(canonicalize_url("http://www.example.com/do?c=1&b=2&a=3"),
                                          "http://www.example.com/do?a=3&b=2&c=1")
        self.assertEqual(canonicalize_url("http://www.example.com/do?&a=1"),
                                          "http://www.example.com/do?a=1")
        
        # sorting by argument values
        self.assertEqual(canonicalize_url("http://www.example.com/do?c=3&b=5&b=2&a=50"),
                         "http://www.example.com/do?a=50&b=2&b=5&c=3")

        # using keep_blank_values
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2"),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2", keep_blank_values=True),
                                          "http://www.example.com/do?a=2&b=")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2"),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2", keep_blank_values=True),
                                          "http://www.example.com/do?a=2&b=&c=")
                        
        # spaces
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a+space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")
        self.assertEqual(canonicalize_url("http://www.example.com/do?q=a%20space&a=1"),
                                          "http://www.example.com/do?a=1&q=a+space")

        # normalize percent-encoding case (in paths)
        self.assertEqual(canonicalize_url("http://www.example.com/a%a3do"),
                                          "http://www.example.com/a%A3do"),
        # normalize percent-encoding case (in query arguments)
        self.assertEqual(canonicalize_url("http://www.example.com/do?k=b%a3"),
                                          "http://www.example.com/do?k=b%A3")

        # non-ASCII percent-encoding in paths
        self.assertEqual(canonicalize_url("http://www.example.com/a do?a=1"),
                                          "http://www.example.com/a%20do?a=1"),
        self.assertEqual(canonicalize_url("http://www.example.com/a %20do?a=1"),
                                          "http://www.example.com/a%20%20do?a=1"),
        self.assertEqual(canonicalize_url("http://www.example.com/a do\xc2\xa3.html?a=1"),
                                          "http://www.example.com/a%20do%C2%A3.html?a=1")
        # non-ASCII percent-encoding in query arguments
        self.assertEqual(canonicalize_url(u"http://www.example.com/do?price=\xa3500&a=5&z=3"),
                                          u"http://www.example.com/do?a=5&price=%C2%A3500&z=3")
        self.assertEqual(canonicalize_url("http://www.example.com/do?price=\xc2\xa3500&a=5&z=3"),
                                          "http://www.example.com/do?a=5&price=%C2%A3500&z=3")
        self.assertEqual(canonicalize_url("http://www.example.com/do?price(\xc2\xa3)=500&a=1"),
                                          "http://www.example.com/do?a=1&price%28%C2%A3%29=500")

        # urls containing auth and ports
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com:81/do?now=1"),
                                          u"http://user:pass@www.example.com:81/do?now=1")

        # remove fragments
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com/do?a=1#frag"),
                                          u"http://user:pass@www.example.com/do?a=1")
        self.assertEqual(canonicalize_url(u"http://user:pass@www.example.com/do?a=1#frag", keep_fragments=True),
                                          u"http://user:pass@www.example.com/do?a=1#frag")

    def test_check_valid_urlencode(self):
        self.assertFalse(check_valid_urlencode(r'http://www.example.com/pictures\detail\CAN43664.jpg'))
        self.assertTrue(check_valid_urlencode('http://www.example.com/pictures%5Cdetail%5CCAN43664.jpg'))

        self.assertFalse(check_valid_urlencode('http://www.example.com/pictures detail CAN43664.jpg'))
        self.assertTrue(check_valid_urlencode('http://www.example.com/pictures+detail%20CAN43664.jpg'))

        self.assertFalse(check_valid_urlencode('http://www.example.com/?q=foo bar&q2=foo2 bar2'))
        self.assertTrue(check_valid_urlencode('http://www.example.com/?q=foo+bar&q2=foo2%20bar2'))

        self.assertFalse(check_valid_urlencode('http://www.example.com/.,:;!@$%^*()_-[]{}|'))
        self.assertTrue(check_valid_urlencode('http://www.example.com/.,:;!@%24%25%5E*()_-%5B%5D%7B%7D%7C'))
        self.assertTrue(check_valid_urlencode('http://www.example.com/.%2C%3A%3B%21%40%24%25%5E%2A%28%29_-%5B%5D%7B%7D%7C'))

if __name__ == "__main__":
    unittest.main()

