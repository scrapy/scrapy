from twisted.trial import unittest
from zope.interface.verify import verifyObject

from scrapy.contrib.spidercontext import ISpiderContextStorage, SqliteSpiderContextStorage

class SqliteSpiderContextStorageTest(unittest.TestCase):

    def test_interface(self):
        verifyObject(ISpiderContextStorage, SqliteSpiderContextStorage())
