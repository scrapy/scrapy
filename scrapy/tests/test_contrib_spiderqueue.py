from twisted.trial import unittest
from zope.interface.verify import verifyObject

from scrapy.interfaces import ISpiderQueue
from scrapy.utils.test import assert_aws_environ

class SQSSpiderQueueTest(unittest.TestCase):

    def setUp(self):
        assert_aws_environ()

    def test_interface(self):
        from scrapy.contrib.spiderqueue import SQSSpiderQueue
        verifyObject(ISpiderQueue, SQSSpiderQueue())

    # XXX: testing SQS queue operations is hard because there are long delays
    # for the operations to complete
