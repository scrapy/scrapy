import unittest

from scrapyd.utils import get_crawl_args

class UtilsTest(unittest.TestCase):

    def test_get_crawl_args(self):
        msg = {'project': 'lolo', 'spider': 'lala'}
        self.assertEqual(get_crawl_args(msg), ['lala'])
        msg = {'project': 'lolo', 'spider': 'lala', 'arg1': u'val1'}
        cargs = get_crawl_args(msg)
        self.assertEqual(cargs, ['lala', '-a', 'arg1=val1'])
        assert all(isinstance(x, str) for x in cargs), cargs
