import re

import scrapy
from docs._ext.scrapylinkcode import resolve
from scrapy.utils.misc import set_environ
from twisted.trial import unittest


BASE_URL_PATTERN = re.escape('https://github.com/scrapy/scrapy/blob')
DOMAIN = 'py'
INFO = {'module': 'scrapy', 'fullname': 'Spider'}
PATH = 'scrapy/spiders/__init__.py'


def check_url(url, path=PATH, branch='master'):
    pattern = r'^{}/{}/{}#L\d+-L\d+$'.format(
        BASE_URL_PATTERN, re.escape(branch), re.escape(path))
    assert re.match(pattern, url) is not None


class TestCase(unittest.TestCase):

    def test_unexisting_object(self):
        info = {'module': 'scrapy.crawler', 'fullname': 'Crawler.settings'}
        assert resolve(DOMAIN, info) is None

    def test_property(self):
        info = {'module': 'scrapy.crawler', 'fullname': 'CrawlerRunner.crawlers'}
        assert resolve(DOMAIN, info) is None

    def test_local_build(self):
        url = resolve(DOMAIN, INFO)
        check_url(url)

    def test_master_build(self):
        with set_environ(READTHEDOCS_VERSION='master'):
            url = resolve(DOMAIN, INFO)
        check_url(url)

    def test_versioned_build(self):
        with set_environ(READTHEDOCS_VERSION='1.8'):
            url = resolve(DOMAIN, INFO)
        check_url(url, branch=scrapy.__version__)
