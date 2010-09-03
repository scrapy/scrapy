import unittest

from zope.interface.verify import verifyObject

from scrapy.interfaces import ISpiderQueue
from scrapy.spiderqueue import SqliteSpiderQueue

class SpiderQueueTest(unittest.TestCase):

    def test_interface(self):
        verifyObject(ISpiderQueue, SqliteSpiderQueue())

