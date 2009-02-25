import unittest

from scrapy.http import Headers

class HeadersTest(unittest.TestCase):
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
        self.assertEqual(dict(h), {'Content-Type': ['text/html'], 'X-Forwarded-For': ['ip1', 'ip2']})
        self.assertEqual(h.keys(), ['X-Forwarded-For', 'Content-Type'])
        self.assertEqual(h.items(), [('X-Forwarded-For', 'ip2'), ('Content-Type', 'text/html')])
        self.assertEqual(list(h.iteritems()),
                [('X-Forwarded-For', 'ip2'), ('Content-Type', 'text/html')])

        self.assertEqual(h.values(), ['ip2', 'text/html'])
        self.assertEqual(h.lists(),
                [('X-Forwarded-For', ['ip1', 'ip2']), ('Content-Type', ['text/html'])])

    def test_update(self):
        h = Headers()
        h.update({'Content-Type': 'text/html', 'X-Forwarded-For': ['ip1', 'ip2']})
        self.assertEqual(h.getlist('Content-Type'), ['text/html'])
        self.assertEqual(h.getlist('X-Forwarded-For'), ['ip1', 'ip2'])


