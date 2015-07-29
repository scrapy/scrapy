import sys
from twisted.trial import unittest
from twisted.internet import defer

import scrapy
from scrapy.utils.testproc import ProcessTest


class VersionTest(ProcessTest, unittest.TestCase):

    command = 'version'

    @defer.inlineCallbacks
    def test_output(self):
        encoding = getattr(sys.stdout, 'encoding') or 'utf-8'
        _, out, _ = yield self.execute([])
        self.assertEqual(out.strip().decode(encoding), "Scrapy %s" % scrapy.__version__)
