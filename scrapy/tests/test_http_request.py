import cgi
import unittest
import xmlrpclib
from cStringIO import StringIO
from urlparse import urlparse

from scrapy.http import Request, FormRequest, XmlRpcRequest, Headers, HtmlResponse


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
        headers = {"caca": "coco"}
        r = self.request_class("http://www.example.com", meta=meta, headers=headers, body="a body")

        assert r.meta is not meta
        self.assertEqual(r.meta, meta)
        assert r.headers is not headers
        self.assertEqual(r.headers["caca"], "coco")

    def test_url_no_scheme(self):
        self.assertRaises(ValueError, self.request_class, 'foo')

    def test_headers(self):
        # Different ways of setting headers attribute
        url = 'http://www.scrapy.org'
        headers = {'Accept':'gzip', 'Custom-Header':'nothing to tell you'}
        r = self.request_class(url=url, headers=headers)
        p = self.request_class(url=url, headers=r.headers)

        self.assertEqual(r.headers, p.headers)
        self.assertFalse(r.headers is headers)
        self.assertFalse(p.headers is r.headers)

        # headers must not be unicode
        h = Headers({'key1': u'val1', u'key2': 'val2'})
        h[u'newkey'] = u'newval'
        for k, v in h.iteritems():
            self.assert_(isinstance(k, str))
            for s in v:
                self.assert_(isinstance(s, str))

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
        self.assertEqual(r.url, "http://www.scrapy.org/path")

        # url quoting on creation
        r = self.request_class(url="http://www.scrapy.org/blank%20space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")
        r = self.request_class(url="http://www.scrapy.org/blank space")
        self.assertEqual(r.url, "http://www.scrapy.org/blank%20space")

        # url encoding
        r1 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="utf-8")
        r2 = self.request_class(url=u"http://www.scrapy.org/price/\xa3", encoding="latin1")
        self.assertEqual(r1.url, "http://www.scrapy.org/price/%C2%A3")
        self.assertEqual(r2.url, "http://www.scrapy.org/price/%A3")

    def test_body(self):
        r1 = self.request_class(url="http://www.example.com/")
        assert r1.body == ''

        r2 = self.request_class(url="http://www.example.com/", body="")
        assert isinstance(r2.body, str)
        self.assertEqual(r2.encoding, 'utf-8') # default encoding

        r3 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='utf-8')
        assert isinstance(r3.body, str)
        self.assertEqual(r3.body, "Price: \xc2\xa3100")

        r4 = self.request_class(url="http://www.example.com/", body=u"Price: \xa3100", encoding='latin1')
        assert isinstance(r4.body, str)
        self.assertEqual(r4.body, "Price: \xa3100")

    def test_ajax_url(self):
        # ascii url
        r = self.request_class(url="http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, "http://www.example.com/ajax.html?_escaped_fragment_=key=value")
        # unicode url
        r = self.request_class(url=u"http://www.example.com/ajax.html#!key=value")
        self.assertEqual(r.url, "http://www.example.com/ajax.html?_escaped_fragment_=key=value")

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
        r2 = r1.replace(method="POST", body="New body", headers=hdrs)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual((r1.method, r2.method), ("GET", "POST"))
        self.assertEqual((r1.body, r2.body), ('', "New body"))
        self.assertEqual((r1.headers, r2.headers), (self.default_headers, hdrs))

        # Empty attributes (which may fail if not compared properly)
        r3 = self.request_class("http://www.example.com", meta={'a': 1}, dont_filter=True)
        r4 = r3.replace(url="http://www.example.com/2", body='', meta={}, dont_filter=False)
        self.assertEqual(r4.url, "http://www.example.com/2")
        self.assertEqual(r4.body, '')
        self.assertEqual(r4.meta, {})
        assert r4.dont_filter is False

    def test_method_always_str(self):
        r = self.request_class("http://www.example.com", method=u"POST")
        assert isinstance(r.method, str)


class FormRequestTest(RequestTest):

    request_class = FormRequest

    def test_empty_formdata(self):
        r1 = self.request_class("http://www.example.com", formdata={})
        self.assertEqual(r1.body, '')

    def test_default_encoding(self):
        # using default encoding (utf-8)
        data = {'one': 'two', 'price': '\xc2\xa3 100'}
        r2 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r2.method, 'POST')
        self.assertEqual(r2.encoding, 'utf-8')
        self.assertEqual(r2.body, 'price=%C2%A3+100&one=two')
        self.assertEqual(r2.headers['Content-Type'], 'application/x-www-form-urlencoded')

    def test_custom_encoding(self):
        data = {'price': u'\xa3 100'}
        r3 = self.request_class("http://www.example.com", formdata=data, encoding='latin1')
        self.assertEqual(r3.encoding, 'latin1')
        self.assertEqual(r3.body, 'price=%A3+100')

    def test_multi_key_values(self):
        # using multiples values for a single key
        data = {'price': u'\xa3 100', 'colours': ['red', 'blue', 'green']}
        r3 = self.request_class("http://www.example.com", formdata=data)
        self.assertEqual(r3.body, 'colours=red&colours=blue&colours=green&price=%C2%A3+100')

    def test_from_response_post(self):
        respbody = """
<form action="post.php" method="POST">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'one': ['two', 'three'], 'six': 'seven'}, callback=lambda x: x)
        self.assertEqual(r1.method, 'POST')
        self.assertEqual(r1.headers['Content-type'], 'application/x-www-form-urlencoded')
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(r1.url, "http://www.example.com/this/post.php")
        self.assertEqual(set([f.value for f in fs["test"]]), set(["val1", "val2"]))
        self.assertEqual(set([f.value for f in fs["one"]]), set(["two", "three"]))
        self.assertEqual(fs['test2'].value, 'xxx')
        self.assertEqual(fs['six'].value, 'seven')

    def test_from_response_extra_headers(self):
        respbody = """
