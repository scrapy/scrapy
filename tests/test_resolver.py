import time
from unittest import TestCase
try:
    from unittest import mock
except ImportError:
    import mock

from scrapy.resolver import dnscache


class DNSCache(TestCase):
    def setUp(self):
        self._original_expiration = dnscache.expiration

    def test_expiration(self):
        dnscache.expiration = 100

        now = time.time()
        later = now + 50
        after_expiration = now + 110

        with mock.patch('time.time', return_value=now):
            dnscache['example.com'] = '10.20.30.40'

        with mock.patch('time.time', return_value=later):
            assert dnscache['example.com'] == '10.20.30.40'

        with mock.patch('time.time', return_value=after_expiration):
            with self.assertRaises(KeyError):
                dnscache['example.com']

    def tearDown(self):
        dnscache.expiration = self._original_expiration
