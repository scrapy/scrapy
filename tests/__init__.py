"""
tests: this package contains all Scrapy unittests

see https://docs.scrapy.org/en/latest/contributing.html#running-tests
"""

import os
from pathlib import Path

# ignore system-wide proxies for tests
# which would send requests to a totally unsuspecting server
# (e.g. because urllib does not fully understand the proxy spec)
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['ftp_proxy'] = ''

# Absolutize paths to coverage config and output file because tests that
# spawn subprocesses also changes current working directory.
_sourceroot = Path(__file__).resolve().parents[1]
if 'COV_CORE_CONFIG' in os.environ:
    os.environ['COVERAGE_FILE'] = str(_sourceroot / '.coverage')
    os.environ['COV_CORE_CONFIG'] = str(_sourceroot / os.environ['COV_CORE_CONFIG'])

tests_datadir = Path(__file__).resolve().with_name('sample_data')


def get_testdata(*paths):
    """Return test data"""
    return tests_datadir.joinpath(*paths).read_bytes()