<form action="post.php" method="POST">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        headers = {"Accept-Encoding": "gzip,deflate"}
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'one': ['two', 'three'], 'six': 'seven'}, headers=headers, callback=lambda x: x)
        self.assertEqual(r1.method, 'POST')
        self.assertEqual(r1.headers['Content-type'], 'application/x-www-form-urlencoded')
        self.assertEqual(r1.headers['Accept-Encoding'], 'gzip,deflate')

    def test_from_response_get(self):
        respbody = """
<form action="get.php" method="GET">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'one': ['two', 'three'], 'six': 'seven'})
        self.assertEqual(r1.method, 'GET')
        self.assertEqual(urlparse(r1.url).hostname, "www.example.com")
        self.assertEqual(urlparse(r1.url).path, "/this/get.php")
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertEqual(set(urlargs['test']), set(['val1', 'val2']))
        self.assertEqual(set(urlargs['one']), set(['two', 'three']))
        self.assertEqual(urlargs['test2'], ['xxx'])
        self.assertEqual(urlargs['six'], ['seven'])

    def test_from_response_override_params(self):
        respbody = """
<form action="get.php" method="POST">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="3">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'two': '2'})
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(fs['one'].value, '1')
        self.assertEqual(fs['two'].value, '2')

    def test_from_response_submit_first_clickable(self):
        respbody = """
<form action="get.php" method="GET">
<input type="submit" name="clickable1" value="clicked1">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="3">
<input type="submit" name="clickable2" value="clicked2">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'two': '2'})
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertEqual(urlargs['clickable1'], ['clicked1'])
        self.assertFalse('clickable2' in urlargs, urlargs)
        self.assertEqual(urlargs['one'], ['1'])
        self.assertEqual(urlargs['two'], ['2'])

    def test_from_response_submit_not_first_clickable(self):
        respbody = """
<form action="get.php" method="GET">
<input type="submit" name="clickable1" value="clicked1">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="3">
<input type="submit" name="clickable2" value="clicked2">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'two': '2'}, clickdata={'name': 'clickable2'})
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertEqual(urlargs['clickable2'], ['clicked2'])
        self.assertFalse('clickable1' in urlargs, urlargs)
        self.assertEqual(urlargs['one'], ['1'])
        self.assertEqual(urlargs['two'], ['2'])

    def test_from_response_multiple_clickdata(self):
        respbody = """
<form action="get.php" method="GET">
<input type="submit" name="clickable" value="clicked1">
<input type="submit" name="clickable" value="clicked2">
<input type="hidden" name="one" value="clicked1">
<input type="hidden" name="two" value="clicked2">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, \
                clickdata={'name': 'clickable', 'value': 'clicked2'})
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertEqual(urlargs['clickable'], ['clicked2'])
        self.assertEqual(urlargs['one'], ['clicked1'])
        self.assertEqual(urlargs['two'], ['clicked2'])

    def test_from_response_unicode_clickdata(self):
        body = u"""
