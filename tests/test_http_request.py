import unittest
from six.moves import xmlrpc_client as xmlrpclib
from six.moves.urllib.parse import urlparse
import w3lib.parse

from scrapy.http import Request, FormRequest, XmlRpcRequest, Headers, HtmlResponse
from scrapy.utils.python import unicode_to_str


class RequestTest(unittest.TestCase):

    request_class = Request
    default_method = 'GET'
    default_headers = Headers()
    default_meta = {}

    def test_init(self):
        # Request requires url in the constructor
        self.assertRaises(Exception, self.request_class)

        # url argument must be a string
        self.assertRaises(TypeError, self.request_class, 123)
        r = self.request_class('http://www.example.com')

        r = self.request_class("http://www.example.com")
        assert isinstance(r.url, bytes)
        self.assertEqual(r.url, b"http://www.example.com")
        self.assertEqual(r.method, self.default_method)

        assert isinstance(r.headers, Headers)
        self.assertEqual(r.headers, self.default_headers)
        self.assertEqual(r.meta, self.default_meta)

        meta = {"lala": "lolo"}
        headers = {"caca": "coco"}
        r = self.request_class("http://www.example.com", meta=meta, headers=headers, body=b"a body")

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers["caca"], b"coco")

    def test_url_no_scheme(self):
        self.assertRaises(ValueError, self.request_class, 'foo')

    def test_headers(self):
        # Different ways of setting headers attribute
        url = 'http://www.scrapy.org'
        headers = {b'Accept': b'gzip', b'Custom-Header': b'nothing to tell you'}
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
        """Request url tests"""
        r = self.request_class(url="http://www.scrapy.org/path")
        self.assertEqual(r.url, b"http://www.scrapy.org/path")

        # url quoting on creation
        r = self.request_class(url="http://www.scrapy.org/blank%20space")
        self.assertEqual(r.url, b"http://www.scrapy.org/blank%20space")
        r = self.request_class(url="http://www.scrapy.org/blank space")
        self.assertEqual(r.url, b"http://www.scrapy.org/blank%20space")

        # url encoding
        r1 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="utf-8")
        r2 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="latin1")
        self.assertEqual(r1.url, b"http://www.scrapy.org/price/%C2%A3")
        self.assertEqual(r2.url, b"http://www.scrapy.org/price/%A3")

    def test_body(self):
        r1 = self.request_class(url="http://www.example.com/")
        self.assertEqual(r1.body, b'')

        r2 = self.request_class(url="http://www.example.com/", body=b"")
        self.assertIsInstance(r2.body, bytes)
        self.assertEqual(r2.encoding, 'utf-8') # default encoding

        r3 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='utf-8')
        self.assertIsInstance(r3.body, bytes)
        self.assertEqual(r3.body, b"Price: \xc2\xa3100")

        r4 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='latin1')
        self.assertIsInstance(r4.body, bytes)
        self.assertEqual(r4.body, b"Price: \xa3100")

    def test_ajax_url(self):
        # ascii url
        r = self.request_class(url="http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, b"http://www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue")
        # unicode url
        r = self.request_class(url=u"http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, b"http://www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue")

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
        hdrs = Headers(dict(r1.headers, key='value'))
        r2 = r1.replace(method="POST", body=b"New body", headers=hdrs)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.method, r2.method), ("GET", "POST"))
        self.assertEqual((r1.body, r2.body), (b'', b"New body"))
        self.assertEqual((r1.headers, r2.headers), (self.default_headers, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = self.request_class("http://www.example.com", meta={'a': 1}, dont_filter=True)
        r4 = r3.replace(url="http://www.example.com/2", body='', meta={}, dont_filter=False)
        self.assertEqual(r4.url, b"http://www.example.com/2")
        self.assertEqual(r4.body, b'')
        self.assertEqual(r4.meta, {})
        assert r4.dont_filter is False

    def test_method_always_str(self):
        r = self.request_class("http://www.example.com", method=u"POST")
        assert isinstance(r.method, str)  # "native string"

    def test_immutable_attributes(self):
        r = self.request_class("http://example.com")
        self.assertRaises(AttributeError, setattr, r, 'url', 'http://example2.com')
        self.assertRaises(AttributeError, setattr, r, 'body', 'xxx')


class FormRequestTest(RequestTest):

    request_class = FormRequest

    def assertSortedEqual(self, first, second, msg=None):
        return self.assertEqual(sorted(first), sorted(second), msg)

    def test_empty_formdata(self):
        r1 = self.request_class("http://www.example.com", formdata={})
        self.assertEqual(r1.body, b'')

    def test_default_encoding(self):
        # using default encoding (utf-8)
        data = {b'one': b'two', b'price': b'\xc2\xa3 100'}
        r2 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r2.method, 'POST')
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertSortedEqual(r2.body.split(b'&'),
                               b'price=%C2%A3+100&one=two'.split(b'&'))
        self.assertEqual(r2.headers['Content-Type'], b'application/x-www-form-urlencoded')

    def test_custom_encoding(self):
        data = {'price': u'\xa3 100'}
        r3 = self.request_class("http://www.example.com", formdata=data, encoding='latin1')
        self.assertEqual(r3.encoding, 'latin1')
        self.assertEqual(r3.body, b'price=%A3+100')

    def test_multi_key_values(self):
        # using multiples values for a single key
        data = {'price': u'\xa3 100', 'colours': ['red', 'blue', 'green']}
        r3 = self.request_class("http://www.example.com", formdata=data)
        self.assertSortedEqual(
            r3.body.split(b'&'),
            b'colours=red&colours=blue&colours=green&price=%C2%A3+100'.split(b'&'),
        )

    def test_from_response_post(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html")
        req = self.request_class.from_response(
            response,
            formdata={'one': ['two', 'three'], 'six': 'seven'},
        )
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'], b'application/x-www-form-urlencoded')
        self.assertEqual(req.url, b"http://www.example.com/this/post.php")
        fs = _qs(req)
        self.assertEqual(set(fs[b'test']), {b'val1', b'val2'})
        self.assertEqual(set(fs[b'one']), {b'two', b'three'})
        self.assertEqual(fs[b'test2'], [b'xxx'])
        self.assertEqual(fs[b'six'], [b'seven'])

    def test_from_response_extra_headers(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""")
        req = self.request_class.from_response(
            response,
            formdata={'one': ['two', 'three'], 'six': 'seven'},
            headers={"Accept-Encoding": "gzip,deflate"},
        )
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Content-type'],
                         b'application/x-www-form-urlencoded')
        self.assertEqual(req.headers['Accept-Encoding'], b'gzip,deflate')

    def test_from_response_get(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""",
            url="http://www.example.com/this/list.html")
        r1 = self.request_class.from_response(
            response,
            formdata={'one': ['two', 'three'], 'six': 'seven'},
        )
        self.assertEqual(r1.method, 'GET')
        self.assertEqual(urlparse(r1.url).hostname, b"www.example.com")
        self.assertEqual(urlparse(r1.url).path, b"/this/get.php")
        fs = _qs(r1)
        self.assertEqual(set(fs[b'test']), {b'val1', b'val2'})
        self.assertEqual(set(fs[b'one']), {b'two', b'three'})
        self.assertEqual(fs[b'test2'], [b'xxx'])
        self.assertEqual(fs[b'six'], [b'seven'])

    def test_from_response_override_params(self):
        response = _buildresponse(
            b"""<form action="get.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'})
        fs = _qs(req)
        self.assertEqual(fs[b'one'], [b'1'])
        self.assertEqual(fs[b'two'], [b'2'])

    def test_from_response_override_method(self):
        response = _buildresponse(
                b'''<html><body>
                <form action="/app"></form>
                </body></html>''')
        request = FormRequest.from_response(response)
        self.assertEqual(request.method, 'GET')
        request = FormRequest.from_response(response, method='POST')
        self.assertEqual(request.method, 'POST')

    def test_from_response_override_url(self):
        response = _buildresponse(
                b'''<html><body>
                <form action="/app"></form>
                </body></html>''')
        request = FormRequest.from_response(response)
        self.assertEqual(request.url, b'http://example.com/app')
        request = FormRequest.from_response(response, url='http://foo.bar/absolute')
        self.assertEqual(request.url, b'http://foo.bar/absolute')
        request = FormRequest.from_response(response, url='/relative')
        self.assertEqual(request.url, b'http://example.com/relative')

    def test_from_response_submit_first_clickable(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'})
        fs = _qs(req)
        self.assertEqual(fs[b'clickable1'], [b'clicked1'])
        self.assertFalse(b'clickable2' in fs, fs)
        self.assertEqual(fs[b'one'], [b'1'])
        self.assertEqual(fs[b'two'], [b'2'])

    def test_from_response_submit_not_first_clickable(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        req = self.request_class.from_response(response, formdata={'two': '2'},
                                               clickdata={'name': 'clickable2'})
        fs = _qs(req)
        self.assertEqual(fs[b'clickable2'], [b'clicked2'])
        self.assertFalse(b'clickable1' in fs, fs)
        self.assertEqual(fs[b'one'], [b'1'])
        self.assertEqual(fs[b'two'], [b'2'])

    def test_from_response_dont_submit_image_as_input(self):
        response = _buildresponse(
            b"""<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="image" name="i2" src="http://my.image.org/1.jpg">
            <input type="submit" name="i3" value="i3v">
            </form>""")
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        self.assertEqual(fs, {b'i1': [b'i1v']})

    def test_from_response_dont_submit_reset_as_input(self):
        response = _buildresponse(
            b"""<form>
            <input type="hidden" name="i1" value="i1v">
            <input type="text" name="i2" value="i2v">
            <input type="reset" name="resetme">
            <input type="submit" name="i3" value="i3v">
            </form>""")
        req = self.request_class.from_response(response, dont_click=True)
        fs = _qs(req)
        self.assertEqual(fs, {
            b'i1': [b'i1v'],
            b'i2': [b'i2v'],
        })

    def test_from_response_multiple_clickdata(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="submit" name="clickable" value="clicked1">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="one" value="clicked1">
            <input type="hidden" name="two" value="clicked2">
            </form>""")
        req = self.request_class.from_response(
            response,
            clickdata={'name': 'clickable', 'value': 'clicked2'},
        )
        fs = _qs(req)
        self.assertEqual(fs[b'clickable'], [b'clicked2'])
        self.assertEqual(fs[b'one'], [b'clicked1'])
        self.assertEqual(fs[b'two'], [b'clicked2'])

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
        self.assertTrue(fs[u'price in \u00a3'.encode('utf-8')])

    def test_from_response_multiple_forms_clickdata(self):
        response = _buildresponse(
            b"""<form name="form1">
            <input type="submit" name="clickable" value="clicked1">
            <input type="hidden" name="field1" value="value1">
            </form>
            <form name="form2">
            <input type="submit" name="clickable" value="clicked2">
            <input type="hidden" name="field2" value="value2">
            </form>
            """)
        req = self.request_class.from_response(
            response,
            formname='form2',
            clickdata={'name': 'clickable'},
        )
        fs = _qs(req)
        self.assertEqual(fs[b'clickable'], [b'clicked2'])
        self.assertEqual(fs[b'field2'], [b'value2'])
        self.assertNotIn(b'field1', fs)

    def test_from_response_override_clickable(self):
        response = _buildresponse(
            b'<form><input type="submit" name="clickme" value="one"> </form>'
        )
        req = self.request_class.from_response(
            response,
            formdata={'clickme': 'two'},
            clickdata={'name': 'clickme'},
        )
        fs = _qs(req)
        self.assertEqual(fs[b'clickme'], [b'two'])

    def test_from_response_dont_click(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="submit" name="clickable1" value="clicked1">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="3">
            <input type="submit" name="clickable2" value="clicked2">
            </form>""")
        r1 = self.request_class.from_response(response, dont_click=True)
        fs = _qs(r1)
        self.assertNotIn(b'clickable1', fs)
        self.assertNotIn(b'clickable2', fs)

    def test_from_response_ambiguous_clickdata(self):
        response = _buildresponse(
            b"""
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
            b"""<form>
            <input type="submit" name="clickable" value="clicked">
            </form>""")
        self.assertRaises(ValueError, self.request_class.from_response,
                          response, clickdata={'nonexistent': 'notme'})

    def test_from_response_nr_index_clickdata(self):
        response = _buildresponse(
            b"""<form>
            <input type="submit" name="clickable1" value="clicked1">
            <input type="submit" name="clickable2" value="clicked2">
            </form>
            """)
        req = self.request_class.from_response(response, clickdata={'nr': 1})
        fs = _qs(req)
        self.assertIn(b'clickable2', fs)
        self.assertNotIn(b'clickable1', fs)

    def test_from_response_invalid_nr_index_clickdata(self):
        response = _buildresponse(
            b"""<form>
            <input type="submit" name="clickable" value="clicked">
            </form>
            """)
        self.assertRaises(ValueError, self.request_class.from_response,
                          response, clickdata={'nr': 1})

    def test_from_response_errors_noform(self):
        response = _buildresponse(b"""<html></html>""")
        self.assertRaises(ValueError, self.request_class.from_response, response)

    def test_from_response_invalid_html5(self):
        response = _buildresponse(b"""<!DOCTYPE html><body></html><form>"""
                                  b"""<input type="text" name="foo" value="xxx">"""
                                  b"""</form></body></html>""")
        req = self.request_class.from_response(response, formdata={'bar': 'buz'})
        fs = _qs(req)
        self.assertEqual(fs, {
            b'foo': [b'xxx'],
            b'bar': [b'buz'],
        })

    def test_from_response_errors_formnumber(self):
        response = _buildresponse(
            b"""<form action="get.php" method="GET">
            <input type="hidden" name="test" value="val1">
            <input type="hidden" name="test" value="val2">
            <input type="hidden" name="test2" value="xxx">
            </form>""")
        self.assertRaises(IndexError, self.request_class.from_response, response, formnumber=1)

    def test_from_response_noformname(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>""")
        r1 = self.request_class.from_response(response, formdata={'two': '3'})
        self.assertEqual(r1.method, 'POST')
        self.assertEqual(r1.headers['Content-type'],
                         b'application/x-www-form-urlencoded')
        fs = _qs(r1)
        self.assertEqual(fs, {
            b'one': [b'1'],
            b'two': [b'3'],
        })

    def test_from_response_formname_exists(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
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
        self.assertEqual(fs, {
            b'four': [b'4'],
            b'three': [b'3']},
        )

    def test_from_response_formname_notexist(self):
        response = _buildresponse(
            b"""<form name="form1" action="post.php" method="POST">
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
            b"""<form name="form1" action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            </form>
            <form name="form2" action="post.php" method="POST">
            <input type="hidden" name="two" value="2">
            </form>""")
        self.assertRaises(IndexError, self.request_class.from_response,
                          response, formname="form3", formnumber=2)

    def test_from_response_select(self):
        res = _buildresponse(
            b'''<form>
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
        self.assertEqual(fs, {
            b'i1': [b'i1v2'],
            b'i2': [b'i2v1'],
            b'i4': [b'i4v2', b'i4v3'],
        })

    def test_from_response_radio(self):
        res = _buildresponse(
            b'''<form>
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
        self.assertEqual(fs, {
            b'i1': [b'iv2'],
            b'i2': [b'on'],
        })

    def test_from_response_checkbox(self):
        res = _buildresponse(
            b'''<form>
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
        self.assertEqual(fs, {
            b'i1': [b'iv2'],
            b'i2': [b'on'],
        })

    def test_from_response_input_text(self):
        res = _buildresponse(
            b'''<form>
            <input type="text" name="i1" value="i1v1">
            <input type="text" name="i2">
            <input type="text" value="i3v1">
            <input type="text">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {
            b'i1': [b'i1v1'],
            b'i2': [b''],
        })

    def test_from_response_input_hidden(self):
        res = _buildresponse(
            b'''<form>
            <input type="hidden" name="i1" value="i1v1">
            <input type="hidden" name="i2">
            <input type="hidden" value="i3v1">
            <input type="hidden">
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {
            b'i1': [b'i1v1'],
            b'i2': [b''],
        })

    def test_from_response_input_textarea(self):
        res = _buildresponse(
            b'''<form>
            <textarea name="i1">i1v</textarea>
            <textarea name="i2"></textarea>
            <textarea name="i3"/>
            <textarea>i4v</textarea>
            </form>''')
        req = self.request_class.from_response(res)
        fs = _qs(req)
        self.assertEqual(fs, {
            b'i1': [b'i1v'],
            b'i2': [b''],
            b'i3': [b''],
        })

    def test_from_response_descendants(self):
        res = _buildresponse(
            b'''<form>
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
        self.assertEqual(set(fs),
                         {b'h2', b'i2', b'i1', b'i3', b'h1', b'i5', b'i4'})

    def test_from_response_xpath(self):
        response = _buildresponse(
            b"""<form action="post.php" method="POST">
            <input type="hidden" name="one" value="1">
            <input type="hidden" name="two" value="2">
            </form>
            <form action="post2.php" method="POST">
            <input type="hidden" name="three" value="3">
            <input type="hidden" name="four" value="4">
            </form>""")
        r1 = self.request_class.from_response(
            response, formxpath="//form[@action='post.php']")
        fs = _qs(r1)
        self.assertEqual(fs.get(b'one'), [b'1'], fs)

        r1 = self.request_class.from_response(
            response, formxpath="//form/input[@name='four']")
        fs = _qs(r1)
        self.assertEqual(fs.get(b'three'), [b'3'], fs)

        self.assertRaises(ValueError, self.request_class.from_response,
                          response, formxpath="//form/input[@name='abc']")


def _buildresponse(body, **kwargs):
    kwargs.setdefault('body', body)
    kwargs.setdefault('url', 'http://example.com')
    kwargs.setdefault('encoding', 'utf-8')
    return HtmlResponse(**kwargs)


def _qs(req):
    if req.method == 'POST':
        qs = req.body
    else:
        qs = req.url.partition(b'?')[2]
    return w3lib.parse.parse_qs(qs, True)


class XmlRpcRequestTest(RequestTest):

    request_class = XmlRpcRequest
    default_method = 'POST'
    default_headers = Headers({'Content-Type': ['text/xml']})

    def _test_request(self, **kwargs):
        r = self.request_class('http://scrapytest.org/rpc2', **kwargs)
        xmlrpcbody = unicode_to_str(xmlrpclib.dumps(**kwargs), encoding=r.encoding)
        self.assertEqual(r.headers['Content-Type'], b'text/xml')
        self.assertEqual(r.body, xmlrpcbody)
        self.assertEqual(r.method, 'POST')
        self.assertEqual(r.encoding, kwargs.get('encoding', 'utf-8'))
        self.assertTrue(r.dont_filter, True)

    def test_xmlrpc_dumps(self):
        self._test_request(params=('value',))
        self._test_request(params=('username', 'password'), methodname='login')
        self._test_request(params=('response', ), methodresponse='login')
        self._test_request(params=(u'pas\xa3',), encoding='utf-8')
        self._test_request(params=(u'pas\xa3',), encoding='latin')
        self._test_request(params=(None,), allow_none=1)
        self.assertRaises(TypeError, self._test_request)
        self.assertRaises(TypeError, self._test_request, params=(None,))


if __name__ == "__main__":
    unittest.main()
