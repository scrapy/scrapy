import csv
import json
import os
import random
import shutil
import string
import tempfile
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from io import BytesIO
from logging import getLogger
from pathlib import Path
from string import ascii_letters, digits
from unittest import mock
from urllib.parse import urljoin, urlparse, quote
from urllib.request import pathname2url

import lxml.etree
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial import unittest
from w3lib.url import file_uri_to_path, path_to_file_uri
from zope.interface import implementer
from zope.interface.verify import verifyObject

import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import NotConfigured
from scrapy.exporters import CsvItemExporter
from scrapy.extensions.feedexport import (
    BlockingFeedStorage,
    FeedExporter,
    FileFeedStorage,
    FTPFeedStorage,
    GCSFeedStorage,
    IFeedStorage,
    S3FeedStorage,
    StdoutFeedStorage,
)
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import (
    assert_aws_environ,
    get_s3_content_and_delete,
    get_crawler,
    mock_google_cloud_storage,
)

from tests.mockserver import MockServer


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
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        yield storage.store(file)
        self.assertTrue(os.path.exists(path))
        try:
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"content")
        finally:
            os.unlink(path)


class FTPFeedStorageTest(unittest.TestCase):

    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = 'test_spider'

        crawler = get_crawler(settings_dict=settings)
        spider = TestSpider.from_crawler(crawler)
        return spider

    def test_store(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        st = FTPFeedStorage(uri)
        verifyObject(IFeedStorage, st)
        return self._assert_stores(st, path)

    def test_store_active_mode(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        use_active_mode = {'FEED_STORAGE_FTP_ACTIVE': True}
        crawler = get_crawler(settings_dict=use_active_mode)
        st = FTPFeedStorage.from_crawler(crawler, uri)
        verifyObject(IFeedStorage, st)
        return self._assert_stores(st, path)

    def test_uri_auth_quote(self):
        # RFC3986: 3.2.1. User Information
        pw_quoted = quote(string.punctuation, safe='')
        st = FTPFeedStorage('ftp://foo:%s@example.com/some_path' % pw_quoted)
        self.assertEqual(st.password, string.punctuation)

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        spider = self.get_test_spider()
        file = storage.open(spider)
        file.write(b"content")
        yield storage.store(file)
        self.assertTrue(os.path.exists(path))
        try:
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"content")
            # again, to check s3 objects are overwritten
            yield storage.store(BytesIO(b"new content"))
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"new content")
        finally:
            os.unlink(path)


class BlockingFeedStorageTest(unittest.TestCase):

    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = 'test_spider'

        crawler = get_crawler(settings_dict=settings)
        spider = TestSpider.from_crawler(crawler)
        return spider

    def test_default_temp_dir(self):
        b = BlockingFeedStorage()

        tmp = b.open(self.get_test_spider())
        tmp_path = os.path.dirname(tmp.name)
        self.assertEqual(tmp_path, tempfile.gettempdir())

    def test_temp_file(self):
        b = BlockingFeedStorage()

        tests_path = os.path.dirname(os.path.abspath(__file__))
        spider = self.get_test_spider({'FEED_TEMPDIR': tests_path})
        tmp = b.open(spider)
        tmp_path = os.path.dirname(tmp.name)
        self.assertEqual(tmp_path, tests_path)

    def test_invalid_folder(self):
        b = BlockingFeedStorage()

        tests_path = os.path.dirname(os.path.abspath(__file__))
        invalid_path = os.path.join(tests_path, 'invalid_path')
        spider = self.get_test_spider({'FEED_TEMPDIR': invalid_path})

        self.assertRaises(OSError, b.open, spider=spider)


