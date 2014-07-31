"""
tests: this package contains all Scrapy unittests

see http://doc.scrapy.org/en/latest/contributing.html#running-tests
"""

import os

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
