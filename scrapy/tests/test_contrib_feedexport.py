import os, urlparse
from cStringIO import StringIO

from zope.interface.verify import verifyObject
from twisted.trial import unittest
from twisted.internet import defer
from w3lib.url import path_to_file_uri

from scrapy.spider import Spider
from scrapy.contrib.feedexport import IFeedStorage, FileFeedStorage, FTPFeedStorage, S3FeedStorage, StdoutFeedStorage
from scrapy.utils.test import assert_aws_environ

class FileFeedStorageTest(unittest.TestCase):

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

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        spider = Spider("default")
        file = storage.open(spider)
        file.write("content")
        yield storage.store(file)
        self.failUnless(os.path.exists(path))
        self.failUnlessEqual(open(path).read(), "content")


class FTPFeedStorageTest(unittest.TestCase):

    def test_store(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        st = FTPFeedStorage(uri)
        verifyObject(IFeedStorage, st)
        return self._assert_stores(st, path)

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        spider = Spider("default")
        file = storage.open(spider)
        file.write("content")
        yield storage.store(file)
        self.failUnless(os.path.exists(path))
        self.failUnlessEqual(open(path).read(), "content")
        # again, to check s3 objects are overwritten
        yield storage.store(StringIO("new content"))
        self.failUnlessEqual(open(path).read(), "new content")


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
        file = storage.open(Spider("default"))
        file.write("content")
        yield storage.store(file)
        u = urlparse.urlparse(uri)
        key = connect_s3().get_bucket(u.hostname, validate=False).get_key(u.path)
        self.failUnlessEqual(key.get_contents_as_string(), "content")

class StdoutFeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        out = StringIO()
        storage = StdoutFeedStorage('stdout:', _stdout=out)
        file = storage.open(Spider("default"))
        file.write("content")
        yield storage.store(file)
        self.assertEqual(out.getvalue(), "content")
