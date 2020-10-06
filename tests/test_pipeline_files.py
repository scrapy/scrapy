import os
import random
import time
from datetime import datetime
from io import BytesIO
from shutil import rmtree
from tempfile import mkdtemp
from unittest import mock, skipIf
from urllib.parse import urlparse

import attr
from itemadapter import ItemAdapter
from twisted.internet import defer
from twisted.trial import unittest

from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.pipelines.files import (
    FilesPipeline,
    FSFilesStore,
    FTPFilesStore,
    GCSFilesStore,
    S3FilesStore,
)
from scrapy.settings import Settings
from scrapy.utils.test import (
    assert_gcs_environ,
    get_ftp_content_and_delete,
    get_gcs_content_and_delete,
    skip_if_no_boto,
)


try:
    from dataclasses import make_dataclass, field as dataclass_field
except ImportError:
    make_dataclass = None
    dataclass_field = None


def _mocked_download_func(request, info):
    response = request.meta.get('response')
    return response() if callable(response) else response


class FilesPipelineTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = mkdtemp()
        self.pipeline = FilesPipeline.from_settings(Settings({'FILES_STORE': self.tempdir}))
        self.pipeline.download_func = _mocked_download_func
        self.pipeline.open_spider(None)

    def tearDown(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        self.assertEqual(
            file_path(Request("https://dev.mydeco.com/mydeco.pdf")),
            'full/c9b564df929f4bc635bdd19fde4f3d4847c757c5.pdf')
        self.assertEqual(
            file_path(Request("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.txt")),
            'full/4ce274dd83db0368bafd7e406f382ae088e39219.txt')
        self.assertEqual(
            file_path(Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.doc")),
            'full/94ccc495a17b9ac5d40e3eabf3afcb8c2c9b9e1a.doc')
        self.assertEqual(
            file_path(Request("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg")),
            'full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532/")),
            'full/97ee6f8a46cbbb418ea91502fd24176865cf39b2')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532")),
            'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532"),
                      response=Response("http://www.dorma.co.uk/images/product_details/2532"),
                      info=object()),
            'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1')
        self.assertEqual(
            file_path(Request("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg.bohaha")),
            'full/76c00cef2ef669ae65052661f68d451162829507')
        self.assertEqual(
            file_path(Request("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAR0AAACxCAMAAADOHZloAAACClBMVEX/\
                                    //+F0tzCwMK76ZKQ21AMqr7oAAC96JvD5aWM2kvZ78J0N7fmAAC46Y4Ap7y")),
            'full/178059cbeba2e34120a67f2dc1afc3ecc09b61cb.png')

    def test_fs_store(self):
        assert isinstance(self.pipeline.store, FSFilesStore)
        self.assertEqual(self.pipeline.store.basedir, self.tempdir)

        path = 'some/image/key.jpg'
        fullpath = os.path.join(self.tempdir, 'some', 'image', 'key.jpg')
        self.assertEqual(self.pipeline.store._get_filesystem_path(path), fullpath)

    @defer.inlineCallbacks
    def test_file_not_expired(self):
        item_url = "http://example.com/file.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, 'inc_stats', return_value=True),
            mock.patch.object(FSFilesStore, 'stat_file', return_value={
                'checksum': 'abc', 'last_modified': time.time()}),
            mock.patch.object(FilesPipeline, 'get_media_requests',
                              return_value=[_prepare_request_object(item_url)])
        ]
        for p in patchers:
            p.start()

        result = yield self.pipeline.process_item(item, None)
        self.assertEqual(result['files'][0]['checksum'], 'abc')
        self.assertEqual(result['files'][0]['status'], 'uptodate')

        for p in patchers:
            p.stop()

    @defer.inlineCallbacks
    def test_file_expired(self):
        item_url = "http://example.com/file2.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FSFilesStore, 'stat_file', return_value={
                'checksum': 'abc',
                'last_modified': time.time() - (self.pipeline.expires * 60 * 60 * 24 * 2)}),
            mock.patch.object(FilesPipeline, 'get_media_requests',
                              return_value=[_prepare_request_object(item_url)]),
            mock.patch.object(FilesPipeline, 'inc_stats', return_value=True)
        ]
        for p in patchers:
            p.start()

        result = yield self.pipeline.process_item(item, None)
        self.assertNotEqual(result['files'][0]['checksum'], 'abc')
        self.assertEqual(result['files'][0]['status'], 'downloaded')

        for p in patchers:
            p.stop()

    @defer.inlineCallbacks
    def test_file_cached(self):
        item_url = "http://example.com/file3.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, 'inc_stats', return_value=True),
            mock.patch.object(FSFilesStore, 'stat_file', return_value={
                'checksum': 'abc',
                'last_modified': time.time() - (self.pipeline.expires * 60 * 60 * 24 * 2)}),
            mock.patch.object(FilesPipeline, 'get_media_requests',
                              return_value=[_prepare_request_object(item_url, flags=['cached'])])
        ]
        for p in patchers:
            p.start()

        result = yield self.pipeline.process_item(item, None)
        self.assertNotEqual(result['files'][0]['checksum'], 'abc')
        self.assertEqual(result['files'][0]['status'], 'cached')

        for p in patchers:
            p.stop()

    def test_file_path_from_item(self):
        """
        Custom file path based on item data, overriding default implementation
        """
        class CustomFilesPipeline(FilesPipeline):
            def file_path(self, request, response=None, info=None, item=None):
                return f'full/{item.get("path")}'

        file_path = CustomFilesPipeline.from_settings(Settings({'FILES_STORE': self.tempdir})).file_path
        item = dict(path='path-to-store-file')
        request = Request("http://example.com")
        self.assertEqual(file_path(request, item=item), 'full/path-to-store-file')


