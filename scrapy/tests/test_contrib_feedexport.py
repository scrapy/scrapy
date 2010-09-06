import os, urlparse

from zope.interface.verify import verifyObject
from twisted.trial import unittest
from twisted.internet import defer
from cStringIO import StringIO

from scrapy.spider import BaseSpider
from scrapy.contrib.feedexport import IFeedStorage, FileFeedStorage, FTPFeedStorage, S3FeedStorage, StdoutFeedStorage
from scrapy.utils.url import path_to_file_uri
from scrapy.utils.test import assert_aws_environ

class FeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        yield storage.store(StringIO("content"), BaseSpider("default"))
        self.failUnless(os.path.exists(path))
        self.failUnlessEqual(open(path).read(), "content")
        # again, to check files are overwritten properly
        yield storage.store(StringIO("new content"), BaseSpider("default"))
        self.failUnlessEqual(open(path).read(), "new content")

class FileFeedStorageTest(FeedStorageTest):

    def test_store_file_uri(self):
        path = os.path.abspath(self.mktemp())
        uri = path_to_file_uri(path)
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_file_uri_makedirs(self):
        path = os.path.abspath(self.mktemp())
        path = os.path.join(path, 'more', 'paths', 'file.txt')
        uri = path_to_file_uri(path)
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_direct_path(self):
        path = os.path.abspath(self.mktemp())
        return self._assert_stores(FileFeedStorage(path), path)

    def test_store_direct_path_relative(self):
        path = self.mktemp()
        return self._assert_stores(FileFeedStorage(path), path)

    def test_interface(self):
        path = self.mktemp()
        st = FileFeedStorage(path)
        verifyObject(IFeedStorage, st)


class FTPFeedStorageTest(FeedStorageTest):

    def test_store(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        st = FTPFeedStorage(uri)
        verifyObject(IFeedStorage, st)
        return self._assert_stores(st, path)


class S3FeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        assert_aws_environ()
        uri = os.environ.get('FEEDTEST_S3_URI')
        if not uri:
            raise unittest.SkipTest("No S3 URI available for testing")
        from boto import connect_s3
        storage = S3FeedStorage(uri)
        verifyObject(IFeedStorage, storage)
        yield storage.store(StringIO("content"), BaseSpider("default"))
        u = urlparse.urlparse(uri)
        key = connect_s3().get_bucket(u.hostname, validate=False).get_key(u.path)
        self.failUnlessEqual(key.get_contents_as_string(), "content")

class StdoutFeedStorageTest(FeedStorageTest):

    @defer.inlineCallbacks
    def test_store(self):
        out = StringIO()
        storage = StdoutFeedStorage('stdout:', _stdout=out)
        yield storage.store(StringIO("content"), BaseSpider("default"))
        self.assertEqual(out.getvalue(), "content")