<form action="get.php" method="GET">
<input type="submit" name="price in \u00a3" value="\u00a3 1000">
<input type="submit" name="price in \u20ac" value="\u20ac 2000">
<input type="hidden" name="poundsign" value="\u00a3">
<input type="hidden" name="eurosign" value="\u20ac">
</form>
        """
        response = HtmlResponse("http://www.example.com", body=body, \
                                encoding='utf-8')
        r1 = self.request_class.from_response(response, \
                clickdata={'name': u'price in \u00a3'})
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertTrue(urlargs[u'price in \u00a3'.encode('utf-8')])

    def test_from_response_with_select(self):
        body = u"""
        <form name="form1">
          <select name="inputname"><option selected="selected" value="inputvalue">text</option></select>
          <input type="submit" name="clickable" value="clicked">
        </form>
        """
        res = HtmlResponse("http://example.com", body=body, encoding='utf-8')
        req = self.request_class.from_response(res)
        urlargs = cgi.parse_qs(urlparse(req.url).query)
        self.assertEqual(urlargs['inputname'], ['inputvalue'])

    def test_from_response_multiple_forms_clickdata(self):
        body = u"""
        <form name="form1">
          <input type="submit" name="clickable" value="clicked1">
          <input type="hidden" name="field1" value="value1">
        </form>
        <form name="form2">
          <input type="submit" name="clickable" value="clicked2">
          <input type="hidden" name="field2" value="value2">
        </form>
        """
        res = HtmlResponse("http://example.com", body=body, encoding='utf-8')
        req = self.request_class.from_response(res, formname='form2', \
                clickdata={'name': 'clickable'})
        urlargs = cgi.parse_qs(urlparse(req.url).query)
        self.assertEqual(urlargs['clickable'], ['clicked2'])
        self.assertEqual(urlargs['field2'], ['value2'])
        self.assertFalse('field1' in urlargs, urlargs)

    def test_from_response_override_clickable(self):
        body = u'<form><input type="submit" name="clickme" value="one"></form>'
        res = HtmlResponse("http://example.com", body=body, encoding='utf-8')
        req = self.request_class.from_response(res, \
                                               formdata={'clickme': 'two'}, \
                                               clickdata={'name': 'clickme'})
        urlargs = cgi.parse_qs(urlparse(req.url).query)
        self.assertEqual(urlargs['clickme'], ['two'])

    def test_from_response_dont_click(self):
        respbody = """
