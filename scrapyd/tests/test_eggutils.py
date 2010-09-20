import pkgutil, unittest
from cStringIO import StringIO

from scrapyd.eggutils import get_spider_list_from_eggfile

class EggUtilsTest(unittest.TestCase):

    def test_get_spider_list_from_eggfile(self):
        eggfile = StringIO(pkgutil.get_data(__package__, 'mybot.egg'))
        spiders = get_spider_list_from_eggfile(eggfile, 'mybot')
        self.assertEqual(set(spiders), set(['spider1', 'spider2']))
