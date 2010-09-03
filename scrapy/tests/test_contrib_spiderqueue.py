import os

from twisted.trial import unittest
from zope.interface.verify import verifyObject

from scrapy.interfaces import ISpiderQueue

class SQSSpiderQueueTest(unittest.TestCase):

    try:
        import boto
    except ImportError, e:
        skip = str(e)
    
    if 'AWS_ACCESS_KEY_ID' not in os.environ:
        skip = "AWS keys not found"

    def test_interface(self):
        from scrapy.contrib.spiderqueue import SQSSpiderQueue
        verifyObject(ISpiderQueue, SQSSpiderQueue())

