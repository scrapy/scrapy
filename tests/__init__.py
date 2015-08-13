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

# Absolutize paths to coverage config and output file because tests that
# spawn subprocesses also changes current working directory.
_sourceroot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if 'COV_CORE_CONFIG' in os.environ:
    os.environ['COVERAGE_FILE'] = os.path.join(_sourceroot, '.coverage')
    os.environ['COV_CORE_CONFIG'] = os.path.join(_sourceroot,
                                                 os.environ['COV_CORE_CONFIG'])

try:
    import unittest.mock as mock
except ImportError:
    import mock

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
