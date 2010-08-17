import os, urlparse

from twisted.trial import unittest
from twisted.internet import defer
from cStringIO import StringIO

from scrapy.spider import BaseSpider
from scrapy.contrib.feedexport import FileFeedStorage, FTPFeedStorage, S3FeedStorage

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
        uri = "file://%s" % path
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_file_uri_makedirs(self):
        path = os.path.abspath(self.mktemp())
        path = os.path.join(path, 'more', 'paths', 'file.txt')
        uri = "file://%s" % path
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_direct_path(self):
        path = os.path.abspath(self.mktemp())
        return self._assert_stores(FileFeedStorage(path), path)

    def test_store_direct_path_relative(self):
        path = self.mktemp()
        return self._assert_stores(FileFeedStorage(path), path)


class FTPFeedStorageTest(FeedStorageTest):

    def test_store(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        return self._assert_stores(FTPFeedStorage(uri), path)


class S3FeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        uri = os.environ.get('FEEDTEST_S3_URI')
        if not uri:
            raise unittest.SkipTest("No S3 bucket available for testing")
        try:
            from boto import connect_s3
        except ImportError:
            raise unittest.SkipTest("Missing library: boto")
        storage = S3FeedStorage(uri)
        yield storage.store(StringIO("content"), BaseSpider("default"))
        u = urlparse.urlparse(uri)
        key = connect_s3().get_bucket(u.hostname, validate=False).get_key(u.path)
        self.failUnlessEqual(key.get_contents_as_string(), "content")

