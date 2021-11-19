import bz2
import csv
import gzip
import json
import lzma
import os
import random
import shutil
import string
import tempfile
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import ExitStack
from io import BytesIO
from logging import getLogger
from pathlib import Path
from string import ascii_letters, digits
from unittest import mock
from urllib.parse import urljoin, quote
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
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
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
    get_crawler,
    mock_google_cloud_storage,
    skip_if_no_boto,
)

from tests.mockserver import MockFTPServer, MockServer
from tests.spiders import ItemSpider


def path_to_url(path):
    return urljoin('file:', pathname2url(str(path)))


def printf_escape(string):
    return string.replace('%', '%%')


def build_url(path):
    if path[0] != '/':
        path = '/' + path
    return urljoin('file:', path)


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

    def _store(self, feed_options=None):
        path = os.path.abspath(self.mktemp())
        storage = FileFeedStorage(path, feed_options=feed_options)
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        storage.store(file)
        return path

    def test_append(self):
        path = self._store()
        return self._assert_stores(FileFeedStorage(path), path, b"contentcontent")

    def test_overwrite(self):
        path = self._store({"overwrite": True})
        return self._assert_stores(
            FileFeedStorage(path, feed_options={"overwrite": True}),
            path
        )

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path, expected_content=b"content"):
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        yield storage.store(file)
        self.assertTrue(os.path.exists(path))
        try:
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), expected_content)
        finally:
            os.unlink(path)


