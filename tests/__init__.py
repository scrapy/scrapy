"""
tests: this package contains all Scrapy unittests

see http://doc.scrapy.org/en/latest/contributing.html#running-tests
"""

import os

# ignore system-wide proxies for tests
# which would send requests to a totally unsuspecting server
# (e.g. because urllib does not fully understand the proxy spec)
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['ftp_proxy'] = ''

try:
    import unittest.mock as mock
except ImportError:
    import mock

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