class S3FeedStorageTest(unittest.TestCase):

    @mock.patch('scrapy.utils.project.get_project_settings',
                new=mock.MagicMock(return_value={'AWS_ACCESS_KEY_ID': 'conf_key',
                                                 'AWS_SECRET_ACCESS_KEY': 'conf_secret'}),
                create=True)
    def test_parse_credentials(self):
        try:
            import boto  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("S3FeedStorage requires boto")
        aws_credentials = {'AWS_ACCESS_KEY_ID': 'settings_key',
                           'AWS_SECRET_ACCESS_KEY': 'settings_secret'}
        crawler = get_crawler(settings_dict=aws_credentials)
        # Instantiate with crawler
        storage = S3FeedStorage.from_crawler(crawler,
                                             's3://mybucket/export.csv')
        self.assertEqual(storage.access_key, 'settings_key')
        self.assertEqual(storage.secret_key, 'settings_secret')
        # Instantiate directly
        storage = S3FeedStorage('s3://mybucket/export.csv',
                                aws_credentials['AWS_ACCESS_KEY_ID'],
                                aws_credentials['AWS_SECRET_ACCESS_KEY'])
        self.assertEqual(storage.access_key, 'settings_key')
        self.assertEqual(storage.secret_key, 'settings_secret')
        # URI priority > settings priority
        storage = S3FeedStorage('s3://uri_key:uri_secret@mybucket/export.csv',
                                aws_credentials['AWS_ACCESS_KEY_ID'],
                                aws_credentials['AWS_SECRET_ACCESS_KEY'])
        self.assertEqual(storage.access_key, 'uri_key')
        self.assertEqual(storage.secret_key, 'uri_secret')
        # Backward compatibility for initialising without settings
        with warnings.catch_warnings(record=True) as w:
            storage = S3FeedStorage('s3://mybucket/export.csv')
            self.assertEqual(storage.access_key, 'conf_key')
            self.assertEqual(storage.secret_key, 'conf_secret')
            self.assertTrue('without AWS keys' in str(w[-1].message))

    @defer.inlineCallbacks
    def test_store(self):
        assert_aws_environ()
        uri = os.environ.get('S3_TEST_FILE_URI')
        if not uri:
            raise unittest.SkipTest("No S3 URI available for testing")
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        storage = S3FeedStorage(uri, access_key, secret_key)
        verifyObject(IFeedStorage, storage)
        file = storage.open(scrapy.Spider("default"))
        expected_content = b"content: \xe2\x98\x83"
        file.write(expected_content)
        yield storage.store(file)
        u = urlparse(uri)
        content = get_s3_content_and_delete(u.hostname, u.path[1:])
        self.assertEqual(content, expected_content)

    def test_init_without_acl(self):
        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, None)

    def test_init_with_acl(self):
        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
            'custom-acl'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, 'custom-acl')

    def test_from_crawler_without_acl(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, None)

    def test_from_crawler_with_acl(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
            'FEED_STORAGE_S3_ACL': 'custom-acl',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, 'custom-acl')

    @defer.inlineCallbacks
    def test_store_botocore_without_acl(self):
        try:
            import botocore  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('botocore is required')

        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, None)

        storage.s3_client = mock.MagicMock()
        yield storage.store(BytesIO(b'test file'))
        self.assertNotIn('ACL', storage.s3_client.put_object.call_args[1])

    @defer.inlineCallbacks
    def test_store_botocore_with_acl(self):
        try:
            import botocore  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('botocore is required')

        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
            'custom-acl'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, 'custom-acl')

        storage.s3_client = mock.MagicMock()
        yield storage.store(BytesIO(b'test file'))
        self.assertEqual(
            storage.s3_client.put_object.call_args[1].get('ACL'),
            'custom-acl'
        )

    @defer.inlineCallbacks
    def test_store_not_botocore_without_acl(self):
        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, None)

        storage.is_botocore = False
        storage.connect_s3 = mock.MagicMock()
        self.assertFalse(storage.is_botocore)

        yield storage.store(BytesIO(b'test file'))

        conn = storage.connect_s3(*storage.connect_s3.call_args)
        bucket = conn.get_bucket(*conn.get_bucket.call_args)
        key = bucket.new_key(*bucket.new_key.call_args)
        self.assertNotIn(
            dict(policy='custom-acl'),
            key.set_contents_from_file.call_args
        )

    @defer.inlineCallbacks
    def test_store_not_botocore_with_acl(self):
        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
            'custom-acl'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, 'custom-acl')

        storage.is_botocore = False
        storage.connect_s3 = mock.MagicMock()
        self.assertFalse(storage.is_botocore)

        yield storage.store(BytesIO(b'test file'))

        conn = storage.connect_s3(*storage.connect_s3.call_args)
        bucket = conn.get_bucket(*conn.get_bucket.call_args)
        key = bucket.new_key(*bucket.new_key.call_args)
        self.assertIn(
            dict(policy='custom-acl'),
            key.set_contents_from_file.call_args
        )


class GCSFeedStorageTest(unittest.TestCase):

    def test_parse_settings(self):
        try:
            from google.cloud.storage import Client  # noqa
        except ImportError:
            raise unittest.SkipTest("GCSFeedStorage requires google-cloud-storage")

        settings = {'GCS_PROJECT_ID': '123', 'FEED_STORAGE_GCS_ACL': 'publicRead'}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, 'gs://mybucket/export.csv')
        assert storage.project_id == '123'
        assert storage.acl == 'publicRead'
        assert storage.bucket_name == 'mybucket'
        assert storage.blob_name == 'export.csv'

    def test_parse_empty_acl(self):
        try:
            from google.cloud.storage import Client  # noqa
        except ImportError:
            raise unittest.SkipTest("GCSFeedStorage requires google-cloud-storage")

        settings = {'GCS_PROJECT_ID': '123', 'FEED_STORAGE_GCS_ACL': ''}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, 'gs://mybucket/export.csv')
        assert storage.acl is None

        settings = {'GCS_PROJECT_ID': '123', 'FEED_STORAGE_GCS_ACL': None}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, 'gs://mybucket/export.csv')
        assert storage.acl is None

    @defer.inlineCallbacks
    def test_store(self):
        try:
            from google.cloud.storage import Client  # noqa
        except ImportError:
            raise unittest.SkipTest("GCSFeedStorage requires google-cloud-storage")

        uri = 'gs://mybucket/export.csv'
        project_id = 'myproject-123'
        acl = 'publicRead'
        (client_mock, bucket_mock, blob_mock) = mock_google_cloud_storage()
        with mock.patch('google.cloud.storage.Client') as m:
            m.return_value = client_mock

            f = mock.Mock()
            storage = GCSFeedStorage(uri, project_id, acl)
            yield storage.store(f)

            f.seek.assert_called_once_with(0)
            m.assert_called_once_with(project=project_id)
            client_mock.get_bucket.assert_called_once_with('mybucket')
            bucket_mock.blob.assert_called_once_with('export.csv')
            blob_mock.upload_from_file.assert_called_once_with(f, predefined_acl=acl)


class StdoutFeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        out = BytesIO()
        storage = StdoutFeedStorage('stdout:', _stdout=out)
        file = storage.open(scrapy.Spider("default"))
        file.write(b"content")
        yield storage.store(file)
        self.assertEqual(out.getvalue(), b"content")


class FromCrawlerMixin:
    init_with_crawler = False

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        cls.init_with_crawler = True
        return cls(*args, **kwargs)


class FromCrawlerCsvItemExporter(CsvItemExporter, FromCrawlerMixin):
    pass


class FromCrawlerFileFeedStorage(FileFeedStorage, FromCrawlerMixin):
    pass


class DummyBlockingFeedStorage(BlockingFeedStorage):

    def __init__(self, uri):
        self.path = file_uri_to_path(uri)

    def _store_in_thread(self, file):
        dirname = os.path.dirname(self.path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(self.path, 'ab') as output_file:
            output_file.write(file.read())

        file.close()


class FailingBlockingFeedStorage(DummyBlockingFeedStorage):

    def _store_in_thread(self, file):
        raise OSError('Cannot store')


@implementer(IFeedStorage)
class LogOnStoreFileStorage:
    """
    This storage logs inside `store` method.
    It can be used to make sure `store` method is invoked.
    """

    def __init__(self, uri):
        self.path = file_uri_to_path(uri)
        self.logger = getLogger()

    def open(self, spider):
        return tempfile.NamedTemporaryFile(prefix='feed-')

    def store(self, file):
        self.logger.info('Storage.store is called')
        file.close()


class FeedExportTestBase(ABC, unittest.TestCase):
    __test__ = False

    class MyItem(scrapy.Item):
        foo = scrapy.Field()
        egg = scrapy.Field()
        baz = scrapy.Field()

    def _random_temp_filename(self, inter_dir=''):
        chars = [random.choice(ascii_letters + digits) for _ in range(15)]
        filename = ''.join(chars)
        return os.path.join(self.temp_dir, inter_dir, filename)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @defer.inlineCallbacks
    def exported_data(self, items, settings):
        """
        Return exported data which a spider yielding ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = 'testspider'

            def parse(self, response):
                for item in items:
                    yield item

        data = yield self.run_and_export(TestSpider, settings)
        return data

    @defer.inlineCallbacks
    def exported_no_data(self, settings):
        """
        Return exported data which a spider yielding no ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = 'testspider'

            def parse(self, response):
                pass

        data = yield self.run_and_export(TestSpider, settings)
        return data

    @defer.inlineCallbacks
    def assertExported(self, items, header, rows, settings=None, ordered=True):
        yield self.assertExportedCsv(items, header, rows, settings, ordered)
        yield self.assertExportedJsonLines(items, rows, settings)
        yield self.assertExportedXml(items, rows, settings)
        yield self.assertExportedPickle(items, rows, settings)
        yield self.assertExportedMarshal(items, rows, settings)
        yield self.assertExportedMultiple(items, rows, settings)

    @abstractmethod
    def run_and_export(self, spider_cls, settings):
        pass

    def _load_until_eof(self, data, load_func):
        result = []
        with tempfile.TemporaryFile() as temp:
            temp.write(data)
            temp.seek(0)
            while True:
                try:
                    result.append(load_func(temp))
                except EOFError:
                    break
        return result


class FeedExportTest(FeedExportTestBase):
    __test__ = True

    @defer.inlineCallbacks
    def run_and_export(self, spider_cls, settings):
        """ Run spider with specified settings; return exported data. """

        def path_to_url(path):
            return urljoin('file:', pathname2url(str(path)))

        def printf_escape(string):
            return string.replace('%', '%%')

        FEEDS = settings.get('FEEDS') or {}
        settings['FEEDS'] = {
            printf_escape(path_to_url(file_path)): feed
            for file_path, feed in FEEDS.items()
        }

        content = {}
        try:
            with MockServer() as s:
                runner = CrawlerRunner(Settings(settings))
                spider_cls.start_urls = [s.url('/')]
                yield runner.crawl(spider_cls)

            for file_path, feed in FEEDS.items():
                if not os.path.exists(str(file_path)):
                    continue

                with open(str(file_path), 'rb') as f:
                    content[feed['format']] = f.read()

        finally:
            for file_path in FEEDS.keys():
                if not os.path.exists(str(file_path)):
                    continue

                os.remove(str(file_path))

        return content

    @defer.inlineCallbacks
    def assertExportedCsv(self, items, header, rows, settings=None, ordered=True):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'csv'},
            },
        })
        data = yield self.exported_data(items, settings)

        reader = csv.DictReader(to_unicode(data['csv']).splitlines())
        got_rows = list(reader)
        if ordered:
            self.assertEqual(reader.fieldnames, header)
        else:
            self.assertEqual(set(reader.fieldnames), set(header))

        self.assertEqual(rows, got_rows)

    @defer.inlineCallbacks
    def assertExportedJsonLines(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'jl'},
            },
        })
        data = yield self.exported_data(items, settings)
        parsed = [json.loads(to_unicode(line)) for line in data['jl'].splitlines()]
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        self.assertEqual(rows, parsed)

    @defer.inlineCallbacks
    def assertExportedXml(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'xml'},
            },
        })
        data = yield self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        root = lxml.etree.fromstring(data['xml'])
        got_rows = [{e.tag: e.text for e in it} for it in root.findall('item')]
        self.assertEqual(rows, got_rows)

    @defer.inlineCallbacks
    def assertExportedMultiple(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'xml'},
                self._random_temp_filename(): {'format': 'json'},
            },
        })
        data = yield self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        # XML
        root = lxml.etree.fromstring(data['xml'])
        xml_rows = [{e.tag: e.text for e in it} for it in root.findall('item')]
        self.assertEqual(rows, xml_rows)
        # JSON
        json_rows = json.loads(to_unicode(data['json']))
        self.assertEqual(rows, json_rows)

    @defer.inlineCallbacks
    def assertExportedPickle(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'pickle'},
            },
        })
        data = yield self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]
        import pickle
        result = self._load_until_eof(data['pickle'], load_func=pickle.load)
        self.assertEqual(expected, result)

    @defer.inlineCallbacks
    def assertExportedMarshal(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                self._random_temp_filename(): {'format': 'marshal'},
            },
        })
        data = yield self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]
        import marshal
        result = self._load_until_eof(data['marshal'], load_func=marshal.load)
        self.assertEqual(expected, result)

    @defer.inlineCallbacks
    def test_export_items(self):
        # feed exporters use field names from Item
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
        ]
        rows = [
            {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
            {'egg': 'spam2', 'foo': 'bar2', 'baz': 'quux2'}
        ]
        header = self.MyItem.fields.keys()
        yield self.assertExported(items, header, rows, ordered=False)

    @defer.inlineCallbacks
    def test_export_no_items_not_store_empty(self):
        for fmt in ('json', 'jsonlines', 'xml', 'csv'):
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): {'format': fmt},
                },
            }
            data = yield self.exported_no_data(settings)
            self.assertEqual(b'', data[fmt])

    @defer.inlineCallbacks
    def test_export_no_items_store_empty(self):
        formats = (
            ('json', b'[]'),
            ('jsonlines', b''),
            ('xml', b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ('csv', b''),
        )

        for fmt, expctd in formats:
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): {'format': fmt},
                },
                'FEED_STORE_EMPTY': True,
                'FEED_EXPORT_INDENT': None,
            }
            data = yield self.exported_no_data(settings)
            self.assertEqual(expctd, data[fmt])

    @defer.inlineCallbacks
    def test_export_no_items_multiple_feeds(self):
        """ Make sure that `storage.store` is called for every feed. """
        settings = {
            'FEEDS': {
                self._random_temp_filename(): {'format': 'json'},
                self._random_temp_filename(): {'format': 'xml'},
                self._random_temp_filename(): {'format': 'csv'},
            },
            'FEED_STORAGES': {'file': 'tests.test_feedexport.LogOnStoreFileStorage'},
            'FEED_STORE_EMPTY': False
        }

        with LogCapture() as log:
            yield self.exported_no_data(settings)

        print(log)
        self.assertEqual(str(log).count('Storage.store is called'), 3)

    @defer.inlineCallbacks
    def test_export_multiple_item_classes(self):

        class MyItem2(scrapy.Item):
            foo = scrapy.Field()
            hello = scrapy.Field()

        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            MyItem2({'hello': 'world2', 'foo': 'bar2'}),
            self.MyItem({'foo': 'bar3', 'egg': 'spam3', 'baz': 'quux3'}),
            {'hello': 'world4', 'egg': 'spam4'},
        ]

        # by default, Scrapy uses fields of the first Item for CSV and
        # all fields for JSON Lines
        header = self.MyItem.fields.keys()
        rows_csv = [
            {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
            {'egg': '', 'foo': 'bar2', 'baz': ''},
            {'egg': 'spam3', 'foo': 'bar3', 'baz': 'quux3'},
            {'egg': 'spam4', 'foo': '', 'baz': ''},
        ]
        rows_jl = [dict(row) for row in items]
        yield self.assertExportedCsv(items, header, rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl)

        # edge case: FEED_EXPORT_FIELDS==[] means the same as default None
        settings = {'FEED_EXPORT_FIELDS': []}
        yield self.assertExportedCsv(items, header, rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl, settings)

        # it is possible to override fields using FEED_EXPORT_FIELDS
        header = ["foo", "baz", "hello"]
        settings = {'FEED_EXPORT_FIELDS': header}
        rows = [
            {'foo': 'bar1', 'baz': '', 'hello': ''},
            {'foo': 'bar2', 'baz': '', 'hello': 'world2'},
            {'foo': 'bar3', 'baz': 'quux3', 'hello': ''},
            {'foo': '', 'baz': '', 'hello': 'world4'},
        ]
        yield self.assertExported(items, header, rows,
                                  settings=settings, ordered=True)

    @defer.inlineCallbacks
    def test_export_dicts(self):
        # When dicts are used, only keys from the first row are used as
        # a header for CSV, and all fields are used for JSON Lines.
        items = [
            {'foo': 'bar', 'egg': 'spam'},
            {'foo': 'bar', 'egg': 'spam', 'baz': 'quux'},
        ]
        rows_csv = [
            {'egg': 'spam', 'foo': 'bar'},
            {'egg': 'spam', 'foo': 'bar'}
        ]
        rows_jl = items
        yield self.assertExportedCsv(items, ['egg', 'foo'], rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl)

    @defer.inlineCallbacks
    def test_export_feed_export_fields(self):
        # FEED_EXPORT_FIELDS option allows to order export fields
        # and to select a subset of fields to export, both for Items and dicts.

        for item_cls in [self.MyItem, dict]:
            items = [
                item_cls({'foo': 'bar1', 'egg': 'spam1'}),
                item_cls({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            ]

            # export all columns
            settings = {'FEED_EXPORT_FIELDS': 'foo,baz,egg'}
            rows = [
                {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
                {'egg': 'spam2', 'foo': 'bar2', 'baz': 'quux2'}
            ]
            yield self.assertExported(items, ['foo', 'baz', 'egg'], rows,
                                      settings=settings, ordered=True)

            # export a subset of columns
            settings = {'FEED_EXPORT_FIELDS': 'egg,baz'}
            rows = [
                {'egg': 'spam1', 'baz': ''},
                {'egg': 'spam2', 'baz': 'quux2'}
            ]
            yield self.assertExported(items, ['egg', 'baz'], rows,
                                      settings=settings, ordered=True)

    @defer.inlineCallbacks
    def test_export_encoding(self):
        items = [dict({'foo': 'Test\xd6'})]

        formats = {
            'json': '[{"foo": "Test\\u00d6"}]'.encode('utf-8'),
            'jsonlines': '{"foo": "Test\\u00d6"}\n'.encode('utf-8'),
            'xml': (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<items><item><foo>Test\xd6</foo></item></items>'
            ).encode('utf-8'),
            'csv': 'foo\r\nTest\xd6\r\n'.encode('utf-8'),
        }

        for fmt, expected in formats.items():
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): {'format': fmt},
                },
                'FEED_EXPORT_INDENT': None,
            }
            data = yield self.exported_data(items, settings)
            self.assertEqual(expected, data[fmt])

        formats = {
            'json': '[{"foo": "Test\xd6"}]'.encode('latin-1'),
            'jsonlines': '{"foo": "Test\xd6"}\n'.encode('latin-1'),
            'xml': (
                '<?xml version="1.0" encoding="latin-1"?>\n'
                '<items><item><foo>Test\xd6</foo></item></items>'
            ).encode('latin-1'),
            'csv': 'foo\r\nTest\xd6\r\n'.encode('latin-1'),
        }

        for fmt, expected in formats.items():
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): {'format': fmt},
                },
                'FEED_EXPORT_INDENT': None,
                'FEED_EXPORT_ENCODING': 'latin-1',
            }
            data = yield self.exported_data(items, settings)
            self.assertEqual(expected, data[fmt])

    @defer.inlineCallbacks
    def test_export_multiple_configs(self):
        items = [dict({'foo': 'FOO', 'bar': 'BAR'})]

        formats = {
            'json': '[\n{"bar": "BAR"}\n]'.encode('utf-8'),
            'xml': (
                '<?xml version="1.0" encoding="latin-1"?>\n'
                '<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>'
            ).encode('latin-1'),
            'csv': 'bar,foo\r\nBAR,FOO\r\n'.encode('utf-8'),
        }

        settings = {
            'FEEDS': {
                self._random_temp_filename(): {
                    'format': 'json',
                    'indent': 0,
                    'fields': ['bar'],
                    'encoding': 'utf-8',
                },
                self._random_temp_filename(): {
                    'format': 'xml',
                    'indent': 2,
                    'fields': ['foo'],
                    'encoding': 'latin-1',
                },
                self._random_temp_filename(): {
                    'format': 'csv',
                    'indent': None,
                    'fields': ['bar', 'foo'],
                    'encoding': 'utf-8',
                },
            },
        }

        data = yield self.exported_data(items, settings)
        for fmt, expected in formats.items():
            self.assertEqual(expected, data[fmt])

    @defer.inlineCallbacks
    def test_export_indentation(self):
        items = [
            {'foo': ['bar']},
            {'key': 'value'},
        ]

        test_cases = [
            # JSON
            {
                'format': 'json',
                'indent': None,
                'expected': b'[{"foo": ["bar"]},{"key": "value"}]',
            },
            {
                'format': 'json',
                'indent': -1,
                'expected': b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                'format': 'json',
                'indent': 0,
                'expected': b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                'format': 'json',
                'indent': 2,
                'expected': b"""[
{
  "foo": [
    "bar"
  ]
},
{
  "key": "value"
}
]""",
            },
            {
                'format': 'json',
                'indent': 4,
                'expected': b"""[
{
    "foo": [
        "bar"
    ]
},
{
    "key": "value"
}
]""",
            },
            {
                'format': 'json',
                'indent': 5,
                'expected': b"""[
{
     "foo": [
          "bar"
     ]
},
{
     "key": "value"
}
]""",
            },

            # XML
            {
                'format': 'xml',
                'indent': None,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items><item><foo><value>bar</value></foo></item><item><key>value</key></item></items>""",
            },
            {
                'format': 'xml',
                'indent': -1,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                'format': 'xml',
                'indent': 0,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                'format': 'xml',
                'indent': 2,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items>
  <item>
    <foo>
      <value>bar</value>
    </foo>
  </item>
  <item>
    <key>value</key>
  </item>
</items>""",
            },
            {
                'format': 'xml',
                'indent': 4,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items>
    <item>
        <foo>
            <value>bar</value>
        </foo>
    </item>
    <item>
        <key>value</key>
    </item>
</items>""",
            },
            {
                'format': 'xml',
                'indent': 5,
                'expected': b"""<?xml version="1.0" encoding="utf-8"?>
<items>
     <item>
          <foo>
               <value>bar</value>
          </foo>
     </item>
     <item>
          <key>value</key>
     </item>
</items>""",
            },
        ]

        for row in test_cases:
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): {
                        'format': row['format'],
                        'indent': row['indent'],
                    },
                },
            }
            data = yield self.exported_data(items, settings)
            self.assertEqual(row['expected'], data[row['format']])

    @defer.inlineCallbacks
    def test_init_exporters_storages_with_crawler(self):
        settings = {
            'FEED_EXPORTERS': {'csv': 'tests.test_feedexport.FromCrawlerCsvItemExporter'},
            'FEED_STORAGES': {'file': 'tests.test_feedexport.FromCrawlerFileFeedStorage'},
            'FEEDS': {
                self._random_temp_filename(): {'format': 'csv'},
            },
        }
        yield self.exported_data(items=[], settings=settings)
        self.assertTrue(FromCrawlerCsvItemExporter.init_with_crawler)
        self.assertTrue(FromCrawlerFileFeedStorage.init_with_crawler)

    @defer.inlineCallbacks
    def test_pathlib_uri(self):
        feed_path = Path(self._random_temp_filename())
        settings = {
            'FEED_STORE_EMPTY': True,
            'FEEDS': {
                feed_path: {'format': 'csv'}
            },
        }
        data = yield self.exported_no_data(settings)
        self.assertEqual(data['csv'], b'')

    @defer.inlineCallbacks
    def test_multiple_feeds_success_logs_blocking_feed_storage(self):
        settings = {
            'FEEDS': {
                self._random_temp_filename(): {'format': 'json'},
                self._random_temp_filename(): {'format': 'xml'},
                self._random_temp_filename(): {'format': 'csv'},
            },
            'FEED_STORAGES': {'file': 'tests.test_feedexport.DummyBlockingFeedStorage'},
        }
        items = [
            {'foo': 'bar1', 'baz': ''},
            {'foo': 'bar2', 'baz': 'quux'},
        ]
        with LogCapture() as log:
            yield self.exported_data(items, settings)

        print(log)
        for fmt in ['json', 'xml', 'csv']:
            self.assertIn('Stored %s feed (2 items)' % fmt, str(log))

    @defer.inlineCallbacks
    def test_multiple_feeds_failing_logs_blocking_feed_storage(self):
        settings = {
            'FEEDS': {
                self._random_temp_filename(): {'format': 'json'},
                self._random_temp_filename(): {'format': 'xml'},
                self._random_temp_filename(): {'format': 'csv'},
            },
            'FEED_STORAGES': {'file': 'tests.test_feedexport.FailingBlockingFeedStorage'},
        }
        items = [
            {'foo': 'bar1', 'baz': ''},
            {'foo': 'bar2', 'baz': 'quux'},
        ]
        with LogCapture() as log:
            yield self.exported_data(items, settings)

        print(log)
        for fmt in ['json', 'xml', 'csv']:
            self.assertIn('Error storing %s feed (2 items)' % fmt, str(log))


class BatchDeliveriesTest(FeedExportTestBase):
    __test__ = True
    _file_mark = '_%(batch_time)s_#%(batch_id)02d_'

    @defer.inlineCallbacks
    def run_and_export(self, spider_cls, settings):
        """ Run spider with specified settings; return exported data. """

        def build_url(path):
            if path[0] != '/':
                path = '/' + path
            return urljoin('file:', path)

        FEEDS = settings.get('FEEDS') or {}
        settings['FEEDS'] = {
            build_url(file_path): feed
            for file_path, feed in FEEDS.items()
        }
        content = defaultdict(list)
        try:
            with MockServer() as s:
                runner = CrawlerRunner(Settings(settings))
                spider_cls.start_urls = [s.url('/')]
                yield runner.crawl(spider_cls)

            for path, feed in FEEDS.items():
                dir_name = os.path.dirname(path)
                for file in sorted(os.listdir(dir_name)):
                    with open(os.path.join(dir_name, file), 'rb') as f:
                        data = f.read()
                        content[feed['format']].append(data)
        finally:
            self.tearDown()
        defer.returnValue(content)

    @defer.inlineCallbacks
    def assertExportedJsonLines(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'jl', self._file_mark): {'format': 'jl'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = yield self.exported_data(items, settings)
        for batch in data['jl']:
            got_batch = [json.loads(to_unicode(batch_item)) for batch_item in batch.splitlines()]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def assertExportedCsv(self, items, header, rows, settings=None, ordered=True):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'csv', self._file_mark): {'format': 'csv'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        data = yield self.exported_data(items, settings)
        for batch in data['csv']:
            got_batch = csv.DictReader(to_unicode(batch).splitlines())
            self.assertEqual(list(header), got_batch.fieldnames)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            self.assertEqual(expected_batch, list(got_batch))

    @defer.inlineCallbacks
    def assertExportedXml(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'xml', self._file_mark): {'format': 'xml'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = yield self.exported_data(items, settings)
        for batch in data['xml']:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall('item')]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def assertExportedMultiple(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'xml', self._file_mark): {'format': 'xml'},
                os.path.join(self._random_temp_filename(), 'json', self._file_mark): {'format': 'json'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = yield self.exported_data(items, settings)
        # XML
        xml_rows = rows.copy()
        for batch in data['xml']:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall('item')]
            expected_batch, xml_rows = xml_rows[:batch_size], xml_rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)
        # JSON
        json_rows = rows.copy()
        for batch in data['json']:
            got_batch = json.loads(batch.decode('utf-8'))
            expected_batch, json_rows = json_rows[:batch_size], json_rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def assertExportedPickle(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'pickle', self._file_mark): {'format': 'pickle'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = yield self.exported_data(items, settings)
        import pickle
        for batch in data['pickle']:
            got_batch = self._load_until_eof(batch, load_func=pickle.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def assertExportedMarshal(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'marshal', self._file_mark): {'format': 'marshal'},
            },
        })
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = yield self.exported_data(items, settings)
        import marshal
        for batch in data['marshal']:
            got_batch = self._load_until_eof(batch, load_func=marshal.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def test_export_items(self):
        """ Test partial deliveries in all supported formats """
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            self.MyItem({'foo': 'bar3', 'baz': 'quux3'}),
        ]
        rows = [
            {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
            {'egg': 'spam2', 'foo': 'bar2', 'baz': 'quux2'},
            {'foo': 'bar3', 'baz': 'quux3', 'egg': ''}
        ]
        settings = {
            'FEED_EXPORT_BATCH_ITEM_COUNT': 2
        }
        header = self.MyItem.fields.keys()
        yield self.assertExported(items, header, rows, settings=Settings(settings))

    def test_wrong_path(self):
        """ If path is without %(batch_time)s and %(batch_id) an exception must be raised """
        settings = {
            'FEEDS': {
                self._random_temp_filename(): {'format': 'xml'},
            },
            'FEED_EXPORT_BATCH_ITEM_COUNT': 1
        }
        crawler = get_crawler(settings_dict=settings)
        self.assertRaises(NotConfigured, FeedExporter, crawler)

    @defer.inlineCallbacks
    def test_export_no_items_not_store_empty(self):
        for fmt in ('json', 'jsonlines', 'xml', 'csv'):
            settings = {
                'FEEDS': {
                    os.path.join(self._random_temp_filename(), fmt, self._file_mark): {'format': fmt},
                },
                'FEED_EXPORT_BATCH_ITEM_COUNT': 1
            }
            data = yield self.exported_no_data(settings)
            data = dict(data)
            self.assertEqual(b'', data[fmt][0])

    @defer.inlineCallbacks
    def test_export_no_items_store_empty(self):
        formats = (
            ('json', b'[]'),
            ('jsonlines', b''),
            ('xml', b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ('csv', b''),
        )

        for fmt, expctd in formats:
            settings = {
                'FEEDS': {
                    os.path.join(self._random_temp_filename(), fmt, self._file_mark): {'format': fmt},
                },
                'FEED_STORE_EMPTY': True,
                'FEED_EXPORT_INDENT': None,
                'FEED_EXPORT_BATCH_ITEM_COUNT': 1,
            }
            data = yield self.exported_no_data(settings)
            data = dict(data)
            self.assertEqual(expctd, data[fmt][0])

    @defer.inlineCallbacks
    def test_export_multiple_configs(self):
        items = [dict({'foo': 'FOO', 'bar': 'BAR'}), dict({'foo': 'FOO1', 'bar': 'BAR1'})]

        formats = {
            'json': ['[\n{"bar": "BAR"}\n]'.encode('utf-8'),
                     '[\n{"bar": "BAR1"}\n]'.encode('utf-8')],
            'xml': [
                (
                    '<?xml version="1.0" encoding="latin-1"?>\n'
                    '<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>'
                ).encode('latin-1'),
                (
                    '<?xml version="1.0" encoding="latin-1"?>\n'
                    '<items>\n  <item>\n    <foo>FOO1</foo>\n  </item>\n</items>'
                ).encode('latin-1')
            ],
            'csv': ['foo,bar\r\nFOO,BAR\r\n'.encode('utf-8'),
                    'foo,bar\r\nFOO1,BAR1\r\n'.encode('utf-8')],
        }

        settings = {
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'json', self._file_mark): {
                    'format': 'json',
                    'indent': 0,
                    'fields': ['bar'],
                    'encoding': 'utf-8',
                },
                os.path.join(self._random_temp_filename(), 'xml', self._file_mark): {
                    'format': 'xml',
                    'indent': 2,
                    'fields': ['foo'],
                    'encoding': 'latin-1',
                },
                os.path.join(self._random_temp_filename(), 'csv', self._file_mark): {
                    'format': 'csv',
                    'indent': None,
                    'fields': ['foo', 'bar'],
                    'encoding': 'utf-8',
                },
            },
            'FEED_EXPORT_BATCH_ITEM_COUNT': 1,
        }
        data = yield self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt]):
                self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def test_batch_item_count_feeds_setting(self):
        items = [dict({'foo': 'FOO'}), dict({'foo': 'FOO1'})]
        formats = {
            'json': ['[{"foo": "FOO"}]'.encode('utf-8'),
                     '[{"foo": "FOO1"}]'.encode('utf-8')],
        }
        settings = {
            'FEEDS': {
                os.path.join(self._random_temp_filename(), 'json', self._file_mark): {
                    'format': 'json',
                    'indent': None,
                    'encoding': 'utf-8',
                    'batch_item_count': 1,
                },
            },
        }
        data = yield self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt]):
                self.assertEqual(expected_batch, got_batch)

    @defer.inlineCallbacks
    def test_batch_path_differ(self):
        """
        Test that the name of all batch files differ from each other.
        So %(batch_time)s replaced with the current date.
        """
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            self.MyItem({'foo': 'bar3', 'baz': 'quux3'}),
        ]
        settings = {
            'FEEDS': {
                os.path.join(self._random_temp_filename(), '%(batch_time)s'): {
                    'format': 'json',
                },
            },
            'FEED_EXPORT_BATCH_ITEM_COUNT': 1,
        }
        data = yield self.exported_data(items, settings)
        self.assertEqual(len(items) + 1, len(data['json']))

    @defer.inlineCallbacks
    def test_s3_export(self):
        """
        Test export of items into s3 bucket.
        S3_TEST_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY must be specified in tox.ini
        to perform this test:
        [testenv]
        setenv =
            AWS_SECRET_ACCESS_KEY = ABCD
            AWS_ACCESS_KEY_ID = EFGH
            S3_TEST_BUCKET_NAME = IJKL
        """
        try:
            import boto3
        except ImportError:
            raise unittest.SkipTest("S3FeedStorage requires boto3")

        assert_aws_environ()
        s3_test_bucket_name = os.environ.get('S3_TEST_BUCKET_NAME')
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        if not s3_test_bucket_name:
            raise unittest.SkipTest("No S3 BUCKET available for testing")

        chars = [random.choice(ascii_letters + digits) for _ in range(15)]
        filename = ''.join(chars)
        prefix = 'tmp/{filename}'.format(filename=filename)
        s3_test_file_uri = 's3://{bucket_name}/{prefix}/%(batch_time)s.json'.format(
            bucket_name=s3_test_bucket_name, prefix=prefix
        )
        storage = S3FeedStorage(s3_test_bucket_name, access_key, secret_key)
        settings = Settings({
            'FEEDS': {
                s3_test_file_uri: {
                    'format': 'json',
                },
            },
            'FEED_EXPORT_BATCH_ITEM_COUNT': 1,
        })
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            self.MyItem({'foo': 'bar3', 'baz': 'quux3'}),
        ]
        verifyObject(IFeedStorage, storage)

        class TestSpider(scrapy.Spider):
            name = 'testspider'

            def parse(self, response):
                for item in items:
                    yield item

        s3 = boto3.resource('s3')
        my_bucket = s3.Bucket(s3_test_bucket_name)
        batch_size = settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT')

        with MockServer() as s:
            runner = CrawlerRunner(Settings(settings))
            TestSpider.start_urls = [s.url('/')]
            yield runner.crawl(TestSpider)

        for file_uri in my_bucket.objects.filter(Prefix=prefix):
            content = get_s3_content_and_delete(s3_test_bucket_name, file_uri.key)
            if not content and not items:
                break
            content = json.loads(content.decode('utf-8'))
            expected_batch, items = items[:batch_size], items[batch_size:]
            self.assertEqual(expected_batch, content)
