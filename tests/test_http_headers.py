import unittest
import copy

from scrapy.http import Headers

class HeadersTest(unittest.TestCase):

    def assertSortedEqual(self, first, second, msg=None):
        return self.assertEqual(sorted(first), sorted(second), msg)

    def test_basics(self):
        h = Headers({'Content-Type': 'text/html', 'Content-Length': 1234})
        assert h['Content-Type']
        assert h['Content-Length']

        self.assertRaises(KeyError, h.__getitem__, 'Accept')
        self.assertEqual(h.get('Accept'), None)
        self.assertEqual(h.getlist('Accept'), [])

        self.assertEqual(h.get('Accept', '*/*'), '*/*')
        self.assertEqual(h.getlist('Accept', '*/*'), ['*/*'])
        self.assertEqual(h.getlist('Accept', ['text/html', 'images/jpeg']), ['text/html','images/jpeg'])

    def test_single_value(self):
        h = Headers()
        h['Content-Type'] = 'text/html'
        self.assertEqual(h['Content-Type'], 'text/html')
        self.assertEqual(h.get('Content-Type'), 'text/html')
        self.assertEqual(h.getlist('Content-Type'), ['text/html'])

    def test_multivalue(self):
        h = Headers()

        h['X-Forwarded-For'] = hlist = ['ip1', 'ip2']
        self.assertEqual(h['X-Forwarded-For'], 'ip2')
        self.assertEqual(h.get('X-Forwarded-For'), 'ip2')
        self.assertEqual(h.getlist('X-Forwarded-For'), hlist)
        assert h.getlist('X-Forwarded-For') is not hlist

    def test_encode_utf8(self):
        h = Headers({u'key': u'\xa3'}, encoding='utf-8')
        key, val = dict(h).items()[0]
        assert isinstance(key, str), key
        assert isinstance(val[0], str), val[0]
        self.assertEqual(val[0], '\xc2\xa3')

    def test_encode_latin1(self):
        h = Headers({u'key': u'\xa3'}, encoding='latin1')
        key, val = dict(h).items()[0]
        self.assertEqual(val[0], '\xa3')

    def test_encode_multiple(self):
        h = Headers({u'key': [u'\xa3']}, encoding='utf-8')
        key, val = dict(h).items()[0]
        self.assertEqual(val[0], '\xc2\xa3')

    def test_delete_and_contains(self):
        h = Headers()

        h['Content-Type'] = 'text/html'
        assert 'Content-Type' in h

        del h['Content-Type']
        assert 'Content-Type' not in h

    def test_setdefault(self):
        h = Headers()
        hlist = ['ip1', 'ip2']
        olist = h.setdefault('X-Forwarded-For', hlist)
        assert h.getlist('X-Forwarded-For') is not hlist
        assert h.getlist('X-Forwarded-For') is olist

        h = Headers()
        olist = h.setdefault('X-Forwarded-For', 'ip1')
        self.assertEqual(h.getlist('X-Forwarded-For'), ['ip1'])
        assert h.getlist('X-Forwarded-For') is olist

    def test_iterables(self):
        idict = {'Content-Type': 'text/html', 'X-Forwarded-For': ['ip1', 'ip2']}

        h = Headers(idict)
        self.assertDictEqual(dict(h),
                             {'Content-Type': ['text/html'], 'X-Forwarded-For': ['ip1', 'ip2']})
        self.assertSortedEqual(h.keys(), ['X-Forwarded-For', 'Content-Type'])
        self.assertSortedEqual(h.items(), [('X-Forwarded-For', ['ip1', 'ip2']), ('Content-Type', ['text/html'])])
        self.assertSortedEqual(h.iteritems(), [('X-Forwarded-For', ['ip1', 'ip2']), ('Content-Type', ['text/html'])])

        self.assertSortedEqual(h.values(), ['ip2', 'text/html'])

    def test_update(self):
        h = Headers()
        h.update({'Content-Type': 'text/html', 'X-Forwarded-For': ['ip1', 'ip2']})
        self.assertEqual(h.getlist('Content-Type'), ['text/html'])
        self.assertEqual(h.getlist('X-Forwarded-For'), ['ip1', 'ip2'])

    def test_copy(self):
        h1 = Headers({'header1': ['value1', 'value2']})
        h2 = copy.copy(h1)
        self.assertEqual(h1, h2)
        self.assertEqual(h1.getlist('header1'), h2.getlist('header1'))
        assert h1.getlist('header1') is not h2.getlist('header1')
        assert isinstance(h2, Headers)

    def test_appendlist(self):
        h1 = Headers({'header1': 'value1'})
        h1.appendlist('header1', 'value3')
        self.assertEqual(h1.getlist('header1'), ['value1', 'value3'])

        h1 = Headers()
        h1.appendlist('header1', 'value1')
        h1.appendlist('header1', 'value3')
        self.assertEqual(h1.getlist('header1'), ['value1', 'value3'])

    def test_setlist(self):
        h1 = Headers({'header1': 'value1'})
        self.assertEqual(h1.getlist('header1'), ['value1'])
        h1.setlist('header1', ['value2', 'value3'])
        self.assertEqual(h1.getlist('header1'), ['value2', 'value3'])

    def test_setlistdefault(self):
        h1 = Headers({'header1': 'value1'})
        h1.setlistdefault('header1', ['value2', 'value3'])
        h1.setlistdefault('header2', ['value2', 'value3'])
        self.assertEqual(h1.getlist('header1'), ['value1'])
        self.assertEqual(h1.getlist('header2'), ['value2', 'value3'])

    def test_none_value(self):
        h1 = Headers()
        h1['foo'] = 'bar'
        h1['foo'] = None
        h1.setdefault('foo', 'bar')
        self.assertEqual(h1.get('foo'), None)
        self.assertEqual(h1.getlist('foo'), [])
