"""
scrapy.tests: this package contains all Scrapy unittests

To run all Scrapy unittests go to Scrapy main dir and type: 

    bin/runtests.sh
    
If you're in windows use runtests.bat instead.
"""

import os

tests_datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sample_data')

def get_testdata(*paths):
    """Return test data"""
    path = os.path.join(tests_datadir, *paths)
    return open(path, 'rb').read()
