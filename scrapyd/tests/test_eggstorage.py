from cStringIO import StringIO

from twisted.trial import unittest

from zope.interface.verify import verifyObject

from scrapyd.interfaces import IEggStorage
from scrapyd.config import Config
from scrapyd.eggstorage import FilesystemEggStorage

class EggStorageTest(unittest.TestCase):

    def setUp(self):
        d = self.mktemp()
        config = Config(values={'eggs_dir': d})
        self.eggst = FilesystemEggStorage(config)

    def test_interface(self):
        verifyObject(IEggStorage, self.eggst)

    def test_put_get_list_delete(self):
        self.eggst.put(StringIO("egg01"), 'mybot', '01')
        self.eggst.put(StringIO("egg03"), 'mybot', '03')
        self.eggst.put(StringIO("egg02"), 'mybot', '02')

        self.assertEqual(self.eggst.list('mybot'), ['01', '02', '03'])
        self.assertEqual(self.eggst.list('mybot2'), [])

        v, f = self.eggst.get('mybot')
        self.assertEqual(v, "03")
        self.assertEqual(f.read(), "egg03")
        f.close()

        v, f = self.eggst.get('mybot', '02')
        self.assertEqual(v, "02")
        self.assertEqual(f.read(), "egg02")
        f.close()

        self.eggst.delete('mybot', '02')
        self.assertEqual(self.eggst.list('mybot'), ['01', '03'])

        self.eggst.delete('mybot')
        self.assertEqual(self.eggst.list('mybot'), [])
