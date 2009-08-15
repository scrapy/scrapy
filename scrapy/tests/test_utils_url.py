import unittest
from scrapy.utils.url import url_is_from_any_domain, safe_url_string, safe_download_url, \
    url_query_parameter, add_or_replace_parameter, url_query_cleaner, canonicalize_url, \
    urljoin_rfc


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

    def test_urljoin_rfc(self):
        self.assertEqual(urljoin_rfc('http://example.com/some/path', 'newpath/test'),
                                     'http://example.com/some/newpath/test')
        self.assertEqual(urljoin_rfc('http://example.com/some/path/a.jpg', '../key/other'),
                                     'http://example.com/some/key/other')
        u = urljoin_rfc(u'http://example.com/lolo/\xa3/lele', u'lala/\xa3')
        self.assertEqual(u, 'http://example.com/lolo/\xc2\xa3/lala/\xc2\xa3')
        assert isinstance(u, str)
        u = urljoin_rfc(u'http://example.com/lolo/\xa3/lele', 'lala/\xa3', encoding='latin-1')
        self.assertEqual(u, 'http://example.com/lolo/\xa3/lala/\xa3')
        assert isinstance(u, str)
        u = urljoin_rfc('http://example.com/lolo/\xa3/lele', 'lala/\xa3')
        self.assertEqual(u, 'http://example.com/lolo/\xa3/lala/\xa3')
        assert isinstance(u, str)

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

        safeurl = safe_url_string(u"http://www.example.com/\xa3", encoding='latin-1')
        self.assert_(isinstance(safeurl, str))
        self.assertEqual(safeurl, "http://www.example.com/%A3")

        safeurl = safe_url_string(u"http://www.example.com/\xa3", encoding='utf-8')
        self.assert_(isinstance(safeurl, str))
        self.assertEqual(safeurl, "http://www.example.com/%C2%A3")

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

    def test_url_query_parameter_2(self):
        """
        This problem was seen several times in the feeds. Sometime affiliate URLs contains
        nested encoded affiliate URL with direct URL as parameters. For example:
        aff_url1 = 'http://www.tkqlhce.com/click-2590032-10294381?url=http%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FArgosCreateReferral%3FstoreId%3D10001%26langId%3D-1%26referrer%3DCOJUN%26params%3Dadref%253DGarden+and+DIY-%3EGarden+furniture-%3EChildren%26%2339%3Bs+garden+furniture%26referredURL%3Dhttp%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FProductDisplay%253FstoreId%253D10001%2526catalogId%253D1500001501%2526productId%253D1500357023%2526langId%253D-1'
        the typical code to extract needed URL from it is:
        aff_url2 = url_query_parameter(aff_url1, 'url')
        after this aff2_url is:
        'http://www.argos.co.uk/webapp/wcs/stores/servlet/ArgosCreateReferral?storeId=10001&langId=-1&referrer=COJUN&params=adref%3DGarden and DIY->Garden furniture->Children&#39;s gardenfurniture&referredURL=http://www.argos.co.uk/webapp/wcs/stores/servlet/ProductDisplay%3FstoreId%3D10001%26catalogId%3D1500001501%26productId%3D1500357023%26langId%3D-1'
        the direct URL extraction is
        url = url_query_parameter(aff_url2, 'referredURL')
        but this will not work, because aff_url2 contains &#39; (comma sign encoded in the feed)
        and the URL extraction will fail, current workaround was made in the spider,
        just a replace for &#39; to %27
        """
        return # FIXME: this test should pass but currently doesnt
        # correct case
        aff_url1 = "http://www.anrdoezrs.net/click-2590032-10294381?url=http%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FArgosCreateReferral%3FstoreId%3D10001%26langId%3D-1%26referrer%3DCOJUN%26params%3Dadref%253DGarden+and+DIY-%3EGarden+furniture-%3EGarden+table+and+chair+sets%26referredURL%3Dhttp%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FProductDisplay%253FstoreId%253D10001%2526catalogId%253D1500001501%2526productId%253D1500357199%2526langId%253D-1"
        aff_url2 = url_query_parameter(aff_url1, 'url')
        self.assertEqual(aff_url2, "http://www.argos.co.uk/webapp/wcs/stores/servlet/ArgosCreateReferral?storeId=10001&langId=-1&referrer=COJUN&params=adref%3DGarden and DIY->Garden furniture->Garden table and chair sets&referredURL=http://www.argos.co.uk/webapp/wcs/stores/servlet/ProductDisplay%3FstoreId%3D10001%26catalogId%3D1500001501%26productId%3D1500357199%26langId%3D-1")
        prod_url = url_query_parameter(aff_url2, 'referredURL')
        self.assertEqual(prod_url, "http://www.argos.co.uk/webapp/wcs/stores/servlet/ProductDisplay?storeId=10001&catalogId=1500001501&productId=1500357199&langId=-1")
        # weird case
        aff_url1 = "http://www.tkqlhce.com/click-2590032-10294381?url=http%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FArgosCreateReferral%3FstoreId%3D10001%26langId%3D-1%26referrer%3DCOJUN%26params%3Dadref%253DGarden+and+DIY-%3EGarden+furniture-%3EChildren%26%2339%3Bs+garden+furniture%26referredURL%3Dhttp%3A%2F%2Fwww.argos.co.uk%2Fwebapp%2Fwcs%2Fstores%2Fservlet%2FProductDisplay%253FstoreId%253D10001%2526catalogId%253D1500001501%2526productId%253D1500357023%2526langId%253D-1"
        aff_url2 = url_query_parameter(aff_url1, 'url')
        self.assertEqual(aff_url2, "http://www.argos.co.uk/webapp/wcs/stores/servlet/ArgosCreateReferral?storeId=10001&langId=-1&referrer=COJUN&params=adref%3DGarden and DIY->Garden furniture->Children&#39;s garden furniture&referredURL=http://www.argos.co.uk/webapp/wcs/stores/servlet/ProductDisplay%3FstoreId%3D10001%26catalogId%3D1500001501%26productId%3D1500357023%26langId%3D-1")
        prod_url = url_query_parameter(aff_url2, 'referredURL')
        # fails, prod_url is None now
        self.assertEqual(prod_url, "http://www.argos.co.uk/webapp/wcs/stores/servlet/ProductDisplay?storeId=10001&catalogId=1500001501&productId=1500357023&langId=-1")

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
        url = 'http://rmc-offers.co.uk/productlist.asp?BCat=2%2C60&CatID=60'
        self.assertEqual(add_or_replace_parameter(url, 'BCat', 'newvalue', url_is_quoted=True),
                         'http://rmc-offers.co.uk/productlist.asp?BCat=newvalue&CatID=60')
        url = 'http://rmc-offers.co.uk/productlist.asp?BCat=2,60&CatID=60'
        self.assertEqual(add_or_replace_parameter(url, 'BCat', 'newvalue'),
                         'http://rmc-offers.co.uk/productlist.asp?BCat=newvalue&CatID=60')

    def test_url_query_cleaner(self):
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired", 'id'),
                         'product.html?id=200')
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired", ['id', 'name']),
                         'product.html?id=200&name=wired')
        self.assertEqual(url_query_cleaner("product.html?id=200&foo=bar&name=wired#id20", ['id', 'foo']),
                         'product.html?id=200&foo=bar')

    def test_canonicalize_url(self):
        # simplest case
        self.assertEqual(canonicalize_url("http://www.example.com"),
                                          "http://www.example.com")

        # always return a str
        assert isinstance(canonicalize_url(u"http://www.example.com"), str)

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
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2", keep_blank_values=False),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&a=2"),
                                          "http://www.example.com/do?a=2&b=")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2", keep_blank_values=False),
                                          "http://www.example.com/do?a=2")
        self.assertEqual(canonicalize_url("http://www.example.com/do?b=&c&a=2"),
                                          "http://www.example.com/do?a=2&b=&c=")

        self.assertEqual(canonicalize_url(u'http://www.example.com/do?1750,4'),
                                           'http://www.example.com/do?1750%2C4=')

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

        # urllib.quote uses a mapping cache of encoded characters. when parsing
        # an already percent-encoded url, it will fail if that url was not
        # percent-encoded as utf-8, that's why canonicalize_url must always
        # convert the urls to string. the following test asserts that
        # functionality.
        self.assertEqual(canonicalize_url(u'http://www.example.com/caf%E9-con-leche.htm'),
                                           'http://www.example.com/caf%E9-con-leche.htm')

if __name__ == "__main__":
    unittest.main()