class FTPFeedStorageTest(unittest.TestCase):

    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = 'test_spider'

        crawler = get_crawler(settings_dict=settings)
        spider = TestSpider.from_crawler(crawler)
        return spider

    def _store(self, uri, content, feed_options=None, settings=None):
        crawler = get_crawler(settings_dict=settings or {})
        storage = FTPFeedStorage.from_crawler(
            crawler,
            uri,
            feed_options=feed_options,
        )
        verifyObject(IFeedStorage, storage)
        spider = self.get_test_spider()
        file = storage.open(spider)
        file.write(content)
        return storage.store(file)

    def _assert_stored(self, path, content):
        self.assertTrue(path.exists())
        try:
            with path.open('rb') as fp:
                self.assertEqual(fp.read(), content)
        finally:
            os.unlink(str(path))

    @defer.inlineCallbacks
    def test_append(self):
        with MockFTPServer() as ftp_server:
            filename = 'file'
            url = ftp_server.url(filename)
            feed_options = {'overwrite': False}
            yield self._store(url, b"foo", feed_options=feed_options)
            yield self._store(url, b"bar", feed_options=feed_options)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @defer.inlineCallbacks
    def test_overwrite(self):
        with MockFTPServer() as ftp_server:
            filename = 'file'
            url = ftp_server.url(filename)
            yield self._store(url, b"foo")
            yield self._store(url, b"bar")
            self._assert_stored(ftp_server.path / filename, b"bar")

    @defer.inlineCallbacks
    def test_append_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {'FEED_STORAGE_FTP_ACTIVE': True}
            filename = 'file'
            url = ftp_server.url(filename)
            feed_options = {'overwrite': False}
            yield self._store(url, b"foo", feed_options=feed_options, settings=settings)
            yield self._store(url, b"bar", feed_options=feed_options, settings=settings)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @defer.inlineCallbacks
    def test_overwrite_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {'FEED_STORAGE_FTP_ACTIVE': True}
            filename = 'file'
            url = ftp_server.url(filename)
            yield self._store(url, b"foo", settings=settings)
            yield self._store(url, b"bar", settings=settings)
            self._assert_stored(ftp_server.path / filename, b"bar")

    def test_uri_auth_quote(self):
        # RFC3986: 3.2.1. User Information
        pw_quoted = quote(string.punctuation, safe='')
        st = FTPFeedStorage(f'ftp://foo:{pw_quoted}@example.com/some_path', {})
        self.assertEqual(st.password, string.punctuation)


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

    def test_parse_credentials(self):
        skip_if_no_boto()
        aws_credentials = {'AWS_ACCESS_KEY_ID': 'settings_key',
                           'AWS_SECRET_ACCESS_KEY': 'settings_secret',
                           'AWS_SESSION_TOKEN': 'settings_token'}
        crawler = get_crawler(settings_dict=aws_credentials)
        # Instantiate with crawler
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv',
        )
        self.assertEqual(storage.access_key, 'settings_key')
        self.assertEqual(storage.secret_key, 'settings_secret')
        self.assertEqual(storage.session_token, 'settings_token')
        # Instantiate directly
        storage = S3FeedStorage('s3://mybucket/export.csv',
                                aws_credentials['AWS_ACCESS_KEY_ID'],
                                aws_credentials['AWS_SECRET_ACCESS_KEY'],
                                session_token=aws_credentials['AWS_SESSION_TOKEN'])
        self.assertEqual(storage.access_key, 'settings_key')
        self.assertEqual(storage.secret_key, 'settings_secret')
        self.assertEqual(storage.session_token, 'settings_token')
        # URI priority > settings priority
        storage = S3FeedStorage('s3://uri_key:uri_secret@mybucket/export.csv',
                                aws_credentials['AWS_ACCESS_KEY_ID'],
                                aws_credentials['AWS_SECRET_ACCESS_KEY'])
        self.assertEqual(storage.access_key, 'uri_key')
        self.assertEqual(storage.secret_key, 'uri_secret')

    @defer.inlineCallbacks
    def test_store(self):
        skip_if_no_boto()

        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
        }
        crawler = get_crawler(settings_dict=settings)
        bucket = 'mybucket'
        key = 'export.csv'
        storage = S3FeedStorage.from_crawler(crawler, f's3://{bucket}/{key}')
        verifyObject(IFeedStorage, storage)

        file = mock.MagicMock()
        from botocore.stub import Stubber
        with Stubber(storage.s3_client) as stub:
            stub.add_response(
                'put_object',
                expected_params={
                    'Body': file,
                    'Bucket': bucket,
                    'Key': key,
                },
                service_response={},
            )

            yield storage.store(file)

            stub.assert_no_pending_responses()
            self.assertEqual(
                file.method_calls,
                [
                    mock.call.seek(0),
                    # The call to read does not happen with Stubber
                    mock.call.close(),
                ]
            )

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

    def test_init_with_endpoint_url(self):
        storage = S3FeedStorage(
            's3://mybucket/export.csv',
            'access_key',
            'secret_key',
            endpoint_url='https://example.com'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.endpoint_url, 'https://example.com')

    def test_from_crawler_without_acl(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv',
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, None)

    def test_without_endpoint_url(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv',
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.endpoint_url, None)

    def test_from_crawler_with_acl(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
            'FEED_STORAGE_S3_ACL': 'custom-acl',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv',
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.acl, 'custom-acl')

    def test_from_crawler_with_endpoint_url(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
            'AWS_ENDPOINT_URL': 'https://example.com',
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            's3://mybucket/export.csv'
        )
        self.assertEqual(storage.access_key, 'access_key')
        self.assertEqual(storage.secret_key, 'secret_key')
        self.assertEqual(storage.endpoint_url, 'https://example.com')

    @defer.inlineCallbacks
    def test_store_botocore_without_acl(self):
        skip_if_no_boto()
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
        skip_if_no_boto()
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

    def test_overwrite_default(self):
        with LogCapture() as log:
            S3FeedStorage(
                's3://mybucket/export.csv',
                'access_key',
                'secret_key',
                'custom-acl'
            )
        self.assertNotIn('S3 does not support appending to files', str(log))

    def test_overwrite_false(self):
        with LogCapture() as log:
            S3FeedStorage(
                's3://mybucket/export.csv',
                'access_key',
                'secret_key',
                'custom-acl',
                feed_options={'overwrite': False},
            )
        self.assertIn('S3 does not support appending to files', str(log))


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

    def test_overwrite_default(self):
        with LogCapture() as log:
            StdoutFeedStorage('stdout:')
        self.assertNotIn('Standard output (stdout) storage does not support overwriting', str(log))

    def test_overwrite_true(self):
        with LogCapture() as log:
            StdoutFeedStorage('stdout:', feed_options={'overwrite': True})
        self.assertIn('Standard output (stdout) storage does not support overwriting', str(log))


class FromCrawlerMixin:
    init_with_crawler = False

    @classmethod
    def from_crawler(cls, crawler, *args, feed_options=None, **kwargs):
        cls.init_with_crawler = True
        return cls(*args, **kwargs)


class FromCrawlerCsvItemExporter(CsvItemExporter, FromCrawlerMixin):
    pass


class FromCrawlerFileFeedStorage(FileFeedStorage, FromCrawlerMixin):

    @classmethod
    def from_crawler(cls, crawler, *args, feed_options=None, **kwargs):
        cls.init_with_crawler = True
        return cls(*args, feed_options=feed_options, **kwargs)