<form action="get.php" method="GET">
<input type="submit" name="clickable1" value="clicked1">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="3">
<input type="submit" name="clickable2" value="clicked2">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        r1 = self.request_class.from_response(response, dont_click=True)
        urlargs = cgi.parse_qs(urlparse(r1.url).query)
        self.assertFalse('clickable1' in urlargs, urlargs)
        self.assertFalse('clickable2' in urlargs, urlargs)

    def test_from_response_ambiguous_clickdata(self):
        respbody = """
<form action="get.php" method="GET">
<input type="submit" name="clickable1" value="clicked1">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="3">
<input type="submit" name="clickable2" value="clicked2">
</form>
        """
        response = HtmlResponse("http://www.example.com/this/list.html", body=respbody)
        self.assertRaises(ValueError,
                          self.request_class.from_response,
                          response,
                          clickdata={'type': 'submit'})

    def test_from_response_non_matching_clickdata(self):
        body = """
        <form>
          <input type="submit" name="clickable" value="clicked">
        </form>
        """
        res = HtmlResponse("http://example.com", body=body)
        self.assertRaises(ValueError,
                          self.request_class.from_response, res,
                                clickdata={'nonexistent': 'notme'})

    def test_from_response_errors_noform(self):
        respbody = """<html></html>"""
        response = HtmlResponse("http://www.example.com/lala.html", body=respbody)
        self.assertRaises(ValueError, self.request_class.from_response, response)

    def test_from_response_errors_formnumber(self):
        respbody = """
<form action="get.php" method="GET">
<input type="hidden" name="test" value="val1">
<input type="hidden" name="test" value="val2">
<input type="hidden" name="test2" value="xxx">
</form>
        """
        response = HtmlResponse("http://www.example.com/lala.html", body=respbody)
        self.assertRaises(IndexError, self.request_class.from_response, response, formnumber=1)

    def test_from_response_noformname(self):
        respbody = """
<form action="post.php" method="POST">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="2">
</form>
        """
        response = HtmlResponse("http://www.example.com/formname.html", body=respbody)
        r1 = self.request_class.from_response(response, formdata={'two':'3'}, callback=lambda x: x)
        self.assertEqual(r1.method, 'POST')
        self.assertEqual(r1.headers['Content-type'], 'application/x-www-form-urlencoded')
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(fs['one'].value, '1')
        self.assertEqual(fs['two'].value, '3')


    def test_from_response_formname_exists(self):
        respbody = """
<form action="post.php" method="POST">
<input type="hidden" name="one" value="1">
<input type="hidden" name="two" value="2">
</form>
<form name="form2" action="post.php" method="POST">
<input type="hidden" name="three" value="3">
<input type="hidden" name="four" value="4">
</form>
        """
        response = HtmlResponse("http://www.example.com/formname.html", body=respbody)
        r1 = self.request_class.from_response(response, formname="form2", callback=lambda x: x)
        self.assertEqual(r1.method, 'POST')
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(fs['three'].value, "3")
        self.assertEqual(fs['four'].value, "4")

    def test_from_response_formname_notexist(self):
        respbody = """
<form name="form1" action="post.php" method="POST">
<input type="hidden" name="one" value="1">
</form>
<form name="form2" action="post.php" method="POST">
<input type="hidden" name="two" value="2">
</form>
        """
        response = HtmlResponse("http://www.example.com/formname.html", body=respbody)
        r1 = self.request_class.from_response(response, formname="form3", callback=lambda x: x)
        self.assertEqual(r1.method, 'POST')
        fs = cgi.FieldStorage(StringIO(r1.body), r1.headers, environ={"REQUEST_METHOD": "POST"})
        self.assertEqual(fs['one'].value, "1")

    def test_from_response_formname_errors_formnumber(self):
        respbody = """
<form name="form1" action="post.php" method="POST">
<input type="hidden" name="one" value="1">
</form>
<form name="form2" action="post.php" method="POST">
<input type="hidden" name="two" value="2">
</form>
        """
        response = HtmlResponse("http://www.example.com/formname.html", body=respbody)
        self.assertRaises(IndexError, self.request_class.from_response, response, formname="form3", formnumber=2)

    def test_from_response_missed_value(self):
        respbody = """
<form action="get.php" method="POST">
    <input type="hidden" name="key1" value="val1">
    <input type="hidden" name="key2">
    <input type="radio" name="key3" checked>
    <input type="checkbox" name="key4" checked>
    <textarea name="key5">val5</textarea>
    <textarea name="key6"/>
    <select name="key7">
        <option name="opt1" selected></option>
        <option name="opt2">opt2</option>
    </select>
    <input type="submit" value="val8">
</form>
        """
        res = HtmlResponse("http://example.com", body=respbody, encoding='utf-8')
        req = self.request_class.from_response(res)
        fs = cgi.parse_qs(req.body, True)
        self.assertEqual(fs['key1'], ['val1'])
        self.assertEqual(fs['key2'], [''])
        self.assertEqual(fs['key3'], ['on'])
        self.assertEqual(fs['key4'], ['on'])
        self.assertEqual(fs['key5'], ['val5'])
        self.assertEqual(fs['key6'], [''])
        self.assertEqual(fs['key7'], [''])
        self.assertEqual(set(fs), set(['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']))

class XmlRpcRequestTest(RequestTest):

    request_class = XmlRpcRequest
    default_method = 'POST'
    default_headers = {'Content-Type': ['text/xml']}

    def _test_request(self, **kwargs):
        r = self.request_class('http://scrapytest.org/rpc2', **kwargs)
        self.assertEqual(r.headers['Content-Type'], 'text/xml')
        self.assertEqual(r.body, xmlrpclib.dumps(**kwargs))
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
