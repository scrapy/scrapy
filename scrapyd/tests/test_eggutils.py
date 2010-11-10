import unittest
from cStringIO import StringIO

from scrapyd.eggutils import get_spider_list_from_eggfile
from scrapy.utils.py26 import get_data

__package__ = 'scrapyd.tests' # required for compatibility with python 2.5

class EggUtilsTest(unittest.TestCase):

    def test_get_spider_list_from_eggfile(self):
        eggfile = StringIO(get_data(__package__, 'mybot.egg'))
        spiders = get_spider_list_from_eggfile(eggfile, 'mybot')
        self.assertEqual(set(spiders), set(['spider1', 'spider2']))