class DummyBlockingFeedStorage(BlockingFeedStorage):

    def __init__(self, uri, *args, feed_options=None):
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

    def __init__(self, uri, feed_options=None):
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

    class MyItem2(scrapy.Item):
        foo = scrapy.Field()
        hello = scrapy.Field()

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

        FEEDS = settings.get('FEEDS') or {}
        settings['FEEDS'] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content = {}
        try:
            with MockServer() as s:
                runner = CrawlerRunner(Settings(settings))
                spider_cls.start_urls = [s.url('/')]
                yield runner.crawl(spider_cls)

            for file_path, feed_options in FEEDS.items():
                if not os.path.exists(str(file_path)):
                    continue

                with open(str(file_path), 'rb') as f:
                    content[feed_options['format']] = f.read()

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
    def test_stats_file_success(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(self._random_temp_filename())): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with MockServer() as mockserver:
            yield crawler.crawl(mockserver=mockserver)
        self.assertIn("feedexport/success_count/FileFeedStorage", crawler.stats.get_stats())
        self.assertEqual(crawler.stats.get_value("feedexport/success_count/FileFeedStorage"), 1)

    @defer.inlineCallbacks
    def test_stats_file_failed(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(self._random_temp_filename())): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with ExitStack() as stack:
            mockserver = stack.enter_context(MockServer())
            stack.enter_context(
                mock.patch(
                    "scrapy.extensions.feedexport.FileFeedStorage.store",
                    side_effect=KeyError("foo"))
            )
            yield crawler.crawl(mockserver=mockserver)
        self.assertIn("feedexport/failed_count/FileFeedStorage", crawler.stats.get_stats())
        self.assertEqual(crawler.stats.get_value("feedexport/failed_count/FileFeedStorage"), 1)

    @defer.inlineCallbacks
    def test_stats_multiple_file(self):
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
            "FEEDS": {
                printf_escape(path_to_url(self._random_temp_filename())): {
                    "format": "json",
                },
                "s3://bucket/key/foo.csv": {
                    "format": "csv",
                },
                "stdout:": {
                    "format": "xml",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with MockServer() as mockserver, mock.patch.object(S3FeedStorage, "store"):
            yield crawler.crawl(mockserver=mockserver)
        self.assertIn("feedexport/success_count/FileFeedStorage", crawler.stats.get_stats())
        self.assertIn("feedexport/success_count/S3FeedStorage", crawler.stats.get_stats())
        self.assertIn("feedexport/success_count/StdoutFeedStorage", crawler.stats.get_stats())
        self.assertEqual(crawler.stats.get_value("feedexport/success_count/FileFeedStorage"), 1)
        self.assertEqual(crawler.stats.get_value("feedexport/success_count/S3FeedStorage"), 1)
        self.assertEqual(crawler.stats.get_value("feedexport/success_count/StdoutFeedStorage"), 1)

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
            'FEED_STORAGES': {'file': LogOnStoreFileStorage},
            'FEED_STORE_EMPTY': False
        }

        with LogCapture() as log:
            yield self.exported_no_data(settings)

        print(log)
        self.assertEqual(str(log).count('Storage.store is called'), 3)

    @defer.inlineCallbacks
    def test_export_multiple_item_classes(self):

        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem2({'hello': 'world2', 'foo': 'bar2'}),
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
    def test_export_based_on_item_classes(self):
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem2({'hello': 'world2', 'foo': 'bar2'}),
            {'hello': 'world3', 'egg': 'spam3'},
        ]

        formats = {
            'csv': b'baz,egg,foo\r\n,spam1,bar1\r\n',
            'json': b'[\n{"hello": "world2", "foo": "bar2"}\n]',
            'jsonlines': (
                b'{"foo": "bar1", "egg": "spam1"}\n'
                b'{"hello": "world2", "foo": "bar2"}\n'
            ),
            'xml': (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b'<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>'
                b'world2</hello><foo>bar2</foo></item>\n<item><hello>world3'
                b'</hello><egg>spam3</egg></item>\n</items>'
            ),
        }

        settings = {
            'FEEDS': {
                self._random_temp_filename(): {
                    'format': 'csv',
                    'item_classes': [self.MyItem],
                },
                self._random_temp_filename(): {
                    'format': 'json',
                    'item_classes': [self.MyItem2],
                },
                self._random_temp_filename(): {
                    'format': 'jsonlines',
                    'item_classes': [self.MyItem, self.MyItem2],
                },
                self._random_temp_filename(): {
                    'format': 'xml',
                },
            },
        }

        data = yield self.exported_data(items, settings)
        for fmt, expected in formats.items():
            self.assertEqual(expected, data[fmt])

    @defer.inlineCallbacks
    def test_export_based_on_custom_filters(self):
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem2({'hello': 'world2', 'foo': 'bar2'}),
            {'hello': 'world3', 'egg': 'spam3'},
        ]

        MyItem = self.MyItem

        class CustomFilter1:
            def __init__(self, feed_options):
                pass

            def accepts(self, item):
                return isinstance(item, MyItem)

        class CustomFilter2(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                if 'foo' not in item.fields:
                    return False
                return True

        class CustomFilter3(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                if isinstance(item, tuple(self.item_classes)) and item['foo'] == "bar1":
                    return True
                return False

        formats = {
            'json': b'[\n{"foo": "bar1", "egg": "spam1"}\n]',
            'xml': (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b'<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>'
                b'world2</hello><foo>bar2</foo></item>\n</items>'
            ),
            'jsonlines': b'{"foo": "bar1", "egg": "spam1"}\n',
        }

        settings = {
            'FEEDS': {
                self._random_temp_filename(): {
                    'format': 'json',
                    'item_filter': CustomFilter1,
                },
                self._random_temp_filename(): {
                    'format': 'xml',
                    'item_filter': CustomFilter2,
                },
                self._random_temp_filename(): {
                    'format': 'jsonlines',
                    'item_classes': [self.MyItem, self.MyItem2],
                    'item_filter': CustomFilter3,
                },
            },
        }

        data = yield self.exported_data(items, settings)
        for fmt, expected in formats.items():
            self.assertEqual(expected, data[fmt])

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
            'FEED_EXPORTERS': {'csv': FromCrawlerCsvItemExporter},
            'FEED_STORAGES': {'file': FromCrawlerFileFeedStorage},
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
            'FEED_STORAGES': {'file': DummyBlockingFeedStorage},
        }
        items = [
            {'foo': 'bar1', 'baz': ''},
            {'foo': 'bar2', 'baz': 'quux'},
        ]
        with LogCapture() as log:
            yield self.exported_data(items, settings)

        print(log)
        for fmt in ['json', 'xml', 'csv']:
            self.assertIn(f'Stored {fmt} feed (2 items)', str(log))

    @defer.inlineCallbacks
    def test_multiple_feeds_failing_logs_blocking_feed_storage(self):
        settings = {
            'FEEDS': {
                self._random_temp_filename(): {'format': 'json'},
                self._random_temp_filename(): {'format': 'xml'},
                self._random_temp_filename(): {'format': 'csv'},
            },
            'FEED_STORAGES': {'file': FailingBlockingFeedStorage},
        }
        items = [
            {'foo': 'bar1', 'baz': ''},
            {'foo': 'bar2', 'baz': 'quux'},
        ]
        with LogCapture() as log:
            yield self.exported_data(items, settings)

        print(log)
        for fmt in ['json', 'xml', 'csv']:
            self.assertIn(f'Error storing {fmt} feed (2 items)', str(log))

    @defer.inlineCallbacks
    def test_extend_kwargs(self):
        items = [{'foo': 'FOO', 'bar': 'BAR'}]

        expected_with_title_csv = 'foo,bar\r\nFOO,BAR\r\n'.encode('utf-8')
        expected_without_title_csv = 'FOO,BAR\r\n'.encode('utf-8')
        test_cases = [
            # with title
            {
                'options': {
                    'format': 'csv',
                    'item_export_kwargs': {'include_headers_line': True},
                },
                'expected': expected_with_title_csv,
            },
            # without title
            {
                'options': {
                    'format': 'csv',
                    'item_export_kwargs': {'include_headers_line': False},
                },
                'expected': expected_without_title_csv,
            },
        ]

        for row in test_cases:
            feed_options = row['options']
            settings = {
                'FEEDS': {
                    self._random_temp_filename(): feed_options,
                },
                'FEED_EXPORT_INDENT': None,
            }

            data = yield self.exported_data(items, settings)
            self.assertEqual(row['expected'], data[feed_options['format']])


class FeedPostProcessedExportsTest(FeedExportTestBase):
    __test__ = True

    items = [{'foo': 'bar'}]
    expected = b'foo\r\nbar\r\n'

    class MyPlugin1:
        def __init__(self, file, feed_options):
            self.file = file
            self.feed_options = feed_options
            self.char = self.feed_options.get('plugin1_char', b'')

        def write(self, data):
            written_count = self.file.write(data)
            written_count += self.file.write(self.char)
            return written_count

        def close(self):
            self.file.close()

    def _named_tempfile(self, name):
        return os.path.join(self.temp_dir, name)

    @defer.inlineCallbacks
    def run_and_export(self, spider_cls, settings):
        """ Run spider with specified settings; return exported data with filename. """

        FEEDS = settings.get('FEEDS') or {}
        settings['FEEDS'] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content = {}
        try:
            with MockServer() as s:
                runner = CrawlerRunner(Settings(settings))
                spider_cls.start_urls = [s.url('/')]
                yield runner.crawl(spider_cls)

            for file_path, feed_options in FEEDS.items():
                if not os.path.exists(str(file_path)):
                    continue

                with open(str(file_path), 'rb') as f:
                    content[str(file_path)] = f.read()

        finally:
            for file_path in FEEDS.keys():
                if not os.path.exists(str(file_path)):
                    continue

                os.remove(str(file_path))

        return content

    def get_gzip_compressed(self, data, compresslevel=9, mtime=0, filename=''):
        data_stream = BytesIO()
        gzipf = gzip.GzipFile(fileobj=data_stream, filename=filename, mtime=mtime,
                              compresslevel=compresslevel, mode="wb")
        gzipf.write(data)
        gzipf.close()
        data_stream.seek(0)
        return data_stream.read()

    @defer.inlineCallbacks
    def test_gzip_plugin(self):

        filename = self._named_tempfile('gzip_file')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        try:
            gzip.decompress(data[filename])
        except OSError:
            self.fail("Received invalid gzip data.")

    @defer.inlineCallbacks
    def test_gzip_plugin_compresslevel(self):

        filename_to_compressed = {
            self._named_tempfile('compresslevel_0'): self.get_gzip_compressed(self.expected, compresslevel=0),
            self._named_tempfile('compresslevel_9'): self.get_gzip_compressed(self.expected, compresslevel=9),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('compresslevel_0'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_compresslevel': 0,
                    'gzip_mtime': 0,
                    'gzip_filename': "",
                },
                self._named_tempfile('compresslevel_9'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_compresslevel': 9,
                    'gzip_mtime': 0,
                    'gzip_filename': "",
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_gzip_plugin_mtime(self):
        filename_to_compressed = {
            self._named_tempfile('mtime_123'): self.get_gzip_compressed(self.expected, mtime=123),
            self._named_tempfile('mtime_123456789'): self.get_gzip_compressed(self.expected, mtime=123456789),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('mtime_123'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_mtime': 123,
                    'gzip_filename': "",
                },
                self._named_tempfile('mtime_123456789'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_mtime': 123456789,
                    'gzip_filename': "",
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_gzip_plugin_filename(self):
        filename_to_compressed = {
            self._named_tempfile('filename_FILE1'): self.get_gzip_compressed(self.expected, filename="FILE1"),
            self._named_tempfile('filename_FILE2'): self.get_gzip_compressed(self.expected, filename="FILE2"),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('filename_FILE1'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_mtime': 0,
                    'gzip_filename': "FILE1",
                },
                self._named_tempfile('filename_FILE2'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.GzipPlugin'],
                    'gzip_mtime': 0,
                    'gzip_filename': "FILE2",
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_lzma_plugin(self):

        filename = self._named_tempfile('lzma_file')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        try:
            lzma.decompress(data[filename])
        except lzma.LZMAError:
            self.fail("Received invalid lzma data.")

    @defer.inlineCallbacks
    def test_lzma_plugin_format(self):

        filename_to_compressed = {
            self._named_tempfile('format_FORMAT_XZ'): lzma.compress(self.expected, format=lzma.FORMAT_XZ),
            self._named_tempfile('format_FORMAT_ALONE'): lzma.compress(self.expected, format=lzma.FORMAT_ALONE),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('format_FORMAT_XZ'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_format': lzma.FORMAT_XZ,
                },
                self._named_tempfile('format_FORMAT_ALONE'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_format': lzma.FORMAT_ALONE,
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_lzma_plugin_check(self):

        filename_to_compressed = {
            self._named_tempfile('check_CHECK_NONE'): lzma.compress(self.expected, check=lzma.CHECK_NONE),
            self._named_tempfile('check_CHECK_CRC256'): lzma.compress(self.expected, check=lzma.CHECK_SHA256),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('check_CHECK_NONE'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_check': lzma.CHECK_NONE,
                },
                self._named_tempfile('check_CHECK_CRC256'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_check': lzma.CHECK_SHA256,
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_lzma_plugin_preset(self):

        filename_to_compressed = {
            self._named_tempfile('preset_PRESET_0'): lzma.compress(self.expected, preset=0),
            self._named_tempfile('preset_PRESET_9'): lzma.compress(self.expected, preset=9),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('preset_PRESET_0'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_preset': 0,
                },
                self._named_tempfile('preset_PRESET_9'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_preset': 9,
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_lzma_plugin_filters(self):
        import sys
        if "PyPy" in sys.version:
            # https://foss.heptapod.net/pypy/pypy/-/issues/3527
            raise unittest.SkipTest("lzma filters doesn't work in PyPy")

        filters = [{'id': lzma.FILTER_LZMA2}]
        compressed = lzma.compress(self.expected, filters=filters)
        filename = self._named_tempfile('filters')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.LZMAPlugin'],
                    'lzma_filters': filters,
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        self.assertEqual(compressed, data[filename])
        result = lzma.decompress(data[filename])
        self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_bz2_plugin(self):

        filename = self._named_tempfile('bz2_file')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.Bz2Plugin'],
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        try:
            bz2.decompress(data[filename])
        except OSError:
            self.fail("Received invalid bz2 data.")

    @defer.inlineCallbacks
    def test_bz2_plugin_compresslevel(self):

        filename_to_compressed = {
            self._named_tempfile('compresslevel_1'): bz2.compress(self.expected, compresslevel=1),
            self._named_tempfile('compresslevel_9'): bz2.compress(self.expected, compresslevel=9),
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('compresslevel_1'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.Bz2Plugin'],
                    'bz2_compresslevel': 1,
                },
                self._named_tempfile('compresslevel_9'): {
                    'format': 'csv',
                    'postprocessing': ['scrapy.extensions.postprocessing.Bz2Plugin'],
                    'bz2_compresslevel': 9,
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = bz2.decompress(data[filename])
            self.assertEqual(compressed, data[filename])
            self.assertEqual(self.expected, result)

    @defer.inlineCallbacks
    def test_custom_plugin(self):
        filename = self._named_tempfile('csv_file')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1],
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        self.assertEqual(self.expected, data[filename])

    @defer.inlineCallbacks
    def test_custom_plugin_with_parameter(self):

        expected = b'foo\r\n\nbar\r\n\n'
        filename = self._named_tempfile('newline')

        settings = {
            'FEEDS': {
                filename: {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1],
                    'plugin1_char': b'\n'
                },
            },
        }

        data = yield self.exported_data(self.items, settings)
        self.assertEqual(expected, data[filename])

    @defer.inlineCallbacks
    def test_custom_plugin_with_compression(self):

        expected = b'foo\r\n\nbar\r\n\n'

        filename_to_decompressor = {
            self._named_tempfile('bz2'): bz2.decompress,
            self._named_tempfile('lzma'): lzma.decompress,
            self._named_tempfile('gzip'): gzip.decompress,
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('bz2'): {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1, 'scrapy.extensions.postprocessing.Bz2Plugin'],
                    'plugin1_char': b'\n',
                },
                self._named_tempfile('lzma'): {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1, 'scrapy.extensions.postprocessing.LZMAPlugin'],
                    'plugin1_char': b'\n',
                },
                self._named_tempfile('gzip'): {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1, 'scrapy.extensions.postprocessing.GzipPlugin'],
                    'plugin1_char': b'\n',
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, decompressor in filename_to_decompressor.items():
            result = decompressor(data[filename])
            self.assertEqual(expected, result)

    @defer.inlineCallbacks
    def test_exports_compatibility_with_postproc(self):
        import marshal
        import pickle
        filename_to_expected = {
            self._named_tempfile('csv'): b'foo\r\nbar\r\n',
            self._named_tempfile('json'): b'[\n{"foo": "bar"}\n]',
            self._named_tempfile('jsonlines'): b'{"foo": "bar"}\n',
            self._named_tempfile('xml'): b'<?xml version="1.0" encoding="utf-8"?>\n'
                                         b'<items>\n<item><foo>bar</foo></item>\n</items>',
        }

        settings = {
            'FEEDS': {
                self._named_tempfile('csv'): {
                    'format': 'csv',
                    'postprocessing': [self.MyPlugin1],
                    # empty plugin to activate postprocessing.PostProcessingManager
                },
                self._named_tempfile('json'): {
                    'format': 'json',
                    'postprocessing': [self.MyPlugin1],
                },
                self._named_tempfile('jsonlines'): {
                    'format': 'jsonlines',
                    'postprocessing': [self.MyPlugin1],
                },
                self._named_tempfile('xml'): {
                    'format': 'xml',
                    'postprocessing': [self.MyPlugin1],
                },
                self._named_tempfile('marshal'): {
                    'format': 'marshal',
                    'postprocessing': [self.MyPlugin1],
                },
                self._named_tempfile('pickle'): {
                    'format': 'pickle',
                    'postprocessing': [self.MyPlugin1],
                },
            },
        }

        data = yield self.exported_data(self.items, settings)

        for filename, result in data.items():
            if 'pickle' in filename:
                expected, result = self.items[0], pickle.loads(result)
            elif 'marshal' in filename:
                expected, result = self.items[0], marshal.loads(result)
            else:
                expected = filename_to_expected[filename]
            self.assertEqual(expected, result)


class BatchDeliveriesTest(FeedExportTestBase):
    __test__ = True
    _file_mark = '_%(batch_time)s_#%(batch_id)02d_'

    @defer.inlineCallbacks
    def run_and_export(self, spider_cls, settings):
        """ Run spider with specified settings; return exported data. """

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
    def test_stats_batch_file_success(self):
        settings = {
            "FEEDS": {
                build_url(os.path.join(self._random_temp_filename(), "json", self._file_mark)): {
                    "format": "json",
                }
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(ItemSpider, settings)
        with MockServer() as mockserver:
            yield crawler.crawl(total=2, mockserver=mockserver)
        self.assertIn("feedexport/success_count/FileFeedStorage", crawler.stats.get_stats())
        self.assertEqual(crawler.stats.get_value("feedexport/success_count/FileFeedStorage"), 12)

    @defer.inlineCallbacks
    def test_s3_export(self):
        skip_if_no_boto()

        bucket = 'mybucket'
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            self.MyItem({'foo': 'bar3', 'baz': 'quux3'}),
        ]

        class CustomS3FeedStorage(S3FeedStorage):

            stubs = []

            def open(self, *args, **kwargs):
                from botocore.stub import ANY, Stubber
                stub = Stubber(self.s3_client)
                stub.activate()
                CustomS3FeedStorage.stubs.append(stub)
                stub.add_response(
                    'put_object',
                    expected_params={
                        'Body': ANY,
                        'Bucket': bucket,
                        'Key': ANY,
                    },
                    service_response={},
                )
                return super().open(*args, **kwargs)

        key = 'export.csv'
        uri = f's3://{bucket}/{key}/%(batch_time)s.json'
        batch_item_count = 1
        settings = {
            'AWS_ACCESS_KEY_ID': 'access_key',
            'AWS_SECRET_ACCESS_KEY': 'secret_key',
            'FEED_EXPORT_BATCH_ITEM_COUNT': batch_item_count,
            'FEED_STORAGES': {
                's3': CustomS3FeedStorage,
            },
            'FEEDS': {
                uri: {
                    'format': 'json',
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(crawler, uri)
        verifyObject(IFeedStorage, storage)

        class TestSpider(scrapy.Spider):
            name = 'testspider'

            def parse(self, response):
                for item in items:
                    yield item

        with MockServer() as server:
            runner = CrawlerRunner(Settings(settings))
            TestSpider.start_urls = [server.url('/')]
            yield runner.crawl(TestSpider)

        self.assertEqual(len(CustomS3FeedStorage.stubs), len(items) + 1)
        for stub in CustomS3FeedStorage.stubs[:-1]:
            stub.assert_no_pending_responses()


class FeedExportInitTest(unittest.TestCase):

    def test_unsupported_storage(self):
        settings = {
            'FEEDS': {
                'unsupported://uri': {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with self.assertRaises(NotConfigured):
            FeedExporter.from_crawler(crawler)

    def test_unsupported_format(self):
        settings = {
            'FEEDS': {
                'file://path': {
                    'format': 'unsupported_format',
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with self.assertRaises(NotConfigured):
            FeedExporter.from_crawler(crawler)


class StdoutFeedStorageWithoutFeedOptions(StdoutFeedStorage):

    def __init__(self, uri):
        super().__init__(uri)


class StdoutFeedStoragePreFeedOptionsTest(unittest.TestCase):
    """Make sure that any feed exporter created by users before the
    introduction of the ``feed_options`` parameter continues to work as
    expected, and simply issues a warning."""

    def test_init(self):
        settings_dict = {
            'FEED_URI': 'file:///tmp/foobar',
            'FEED_STORAGES': {
                'file': StdoutFeedStorageWithoutFeedOptions
            },
        }
        crawler = get_crawler(settings_dict=settings_dict)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "StdoutFeedStorageWithoutFeedOptions does not support "
                        "the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )


class FileFeedStorageWithoutFeedOptions(FileFeedStorage):

    def __init__(self, uri):
        super().__init__(uri)


class FileFeedStoragePreFeedOptionsTest(unittest.TestCase):
    """Make sure that any feed exporter created by users before the
    introduction of the ``feed_options`` parameter continues to work as
    expected, and simply issues a warning."""

    maxDiff = None

    def test_init(self):
        with tempfile.NamedTemporaryFile() as temp:
            settings_dict = {
                'FEED_URI': f'file:///{temp.name}',
                'FEED_STORAGES': {
                    'file': FileFeedStorageWithoutFeedOptions
                },
            }
            crawler = get_crawler(settings_dict=settings_dict)
            feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "FileFeedStorageWithoutFeedOptions does not support "
                        "the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )


class S3FeedStorageWithoutFeedOptions(S3FeedStorage):

    def __init__(self, uri, access_key, secret_key, acl, endpoint_url, **kwargs):
        super().__init__(uri, access_key, secret_key, acl, endpoint_url, **kwargs)


class S3FeedStorageWithoutFeedOptionsWithFromCrawler(S3FeedStorage):

    @classmethod
    def from_crawler(cls, crawler, uri):
        return super().from_crawler(crawler, uri)


class S3FeedStoragePreFeedOptionsTest(unittest.TestCase):
    """Make sure that any feed exporter created by users before the
    introduction of the ``feed_options`` parameter continues to work as
    expected, and simply issues a warning."""

    maxDiff = None

    def test_init(self):
        settings_dict = {
            'FEED_URI': 'file:///tmp/foobar',
            'FEED_STORAGES': {
                'file': S3FeedStorageWithoutFeedOptions
            },
        }
        crawler = get_crawler(settings_dict=settings_dict)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "S3FeedStorageWithoutFeedOptions does not support "
                        "the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )

    def test_from_crawler(self):
        settings_dict = {
            'FEED_URI': 'file:///tmp/foobar',
            'FEED_STORAGES': {
                'file': S3FeedStorageWithoutFeedOptionsWithFromCrawler
            },
        }
        crawler = get_crawler(settings_dict=settings_dict)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "S3FeedStorageWithoutFeedOptionsWithFromCrawler.from_crawler "
                        "does not support the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )


class FTPFeedStorageWithoutFeedOptions(FTPFeedStorage):

    def __init__(self, uri, use_active_mode=False):
        super().__init__(uri)


class FTPFeedStorageWithoutFeedOptionsWithFromCrawler(FTPFeedStorage):

    @classmethod
    def from_crawler(cls, crawler, uri):
        return super().from_crawler(crawler, uri)


class FTPFeedStoragePreFeedOptionsTest(unittest.TestCase):
    """Make sure that any feed exporter created by users before the
    introduction of the ``feed_options`` parameter continues to work as
    expected, and simply issues a warning."""

    maxDiff = None

    def test_init(self):
        settings_dict = {
            'FEED_URI': 'file:///tmp/foobar',
            'FEED_STORAGES': {
                'file': FTPFeedStorageWithoutFeedOptions
            },
        }
        crawler = get_crawler(settings_dict=settings_dict)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "FTPFeedStorageWithoutFeedOptions does not support "
                        "the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )

    def test_from_crawler(self):
        settings_dict = {
            'FEED_URI': 'file:///tmp/foobar',
            'FEED_STORAGES': {
                'file': FTPFeedStorageWithoutFeedOptionsWithFromCrawler
            },
        }
        crawler = get_crawler(settings_dict=settings_dict)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        with warnings.catch_warnings(record=True) as w:
            feed_exporter.open_spider(spider)
            messages = tuple(str(item.message) for item in w
                             if item.category is ScrapyDeprecationWarning)
            self.assertEqual(
                messages,
                (
                    (
                        "FTPFeedStorageWithoutFeedOptionsWithFromCrawler.from_crawler "
                        "does not support the 'feed_options' keyword argument. Add a "
                        "'feed_options' parameter to its signature to remove "
                        "this warning. This parameter will become mandatory "
                        "in a future version of Scrapy."
                    ),
                )
            )
