import cgi
import unittest
import re

import six
from six.moves import xmlrpc_client as xmlrpclib
from six.moves.urllib.parse import urlparse

from scrapy.http import Request, FormRequest, XmlRpcRequest, Headers, HtmlResponse
from scrapy.utils.python import to_bytes, to_native_str


class RequestTest(unittest.TestCase):

    request_class = Request
    default_method = 'GET'
    default_headers = {}
    default_meta = {}

    def test_init(self):
        # Request requires url in the constructor
        self.assertRaises(Exception, self.request_class)

        # url argument must be basestring
        self.assertRaises(TypeError, self.request_class, 123)
        r = self.request_class('http://www.example.com')

        r = self.request_class("http://www.example.com")
        assert isinstance(r.url, str)
        self.assertEqual(r.url, "http://www.example.com")
        self.assertEqual(r.method, self.default_method)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, self.default_headers)
        self.assertEqual(r.meta, self.default_meta)

        meta = {"lala": "lolo"}
        headers = {b"caca": b"coco"}
        r = self.request_class("http://www.example.com", meta=meta, headers=headers, body="a body")

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers[b"caca"], b"coco")

    def test_url_no_scheme(self):
        self.assertRaises(ValueError, self.request_class, 'foo')

    def test_headers(self):
        # Different ways of setting headers attribute
        url = 'http://www.scrapy.org'
        headers = {b'Accept':'gzip', b'Custom-Header':'nothing to tell you'}
        r = self.request_class(url=url, headers=headers)
        p = self.request_class(url=url, headers=r.headers)

        self.assertEqual(r.headers, p.headers)
        self.assertFalse(r.headers is headers)
        self.assertFalse(p.headers is r.headers)

        # headers must not be unicode
        h = Headers({'key1': u'val1', u'key2': 'val2'})
        h[u'newkey'] = u'newval'
        for k, v in h.iteritems():
            self.assert_(isinstance(k, bytes))
            for s in v:
                self.assert_(isinstance(s, bytes))

    def test_eq(self):
        url = 'http://www.scrapy.org'
        r1 = self.request_class(url=url)
        r2 = self.request_class(url=url)
        self.assertNotEqual(r1, r2)

        set_ = set()
        set_.add(r1)
        set_.add(r2)
        self.assertEqual(len(set_), 2)

    def test_url(self):
        r = self.request_class(url="http://www.scrapy.org/path")
        self.assertEqual(r.url, "http://www.scrapy.org/path")

    def test_url_quoting(self):
        r = self.request_class(url="http://www.scrapy.org/blank%20space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")
        r = self.request_class(url="http://www.scrapy.org/blank space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")

    def test_url_encoding(self):
        r1 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="utf-8")
        r2 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="latin1")
        self.assertEqual(r1.url, "http://www.scrapy.org/price/%C2%A3")
        self.assertEqual(r2.url, "http://www.scrapy.org/price/%A3")

    def test_body(self):
        r1 = self.request_class(url="http://www.example.com/")
        assert r1.body == b''

        r2 = self.request_class(url="http://www.example.com/", body=b"")
        assert isinstance(r2.body, bytes)
        self.assertEqual(r2.encoding, 'utf-8') # default encoding

        r3 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='utf-8')
        assert isinstance(r3.body, bytes)
        self.assertEqual(r3.body, b"Price: \xc2\xa3100")

        r4 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='latin1')
        assert isinstance(r4.body, bytes)
        self.assertEqual(r4.body, b"Price: \xa3100")

    def test_ajax_url(self):
        # ascii url
        r = self.request_class(url="http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, "http://www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue")
        # unicode url
        r = self.request_class(url=u"http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, "http://www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue")

    def test_copy(self):
        """Test Request copy"""

        def somecallback():
            pass

        r1 = self.request_class("http://www.example.com", callback=somecallback, errback=somecallback)
        r1.meta['foo'] = 'bar'
        r2 = r1.copy()

        # make sure copy does not propagate callbacks
        assert r1.callback is somecallback
        assert r1.errback is somecallback
        assert r2.callback is r1.callback
        assert r2.errback is r2.errback

        # make sure meta dict is shallow copied
        assert r1.meta is not r2.meta, "meta must be a shallow copy, not identical"
        self.assertEqual(r1.meta, r2.meta)

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, "headers must be a shallow copy, not identical"
        self.assertEqual(r1.headers, r2.headers)
        self.assertEqual(r1.encoding, r2.encoding)
        self.assertEqual(r1.dont_filter, r2.dont_filter)

        # Request.body can be identical since it's an immutable object (str)

    def test_copy_inherited_classes(self):
        """Test Request children copies preserve their class"""

        class CustomRequest(self.request_class):
            pass

        r1 = CustomRequest('http://www.example.com')
        r2 = r1.copy()

        assert type(r2) is CustomRequest

    def test_replace(self):
        """Test Request.replace() method"""
        r1 = self.request_class("http://www.example.com", method='GET')
        hdrs = Headers(r1.headers)
        hdrs[b'key'] = b'value'
        r2 = r1.replace(method="POST", body="New body", headers=hdrs)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.method, r2.method), ("GET", "POST"))
        self.assertEqual((r1.body, r2.body), (b'', b"New body"))
        self.assertEqual((r1.headers, r2.headers), (self.default_headers, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = self.request_class("http://www.example.com", meta={'a': 1}, dont_filter=True)
        r4 = r3.replace(url="http://www.example.com/2", body=b'', meta={}, dont_filter=False)
        self.assertEqual(r4.url, "http://www.example.com/2")
        self.assertEqual(r4.body, b'')
        self.assertEqual(r4.meta, {})
        assert r4.dont_filter is False

    def test_method_always_str(self):
        r = self.request_class("http://www.example.com", method=u"POST")
        assert isinstance(r.method, str)

    def test_immutable_attributes(self):
        r = self.request_class("http://example.com")
        self.assertRaises(AttributeError, setattr, r, 'url', 'http://example2.com')
        self.assertRaises(AttributeError, setattr, r, 'body', 'xxx')


class FormRequestTest(RequestTest):

    request_class = FormRequest

    def assertQueryEqual(self, first, second, msg=None):
        first = to_native_str(first).split("&")
        second = to_native_str(second).split("&")
        return self.assertEqual(sorted(first), sorted(second), msg)

    def test_empty_formdata(self):
        r1 = self.request_class("http://www.example.com", formdata={})
        self.assertEqual(r1.body, b'')

    def test_default_encoding_bytes(self):
        # using default encoding (utf-8)
        data = {b'one': b'two', b'price': b'\xc2\xa3 100'}
        r2 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r2.method, 'POST')
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertQueryEqual(r2.body, b'price=%C2%A3+100&one=two')
        self.assertEqual(r2.headers[b'Content-Type'], b'application/x-www-form-urlencoded')

    def test_default_encoding_textual_data(self):
        # using default encoding (utf-8)
        data = {'one': 'two', 'price': u'\u00a3 100'}
        r2 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r2.method, 'POST')
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertQueryEqual(r2.body, b'price=%C2%A3+100&one=two')
        self.assertEqual(r2.headers[b'Content-Type'], b'application/x-www-form-urlencoded')

    def test_default_encoding_mixed_data(self):
        # using default encoding (utf-8)
        data = {u'\u00b5one': b'two', b'price\xc2\xa3': u'\u00a3 100'}
        r2 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r2.method, 'POST')
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertQueryEqual(r2.body, b'%C2%B5one=two&price%C2%A3=%C2%A3+100')
        self.assertEqual(r2.headers[b'Content-Type'], b'application/x-www-form-urlencoded')

    def test_custom_encoding(self):
        data = {'price': u'\xa3 100'}
        r3 = self.request_class("http://www.example.com", formdata=data, encoding='latin1')
        self.assertEqual(r3.encoding, 'latin1')
        self.assertEqual(r3.body, b'price=%A3+100')

    def test_multi_key_values(self):
        # using multiples values for a single key
        data = {'price': u'\xa3 100', 'colours': ['red', 'blue', 'green']}
        r3 = self.request_class("http://www.example.com", formdata=data)
        self.assertQueryEqual(r3.body,
            b'colours=red&colours=blue&colours=green&price=%C2%A3+100')

    def test_from_response_post(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(response,
                formdata={'one': ['two', 'three'], 'six': 'seven'})
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers[b'Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, "http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(set(fs[b"test"]), {b"val1", b"val2"})
        self.assertEqual(set(fs[b"one"]), {b"two", b"three"})
        self.assertEqual(fs[b'test2'], [b'xxx'])
        self.assertEqual(fs[b'six'], [b'seven'])

    def test_from_response_extra_headers(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""")
        req = self.request_class.from_response(response,
                formdata={'one': ['two', 'three'], 'six': 'seven'},
                headers={"Accept-Encoding": "gzip,deflate"})
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.headers['Accept-Encoding'], b'gzip,deflate')

    def test_from_response_get(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html")
        r1 = self.request_class.from_response(response,
                formdata={'one': ['two', 'three'], 'six': 'seven'})
        self.assertEqual(r1.method, 'GET')
        self.assertEqual(urlparse(r1.url).hostname, "www.example.com")
        self.assertEqual(urlparse(r1.url).path, "/this/get.php")
        fs = _qs(r1)
        self.assertEqual(set(fs['test']), set(['val1', 'val2']))
        self.assertEqual(set(fs['one']), set(['two', 'three']))
        self.assertEqual(fs['test2'], ['xxx'])
        self.assertEqual(fs['six'], ['seven'])

    def test_from_response_override_params(self):
        response = _buildresponse(
            """<form action="get.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'})
        fs = _qs(req)
        self.assertEqual(fs[b'one'], [b'1'])
        self.assertEqual(fs[b'two'], [b'2'])

    def test_from_response_override_method(self):
        response = _buildresponse(
                '''<html><body>
                <form action="/app"></form>
                </body></html>''')
        request = FormRequest.from_response(response)
        self.assertEqual(request.method, 'GET')
        request = FormRequest.from_response(response, method='POST')
        self.assertEqual(request.method, 'POST')

    def test_from_response_override_url(self):
        response = _buildresponse(
                '''<html><body>
                <form action="/app"></form>
                </body></html>''')
        request = FormRequest.from_response(response)
        self.assertEqual(request.url, 'http://example.com/app')
        request = FormRequest.from_response(response, url='http://foo.bar/absolute')
        self.assertEqual(request.url, 'http://foo.bar/absolute')
        request = FormRequest.from_response(response, url='/relative')
        self.assertEqual(request.url, 'http://example.com/relative')

    def test_from_response_case_insensitive(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="SuBmIt" name="clickable1" value="clicked1">
            <input type="iMaGe" name="i1" src="http://my.image.org/1.jpg">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response)
        fs = _qs(req)
        self.assertEqual(fs['clickable1'], ['clicked1'])
        self.assertFalse('i1' in fs, fs)  # xpath in _get_inputs()
        self.assertFalse('clickable2' in fs, fs)  # xpath in _get_clickable()

    def test_from_response_submit_first_clickable(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'})
        fs = _qs(req)
        self.assertEqual(fs['clickable1'], ['clicked1'])
        self.assertFalse('clickable2' in fs, fs)
        self.assertEqual(fs['one'], ['1'])
        self.assertEqual(fs['two'], ['2'])

    def test_from_response_submit_not_first_clickable(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'}, \
                                              clickdata={'name': 'clickable2'})
        fs = _qs(req)
        self.assertEqual(fs['clickable2'], ['clicked2'])
        self.assertFalse('clickable1' in fs, fs)
        self.assertEqual(fs['one'], ['1'])
        self.assertEqual(fs['two'], ['2'])

    def test_from_response_dont_submit_image_as_input(self):
        response = _buildresponse(
            """<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="image" name="i2" src="http://my.image.org/1.jpg">
            <input type="submit" name="i3" value="i3v">
            </form>""")
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v']})

    def test_from_response_dont_submit_reset_as_input(self):
        response = _buildresponse(
            """<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="text" name="i2" value="i2v">
            <input type="reset" name="resetme">
            <input type="submit" name="i3" value="i3v">
            </form>""")
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v'], 'i2': ['i2v']})

    def test_from_response_multiple_clickdata(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable" value="clicked1">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="one" value="clicked1">
            <input type="hidden" name="two" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response, \
                clickdata={'name': 'clickable', 'value': 'clicked2'})
        fs = _qs(req)
        self.assertEqual(fs['clickable'], ['clicked2'])
        self.assertEqual(fs['one'], ['clicked1'])
        self.assertEqual(fs['two'], ['clicked2'])

    def test_from_response_unicode_clickdata(self):
        response = _buildresponse(
            u"""<form action="get.php" method="GET">
            <input type="submit" name="price in \u00a3" value="\u00a3 1000">
            <input type="submit" name="price in \u20ac" value="\u20ac 2000">
            <input type="hidden" name="poundsign" value="\u00a3">
            <input type="hidden" name="eurosign" value="\u20ac">
            </form>""")
        req = self.request_class.from_response(response, \
                clickdata={'name': u'price in \u00a3'})
        fs = _qs(req)
        self.assertTrue(fs[to_native_str(u'price in \u00a3')])

    def test_from_response_multiple_forms_clickdata(self):
        response = _buildresponse(
            """<form name="form1">
            <input type="submit" name="clickable" value="clicked1">
            <input type="hidden" name="field1" value="value1">
            </form>
            <form name="form2">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="field2" value="value2">
            </form>
            """)
        req = self.request_class.from_response(response, formname='form2', \
                clickdata={'name': 'clickable'})
        fs = _qs(req)
        self.assertEqual(fs['clickable'], ['clicked2'])
        self.assertEqual(fs['field2'], ['value2'])
        self.assertFalse('field1' in fs, fs)

    def test_from_response_override_clickable(self):
        response = _buildresponse('''<form><input type="submit" name="clickme" value="one"> </form>''')
        req = self.request_class.from_response(response, \
                formdata={'clickme': 'two'}, clickdata={'name': 'clickme'})
        fs = _qs(req)
        self.assertEqual(fs['clickme'], ['two'])

    def test_from_response_dont_click(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        r1 = self.request_class.from_response(response, dont_click=True)
        fs = _qs(r1)
        self.assertFalse('clickable1' in fs, fs)
        self.assertFalse('clickable2' in fs, fs)

    def test_from_response_ambiguous_clickdata(self):
        response = _buildresponse(
            """
            <form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        self.assertRaises(ValueError, self.request_class.from_response,
                          response, clickdata={'type': 'submit'})

    def test_from_response_non_matching_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable" value="clicked">
            </form>""")
        self.assertRaises(ValueError, self.request_class.from_response,
                          response, clickdata={'nonexistent': 'notme'})

    def test_from_response_nr_index_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable1" value="clicked1">
            <input type="submit" name="clickable2" value="clicked2">
            </form>
            """)
        req = self.request_class.from_response(response, clickdata={'nr': 1})
        fs = _qs(req)
        self.assertIn('clickable2', fs)
        self.assertNotIn('clickable1', fs)

    def test_from_response_invalid_nr_index_clickdata(self):
        response = _buildresponse(
            """<form>
            <input type="submit" name="clickable" value="clicked">
            </form>
            """)
        self.assertRaises(ValueError, self.request_class.from_response,
                          response, clickdata={'nr': 1})

    def test_from_response_errors_noform(self):
        response = _buildresponse("""<html></html>""")
        self.assertRaises(ValueError, self.request_class.from_response, response)

    def test_from_response_invalid_html5(self):
        response = _buildresponse("""<!DOCTYPE html><body></html><form>"""
                                  """<input type="text" name="foo" value="xxx">"""
                                  """</form></body></html>""")
        req = self.request_class.from_response(response, formdata={'bar': 'buz'})
        fs = _qs(req)
        self.assertEqual(fs, {'foo': ['xxx'], 'bar': ['buz']})

    def test_from_response_errors_formnumber(self):
        response = _buildresponse(
            """<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""")
        self.assertRaises(IndexError, self.request_class.from_response, response, formnumber=1)

    def test_from_response_noformname(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>""")
        r1 = self.request_class.from_response(response, formdata={'two':'3'})
        self.assertEqual(r1.method, 'POST')
        self.assertEqual(r1.headers['Content-type'], b'application/x-www-form-urlencoded')
        fs = _qs(r1)
        self.assertEqual(fs, {b'one': [b'1'], b'two': [b'3']})

    def test_from_response_formname_exists(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(response, formname="form2")
        self.assertEqual(r1.method, 'POST')
        fs = _qs(r1)
        self.assertEqual(fs, {b'four': [b'4'], b'three': [b'3']})

    def test_from_response_formname_notexist(self):
        response = _buildresponse(
            """<form name="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>""")
        r1 = self.request_class.from_response(response, formname="form3")
        self.assertEqual(r1.method, 'POST')
        fs = _qs(r1)
        self.assertEqual(fs, {b'one': [b'1']})

    def test_from_response_formname_errors_formnumber(self):
        response = _buildresponse(
            """<form name="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>""")
        self.assertRaises(IndexError, self.request_class.from_response, \
                          response, formname="form3", formnumber=2)

    def test_from_response_formid_exists(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form id="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(response, formid="form2")
        self.assertEqual(r1.method, 'POST')
        fs = _qs(r1)
        self.assertEqual(fs, {b'four': [b'4'], b'three': [b'3']})

    def test_from_response_formname_notexists_fallback_formid(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form id="form2" name="form2" action="post.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(response, formname="form3", formid="form2")
        self.assertEqual(r1.method, 'POST')
        fs = _qs(r1)
        self.assertEqual(fs, {b'four': [b'4'], b'three': [b'3']})

    def test_from_response_formid_notexist(self):
        response = _buildresponse(
            """<form id="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form id="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>""")
        r1 = self.request_class.from_response(response, formid="form3")
        self.assertEqual(r1.method, 'POST')
        fs = _qs(r1)
        self.assertEqual(fs, {b'one': [b'1']})

    def test_from_response_formid_errors_formnumber(self):
        response = _buildresponse(
            """<form id="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form id="form2" name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>""")
        self.assertRaises(IndexError, self.request_class.from_response, \
                          response, formid="form3", formnumber=2)

    def test_from_response_select(self):
        res = _buildresponse(
            '''<form>
            <select name="i1">
                <option value="i1v1">option 1</option>
                <option value="i1v2" selected>option 2</option>
            </select>
            <select name="i2">
                <option value="i2v1">option 1</option>
                <option value="i2v2">option 2</option>
            </select>
            <select>
                <option value="i3v1">option 1</option>
                <option value="i3v2">option 2</option>
            </select>
            <select name="i4" multiple>
                <option value="i4v1">option 1</option>
                <option value="i4v2" selected>option 2</option>
                <option value="i4v3" selected>option 3</option>
            </select>
            <select name="i5" multiple>
                <option value="i5v1">option 1</option>
                <option value="i5v2">option 2</option>
            </select>
            <select name="i6"></select>
            <select name="i7"/>
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v2'], 'i2': ['i2v1'], 'i4': ['i4v2', 'i4v3']})

    def test_from_response_radio(self):
        res = _buildresponse(
            '''<form>
            <input type="radio" name="i1" value="i1v1">
            <input type="radio" name="i1" value="iv2" checked>
            <input type="radio" name="i2" checked>
            <input type="radio" name="i2">
            <input type="radio" name="i3" value="i3v1">
            <input type="radio" name="i3">
            <input type="radio" value="i4v1">
            <input type="radio">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['iv2'], 'i2': ['on']})

    def test_from_response_checkbox(self):
        res = _buildresponse(
            '''<form>
            <input type="checkbox" name="i1" value="i1v1">
            <input type="checkbox" name="i1" value="iv2" checked>
            <input type="checkbox" name="i2" checked>
            <input type="checkbox" name="i2">
            <input type="checkbox" name="i3" value="i3v1">
            <input type="checkbox" name="i3">
            <input type="checkbox" value="i4v1">
            <input type="checkbox">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['iv2'], 'i2': ['on']})

    def test_from_response_input_text(self):
        res = _buildresponse(
            '''<form>
            <input type="text" name="i1" value="i1v1">
            <input type="text" name="i2">
            <input type="text" value="i3v1">
            <input type="text">
            <input name="i4" value="i4v1">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v1'], 'i2': [''], 'i4': ['i4v1']})

    def test_from_response_input_hidden(self):
        res = _buildresponse(
            '''<form>
            <input type="hidden" name="i1" value="i1v1">
            <input type="hidden" name="i2">
            <input type="hidden" value="i3v1">
            <input type="hidden">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v1'], 'i2': ['']})

    def test_from_response_input_textarea(self):
        res = _buildresponse(
            '''<form>
            <textarea name="i1">i1v</textarea>
            <textarea name="i2"></textarea>
            <textarea name="i3"/>
            <textarea>i4v</textarea>
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {'i1': ['i1v'], 'i2': [''], 'i3': ['']})

    def test_from_response_descendants(self):
        res = _buildresponse(
            '''<form>
            <div>
              <fieldset>
                <input type="text" name="i1">
                <select name="i2">
                    <option value="v1" selected>
                </select>
              </fieldset>
              <input type="radio" name="i3" value="i3v2" checked>
              <input type="checkbox" name="i4" value="i4v2" checked>
              <textarea name="i5"></textarea>
              <input type="hidden" name="h1" value="h1v">
              </div>
            <input type="hidden" name="h2" value="h2v">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(set(fs), set(['h2', 'i2', 'i1', 'i3', 'h1', 'i5', 'i4']))

    def test_from_response_xpath(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form action="post2.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(response, formxpath="//form[@action='post.php']")
        fs = _qs(r1)
        self.assertEqual(fs[b'one'], [b'1'])

        r1 = self.request_class.from_response(response, formxpath="//form/input[@name='four']")
        fs = _qs(r1)
        self.assertEqual(fs[b'three'], [b'3'])

        self.assertRaises(ValueError, self.request_class.from_response,
                          response, formxpath="//form/input[@name='abc']")

    def test_from_response_unicode_xpath(self):
        response = _buildresponse(b'<form name="\xd1\x8a"></form>')
        r = self.request_class.from_response(response, formxpath=u"//form[@name='\u044a']")
        fs = _qs(r)
        self.assertEqual(fs, {})

        xpath = u"//form[@name='\u03b1']"
        encoded = xpath if six.PY3 else xpath.encode('unicode_escape')
        self.assertRaisesRegexp(ValueError, re.escape(encoded),
                                self.request_class.from_response,
                                response, formxpath=xpath)

    def test_from_response_button_submit(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button type="submit" name="button1" value="submit1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(response)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, "http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(fs[b'test1'], [b'val1'])
        self.assertEqual(fs[b'test2'], [b'val2'])
        self.assertEqual(fs[b'button1'], [b'submit1'])

    def test_from_response_button_notype(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button name="button1" value="submit1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(response)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, "http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(fs[b'test1'], [b'val1'])
        self.assertEqual(fs[b'test2'], [b'val2'])
        self.assertEqual(fs[b'button1'], [b'submit1'])

    def test_from_response_submit_novalue(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <input type="submit" name="button1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(response)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, "http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(fs[b'test1'], [b'val1'])
        self.assertEqual(fs[b'test2'], [b'val2'])
        self.assertEqual(fs[b'button1'], [b''])

    def test_from_response_button_novalue(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="test1" value="val1">
            <input type="hidden" name="test2" value="val2">
            <button type="submit" name="button1">Submit</button>
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(response)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, "http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(fs[b'test1'], [b'val1'])
        self.assertEqual(fs[b'test2'], [b'val2'])
        self.assertEqual(fs[b'button1'], [b''])

    def test_html_base_form_action(self):
        response = _buildresponse(
            """
            <html>
                <head>
                    <base href="http://b.com/">
                </head>
                <body>
                    <form action="test_form">
                    </form>
                </body>
            </html>
            """,
            url='http://a.com/'
        )
        req = self.request_class.from_response(response)
        self.assertEqual(req.url, 'http://b.com/test_form')

    def test_from_response_css(self):
        response = _buildresponse(
            """<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form action="post2.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(response, formcss="form[action='post.php']")
        fs = _qs(r1)
        self.assertEqual(fs[b'one'], [b'1'])

        r1 = self.request_class.from_response(response, formcss="input[name='four']")
        fs = _qs(r1)
        self.assertEqual(fs[b'three'], [b'3'])

        self.assertRaises(ValueError, self.request_class.from_response,
                          response, formcss="input[name='abc']")

def _buildresponse(body, **kwargs):
    kwargs.setdefault('body', body)
    kwargs.setdefault('url', 'http://example.com')
    kwargs.setdefault('encoding', 'utf-8')
    return HtmlResponse(**kwargs)

def _qs(req):
    if req.method == 'POST':
        qs = req.body
    else:
        qs = req.url.partition('?')[2]
    return cgi.parse_qs(qs, True)


class XmlRpcRequestTest(RequestTest):

    request_class = XmlRpcRequest
    default_method = 'POST'
    default_headers = {b'Content-Type': [b'text/xml']}

    def _test_request(self, **kwargs):
        r = self.request_class('http://scrapytest.org/rpc2', **kwargs)
        self.assertEqual(r.headers[b'Content-Type'], b'text/xml')
        self.assertEqual(r.encoding, kwargs.get('encoding', 'utf-8'))
        self.assertEqual(r.body, to_bytes(xmlrpclib.dumps(**kwargs), r.encoding))
        self.assertEqual(r.method, 'POST')
        self.assertTrue(r.dont_filter, True)

    def test_xmlrpc_dumps(self):
        self._test_request(params=('value',))
        self._test_request(params=('username', 'password'), methodname='login')
        self._test_request(params=('response', ), methodresponse='login')
        self._test_request(params=(u'pas\xa3',), encoding='utf-8')
        self._test_request(params=(None,), allow_none=1)
        self.assertRaises(TypeError, self._test_request)
        self.assertRaises(TypeError, self._test_request, params=(None,))

    def test_latin1(self):
        self._test_request(params=(u'pas\xa3',), encoding='latin')


if __name__ == "__main__":
    unittest.main()