class FilesPipelineTestCaseFieldsMixin:

    def test_item_fields_default(self):
        url = 'http://www.example.com/files/1.txt'
        item = self.item_class(name='item1', file_urls=[url])
        pipeline = FilesPipeline.from_settings(Settings({'FILES_STORE': 's3://example/files/'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        item = pipeline.item_completed(results, item, None)
        files = ItemAdapter(item).get("files")
        self.assertEqual(files, [results[0][1]])
        self.assertIsInstance(item, self.item_class)

    def test_item_fields_override_settings(self):
        url = 'http://www.example.com/files/1.txt'
        item = self.item_class(name='item1', custom_file_urls=[url])
        pipeline = FilesPipeline.from_settings(Settings({
            'FILES_STORE': 's3://example/files/',
            'FILES_URLS_FIELD': 'custom_file_urls',
            'FILES_RESULT_FIELD': 'custom_files'
        }))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        item = pipeline.item_completed(results, item, None)
        custom_files = ItemAdapter(item).get("custom_files")
        self.assertEqual(custom_files, [results[0][1]])
        self.assertIsInstance(item, self.item_class)


class FilesPipelineTestCaseFieldsDict(FilesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = dict


class FilesPipelineTestItem(Item):
    name = Field()
    # default fields
    file_urls = Field()
    files = Field()
    # overridden fields
    custom_file_urls = Field()
    custom_files = Field()


class FilesPipelineTestCaseFieldsItem(FilesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = FilesPipelineTestItem


@skipIf(not make_dataclass, "dataclasses module is not available")
class FilesPipelineTestCaseFieldsDataClass(FilesPipelineTestCaseFieldsMixin, unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if make_dataclass:
            self.item_class = make_dataclass(
                "FilesPipelineTestDataClass",
                [
                    ("name", str),
                    # default fields
                    ("file_urls", list, dataclass_field(default_factory=list)),
                    ("files", list, dataclass_field(default_factory=list)),
                    # overridden fields
                    ("custom_file_urls", list, dataclass_field(default_factory=list)),
                    ("custom_files", list, dataclass_field(default_factory=list)),
                ],
            )


@attr.s
class FilesPipelineTestAttrsItem:
    name = attr.ib(default="")
    # default fields
    file_urls = attr.ib(default=lambda: [])
    files = attr.ib(default=lambda: [])
    # overridden fields
    custom_file_urls = attr.ib(default=lambda: [])
    custom_files = attr.ib(default=lambda: [])


class FilesPipelineTestCaseFieldsAttrsItem(FilesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = FilesPipelineTestAttrsItem


class FilesPipelineTestCaseCustomSettings(unittest.TestCase):
    default_cls_settings = {
        "EXPIRES": 90,
        "FILES_URLS_FIELD": "file_urls",
        "FILES_RESULT_FIELD": "files"
    }
    file_cls_attr_settings_map = {
        ("EXPIRES", "FILES_EXPIRES", "expires"),
        ("FILES_URLS_FIELD", "FILES_URLS_FIELD", "files_urls_field"),
        ("FILES_RESULT_FIELD", "FILES_RESULT_FIELD", "files_result_field")
    }

    def setUp(self):
        self.tempdir = mkdtemp()

    def tearDown(self):
        rmtree(self.tempdir)

    def _generate_fake_settings(self, prefix=None):

        def random_string():
            return "".join([chr(random.randint(97, 123)) for _ in range(10)])

        settings = {
            "FILES_EXPIRES": random.randint(100, 1000),
            "FILES_URLS_FIELD": random_string(),
            "FILES_RESULT_FIELD": random_string(),
            "FILES_STORE": self.tempdir
        }
        if not prefix:
            return settings

        return {prefix.upper() + "_" + k if k != "FILES_STORE" else k: v for k, v in settings.items()}

    def _generate_fake_pipeline(self):

        class UserDefinedFilePipeline(FilesPipeline):
            EXPIRES = 1001
            FILES_URLS_FIELD = "alfa"
            FILES_RESULT_FIELD = "beta"

        return UserDefinedFilePipeline

    def test_different_settings_for_different_instances(self):
        """
        If there are different instances with different settings they should keep
        different settings.
        """
        custom_settings = self._generate_fake_settings()
        another_pipeline = FilesPipeline.from_settings(Settings(custom_settings))
        one_pipeline = FilesPipeline(self.tempdir)
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            default_value = self.default_cls_settings[pipe_attr]
            self.assertEqual(getattr(one_pipeline, pipe_attr), default_value)
            custom_value = custom_settings[settings_attr]
            self.assertNotEqual(default_value, custom_value)
            self.assertEqual(getattr(another_pipeline, pipe_ins_attr), custom_value)

    def test_subclass_attributes_preserved_if_no_settings(self):
        """
        If subclasses override class attributes and there are no special settings those values should be kept.
        """
        pipe_cls = self._generate_fake_pipeline()
        pipe = pipe_cls.from_settings(Settings({"FILES_STORE": self.tempdir}))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            custom_value = getattr(pipe, pipe_ins_attr)
            self.assertNotEqual(custom_value, self.default_cls_settings[pipe_attr])
            self.assertEqual(getattr(pipe, pipe_ins_attr), getattr(pipe, pipe_attr))

    def test_subclass_attrs_preserved_custom_settings(self):
        """
        If file settings are defined but they are not defined for subclass
        settings should be preserved.
        """
        pipeline_cls = self._generate_fake_pipeline()
        settings = self._generate_fake_settings()
        pipeline = pipeline_cls.from_settings(Settings(settings))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            value = getattr(pipeline, pipe_ins_attr)
            setting_value = settings.get(settings_attr)
            self.assertNotEqual(value, self.default_cls_settings[pipe_attr])
            self.assertEqual(value, setting_value)

    def test_no_custom_settings_for_subclasses(self):
        """
        If there are no settings for subclass and no subclass attributes, pipeline should use
        attributes of base class.
        """
        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        user_pipeline = UserDefinedFilesPipeline.from_settings(Settings({"FILES_STORE": self.tempdir}))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = self.default_cls_settings.get(pipe_attr.upper())
            self.assertEqual(getattr(user_pipeline, pipe_ins_attr), custom_value)

    def test_custom_settings_for_subclasses(self):
        """
        If there are custom settings for subclass and NO class attributes, pipeline should use custom
        settings.
        """
        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        prefix = UserDefinedFilesPipeline.__name__.upper()
        settings = self._generate_fake_settings(prefix=prefix)
        user_pipeline = UserDefinedFilesPipeline.from_settings(Settings(settings))
        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = settings.get(prefix + "_" + settings_attr)
            self.assertNotEqual(custom_value, self.default_cls_settings[pipe_attr])
            self.assertEqual(getattr(user_pipeline, pipe_inst_attr), custom_value)

    def test_custom_settings_and_class_attrs_for_subclasses(self):
        """
        If there are custom settings for subclass AND class attributes
        setting keys are preferred and override attributes.
        """
        pipeline_cls = self._generate_fake_pipeline()
        prefix = pipeline_cls.__name__.upper()
        settings = self._generate_fake_settings(prefix=prefix)
        user_pipeline = pipeline_cls.from_settings(Settings(settings))
        for pipe_cls_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            custom_value = settings.get(prefix + "_" + settings_attr)
            self.assertNotEqual(custom_value, self.default_cls_settings[pipe_cls_attr])
            self.assertEqual(getattr(user_pipeline, pipe_inst_attr), custom_value)

    def test_cls_attrs_with_DEFAULT_prefix(self):
        class UserDefinedFilesPipeline(FilesPipeline):
            DEFAULT_FILES_RESULT_FIELD = "this"
            DEFAULT_FILES_URLS_FIELD = "that"

        pipeline = UserDefinedFilesPipeline.from_settings(Settings({"FILES_STORE": self.tempdir}))
        self.assertEqual(pipeline.files_result_field, "this")
        self.assertEqual(pipeline.files_urls_field, "that")

    def test_user_defined_subclass_default_key_names(self):
        """Test situation when user defines subclass of FilesPipeline,
        but uses attribute names for default pipeline (without prefixing
        them with pipeline class name).
        """
        settings = self._generate_fake_settings()

        class UserPipe(FilesPipeline):
            pass

        pipeline_cls = UserPipe.from_settings(Settings(settings))

        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            expected_value = settings.get(settings_attr)
            self.assertEqual(getattr(pipeline_cls, pipe_inst_attr),
                             expected_value)


class TestS3FilesStore(unittest.TestCase):

    @defer.inlineCallbacks
    def test_persist(self):
        skip_if_no_boto()

        bucket = 'mybucket'
        key = 'export.csv'
        uri = f's3://{bucket}/{key}'
        buffer = mock.MagicMock()
        meta = {'foo': 'bar'}
        path = ''
        content_type = 'image/png'

        store = S3FilesStore(uri)
        from botocore.stub import Stubber
        with Stubber(store.s3_client) as stub:
            stub.add_response(
                'put_object',
                expected_params={
                    'ACL': S3FilesStore.POLICY,
                    'Body': buffer,
                    'Bucket': bucket,
                    'CacheControl': S3FilesStore.HEADERS['Cache-Control'],
                    'ContentType': content_type,
                    'Key': key,
                    'Metadata': meta,
                },
                service_response={},
            )

            yield store.persist_file(
                path,
                buffer,
                info=None,
                meta=meta,
                headers={'Content-Type': content_type},
            )

            stub.assert_no_pending_responses()
            self.assertEqual(
                buffer.method_calls,
                [
                    mock.call.seek(0),
                    # The call to read does not happen with Stubber
                ]
            )

    @defer.inlineCallbacks
    def test_stat(self):
        skip_if_no_boto()

        bucket = 'mybucket'
        key = 'export.csv'
        uri = f's3://{bucket}/{key}'
        checksum = '3187896a9657a28163abb31667df64c8'
        last_modified = datetime(2019, 12, 1)

        store = S3FilesStore(uri)
        from botocore.stub import Stubber
        with Stubber(store.s3_client) as stub:
            stub.add_response(
                'head_object',
                expected_params={
                    'Bucket': bucket,
                    'Key': key,
                },
                service_response={
                    'ETag': f'"{checksum}"',
                    'LastModified': last_modified,
                },
            )

            file_stats = yield store.stat_file('', info=None)
            self.assertEqual(
                file_stats,
                {
                    'checksum': checksum,
                    'last_modified': last_modified.timestamp(),
                },
            )

            stub.assert_no_pending_responses()


class TestGCSFilesStore(unittest.TestCase):
    @defer.inlineCallbacks
    def test_persist(self):
        assert_gcs_environ()
        uri = os.environ.get('GCS_TEST_FILE_URI')
        if not uri:
            raise unittest.SkipTest("No GCS URI available for testing")
        data = b"TestGCSFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {'foo': 'bar'}
        path = 'full/filename'
        store = GCSFilesStore(uri)
        store.POLICY = 'authenticatedRead'
        expected_policy = {'role': 'READER', 'entity': 'allAuthenticatedUsers'}
        yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
        s = yield store.stat_file(path, info=None)
        self.assertIn('last_modified', s)
        self.assertIn('checksum', s)
        self.assertEqual(s['checksum'], 'zc2oVgXkbQr2EQdSdw3OPA==')
        u = urlparse(uri)
        content, acl, blob = get_gcs_content_and_delete(u.hostname, u.path[1:] + path)
        self.assertEqual(content, data)
        self.assertEqual(blob.metadata, {'foo': 'bar'})
        self.assertEqual(blob.cache_control, GCSFilesStore.CACHE_CONTROL)
        self.assertEqual(blob.content_type, 'application/octet-stream')
        self.assertIn(expected_policy, acl)


class TestFTPFileStore(unittest.TestCase):
    @defer.inlineCallbacks
    def test_persist(self):
        uri = os.environ.get('FTP_TEST_FILE_URI')
        if not uri:
            raise unittest.SkipTest("No FTP URI available for testing")
        data = b"TestFTPFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {'foo': 'bar'}
        path = 'full/filename'
        store = FTPFilesStore(uri)
        empty_dict = yield store.stat_file(path, info=None)
        self.assertEqual(empty_dict, {})
        yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
        stat = yield store.stat_file(path, info=None)
        self.assertIn('last_modified', stat)
        self.assertIn('checksum', stat)
        self.assertEqual(stat['checksum'], 'd113d66b2ec7258724a268bd88eef6b6')
        path = f'{store.basedir}/{path}'
        content = get_ftp_content_and_delete(
            path, store.host, store.port,
            store.username, store.password, store.USE_ACTIVE_MODE)
        self.assertEqual(data.decode(), content)


class ItemWithFiles(Item):
    file_urls = Field()
    files = Field()


def _create_item_with_files(*files):
    item = ItemWithFiles()
    item['file_urls'] = files
    return item


def _prepare_request_object(item_url, flags=None):
    return Request(
        item_url,
        meta={'response': Response(item_url, status=200, body=b'data', flags=flags)})


if __name__ == "__main__":
    unittest.main()
