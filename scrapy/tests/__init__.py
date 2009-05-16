"""
scrapy.tests: this package contains all Scrapy unittests

To run all Scrapy unittests go to Scrapy main dir and type: 

    bin/runtests.sh
    
If you're in windows use runtests.bat instead.

Keep in mind that some tests may be skipped if you don't have some (optional)
modules available like MySQLdb or simplejson, but that's not a problem.
"""

import os

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
