"""
scrapy.tests: this package contains all Scrapy unittests

To run all Scrapy unittests type: 

    python -m scrapy.tests.run

Keep in mind that some tests may be skipped if you don't have some (optional)
modules available like MySQLdb or simplejson.
"""

import os

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
