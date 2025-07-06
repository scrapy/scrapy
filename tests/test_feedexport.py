from __future__ import annotations

import bz2
import csv
import gzip
import json
import lzma
import marshal
import os
import pickle
import random
import shutil
import string
import sys
import tempfile
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from io import BytesIO
from logging import getLogger
from pathlib import Path
from string import ascii_letters, digits
from typing import IO, TYPE_CHECKING, Any
from unittest import mock
from urllib.parse import quote, urljoin
from urllib.request import pathname2url

import lxml.etree
import pytest
from packaging.version import Version
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks
from w3lib.url import file_uri_to_path, path_to_file_uri
from zope.interface import implementer
from zope.interface.verify import verifyObject

import scrapy
from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.exporters import CsvItemExporter, JsonItemExporter
from scrapy.extensions.feedexport import (
    BlockingFeedStorage,
    FeedExporter,
    FeedSlot,
    FileFeedStorage,
    FTPFeedStorage,
    GCSFeedStorage,
    IFeedStorage,
    S3FeedStorage,
    StdoutFeedStorage,
)
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler
from tests.mockserver import MockFTPServer, MockServer
from tests.spiders import ItemSpider

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike


def path_to_url(path):
    return urljoin("file:", pathname2url(str(path)))


def printf_escape(string):
    return string.replace("%", "%%")


def build_url(path: str | PathLike) -> str:
    path_str = str(path)
    if path_str[0] != "/":
        path_str = "/" + path_str
    return urljoin("file:", path_str)


def mock_google_cloud_storage() -> tuple[Any, Any, Any]:
    """Creates autospec mocks for google-cloud-storage Client, Bucket and Blob
    classes and set their proper return values.
    """
    from google.cloud.storage import Blob, Bucket, Client  # noqa: PLC0415

    client_mock = mock.create_autospec(Client)

    bucket_mock = mock.create_autospec(Bucket)
    client_mock.get_bucket.return_value = bucket_mock

    blob_mock = mock.create_autospec(Blob)
    bucket_mock.blob.return_value = blob_mock

    return (client_mock, bucket_mock, blob_mock)


class TestFileFeedStorage:
    def test_store_file_uri(self, tmp_path):
        path = tmp_path / "file.txt"
        uri = path_to_file_uri(str(path))
        self._assert_stores(FileFeedStorage(uri), path)

    def test_store_file_uri_makedirs(self, tmp_path):
        path = tmp_path / "more" / "paths" / "file.txt"
        uri = path_to_file_uri(str(path))
        self._assert_stores(FileFeedStorage(uri), path)

    def test_store_direct_path(self, tmp_path):
        path = tmp_path / "file.txt"
        self._assert_stores(FileFeedStorage(str(path)), path)

    def test_store_direct_path_relative(self, tmp_path):
        old_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            path = Path("foo", "bar")
            self._assert_stores(FileFeedStorage(str(path)), path)
        finally:
            os.chdir(old_cwd)

    def test_interface(self, tmp_path):
        path = tmp_path / "file.txt"
        st = FileFeedStorage(str(path))
        verifyObject(IFeedStorage, st)

    @staticmethod
    def _store(path: Path, feed_options: dict[str, Any] | None = None) -> None:
        storage = FileFeedStorage(str(path), feed_options=feed_options)
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        storage.store(file)

    def test_append(self, tmp_path):
        path = tmp_path / "file.txt"
        self._store(path)
        self._assert_stores(FileFeedStorage(str(path)), path, b"contentcontent")

    def test_overwrite(self, tmp_path):
        path = tmp_path / "file.txt"
        self._store(path, {"overwrite": True})
        self._assert_stores(
            FileFeedStorage(str(path), feed_options={"overwrite": True}), path
        )

    @staticmethod
    def _assert_stores(
        storage: FileFeedStorage, path: Path, expected_content: bytes = b"content"
    ) -> None:
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        storage.store(file)
        assert path.exists()
        try:
            assert path.read_bytes() == expected_content
        finally:
            path.unlink()

    def test_preserves_windows_path_without_file_scheme(self):
        path = r"C:\Users\user\Desktop\test.txt"
        storage = FileFeedStorage(path)
        assert storage.path == path


class TestFTPFeedStorage:
    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = "test_spider"

        crawler = get_crawler(settings_dict=settings)
        return TestSpider.from_crawler(crawler)

    async def _store(self, uri, content, feed_options=None, settings=None):
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
        await maybe_deferred_to_future(storage.store(file))

    def _assert_stored(self, path: Path, content):
        assert path.exists()
        try:
            assert path.read_bytes() == content
        finally:
            path.unlink()

    @deferred_f_from_coro_f
    async def test_append(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"overwrite": False}
            await self._store(url, b"foo", feed_options=feed_options)
            await self._store(url, b"bar", feed_options=feed_options)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @deferred_f_from_coro_f
    async def test_overwrite(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            await self._store(url, b"foo")
            await self._store(url, b"bar")
            self._assert_stored(ftp_server.path / filename, b"bar")

    @deferred_f_from_coro_f
    async def test_append_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {"FEED_STORAGE_FTP_ACTIVE": True}
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"overwrite": False}
            await self._store(url, b"foo", feed_options=feed_options, settings=settings)
            await self._store(url, b"bar", feed_options=feed_options, settings=settings)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @deferred_f_from_coro_f
    async def test_overwrite_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {"FEED_STORAGE_FTP_ACTIVE": True}
            filename = "file"
            url = ftp_server.url(filename)
            await self._store(url, b"foo", settings=settings)
            await self._store(url, b"bar", settings=settings)
            self._assert_stored(ftp_server.path / filename, b"bar")

    def test_uri_auth_quote(self):
        # RFC3986: 3.2.1. User Information
        pw_quoted = quote(string.punctuation, safe="")
        st = FTPFeedStorage(f"ftp://foo:{pw_quoted}@example.com/some_path", {})
        assert st.password == string.punctuation


class MyBlockingFeedStorage(BlockingFeedStorage):
    def _store_in_thread(self, file: IO[bytes]) -> None:
        return


class TestBlockingFeedStorage:
    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = "test_spider"

        crawler = get_crawler(settings_dict=settings)
        return TestSpider.from_crawler(crawler)

    def test_default_temp_dir(self):
        b = MyBlockingFeedStorage()

        storage_file = b.open(self.get_test_spider())
        storage_dir = Path(storage_file.name).parent
        assert str(storage_dir) == tempfile.gettempdir()

    def test_temp_file(self, tmp_path):
        b = MyBlockingFeedStorage()

        spider = self.get_test_spider({"FEED_TEMPDIR": str(tmp_path)})
        storage_file = b.open(spider)
        storage_dir = Path(storage_file.name).parent
        assert storage_dir == tmp_path

    def test_invalid_folder(self, tmp_path):
        b = MyBlockingFeedStorage()

        invalid_path = tmp_path / "invalid_path"
        spider = self.get_test_spider({"FEED_TEMPDIR": str(invalid_path)})

        with pytest.raises(OSError, match="Not a Directory:"):
            b.open(spider=spider)


@pytest.mark.requires_boto3
class TestS3FeedStorage:
    def test_parse_credentials(self):
        aws_credentials = {
            "AWS_ACCESS_KEY_ID": "settings_key",
            "AWS_SECRET_ACCESS_KEY": "settings_secret",
            "AWS_SESSION_TOKEN": "settings_token",
        }
        crawler = get_crawler(settings_dict=aws_credentials)
        # Instantiate with crawler
        storage = S3FeedStorage.from_crawler(
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "settings_key"
        assert storage.secret_key == "settings_secret"
        assert storage.session_token == "settings_token"
        # Instantiate directly
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            aws_credentials["AWS_ACCESS_KEY_ID"],
            aws_credentials["AWS_SECRET_ACCESS_KEY"],
            session_token=aws_credentials["AWS_SESSION_TOKEN"],
        )
        assert storage.access_key == "settings_key"
        assert storage.secret_key == "settings_secret"
        assert storage.session_token == "settings_token"
        # URI priority > settings priority
        storage = S3FeedStorage(
            "s3://uri_key:uri_secret@mybucket/export.csv",
            aws_credentials["AWS_ACCESS_KEY_ID"],
            aws_credentials["AWS_SECRET_ACCESS_KEY"],
        )
        assert storage.access_key == "uri_key"
        assert storage.secret_key == "uri_secret"

    @deferred_f_from_coro_f
    async def test_store(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
        }
        crawler = get_crawler(settings_dict=settings)
        bucket = "mybucket"
        key = "export.csv"
        storage = S3FeedStorage.from_crawler(crawler, f"s3://{bucket}/{key}")
        verifyObject(IFeedStorage, storage)

        file = mock.MagicMock()

        storage.s3_client = mock.MagicMock()
        await maybe_deferred_to_future(storage.store(file))
        assert storage.s3_client.upload_fileobj.call_args == mock.call(
            Bucket=bucket, Key=key, Fileobj=file
        )

    def test_init_without_acl(self):
        storage = S3FeedStorage("s3://mybucket/export.csv", "access_key", "secret_key")
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl is None

    def test_init_with_acl(self):
        storage = S3FeedStorage(
            "s3://mybucket/export.csv", "access_key", "secret_key", "custom-acl"
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl == "custom-acl"

    def test_init_with_endpoint_url(self):
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            endpoint_url="https://example.com",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.endpoint_url == "https://example.com"

    def test_init_with_region_name(self):
        region_name = "ap-east-1"
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            region_name=region_name,
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.region_name == region_name
        assert storage.s3_client._client_config.region_name == region_name

    def test_from_crawler_without_acl(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl is None

    def test_without_endpoint_url(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.endpoint_url is None

    def test_without_region_name(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.s3_client._client_config.region_name == "us-east-1"

    def test_from_crawler_with_acl(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "FEED_STORAGE_S3_ACL": "custom-acl",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl == "custom-acl"

    def test_from_crawler_with_endpoint_url(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "AWS_ENDPOINT_URL": "https://example.com",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(crawler, "s3://mybucket/export.csv")
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.endpoint_url == "https://example.com"

    def test_from_crawler_with_region_name(self):
        region_name = "ap-east-1"
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "AWS_REGION_NAME": region_name,
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(crawler, "s3://mybucket/export.csv")
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.region_name == region_name
        assert storage.s3_client._client_config.region_name == region_name

    @deferred_f_from_coro_f
    async def test_store_without_acl(self):
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl is None

        storage.s3_client = mock.MagicMock()
        await maybe_deferred_to_future(storage.store(BytesIO(b"test file")))
        acl = (
            storage.s3_client.upload_fileobj.call_args[1]
            .get("ExtraArgs", {})
            .get("ACL")
        )
        assert acl is None

    @deferred_f_from_coro_f
    async def test_store_with_acl(self):
        storage = S3FeedStorage(
            "s3://mybucket/export.csv", "access_key", "secret_key", "custom-acl"
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.acl == "custom-acl"

        storage.s3_client = mock.MagicMock()
        await maybe_deferred_to_future(storage.store(BytesIO(b"test file")))
        acl = storage.s3_client.upload_fileobj.call_args[1]["ExtraArgs"]["ACL"]
        assert acl == "custom-acl"

    def test_overwrite_default(self):
        with LogCapture() as log:
            S3FeedStorage(
                "s3://mybucket/export.csv", "access_key", "secret_key", "custom-acl"
            )
        assert "S3 does not support appending to files" not in str(log)

    def test_overwrite_false(self):
        with LogCapture() as log:
            S3FeedStorage(
                "s3://mybucket/export.csv",
                "access_key",
                "secret_key",
                "custom-acl",
                feed_options={"overwrite": False},
            )
        assert "S3 does not support appending to files" in str(log)


class TestGCSFeedStorage:
    def test_parse_settings(self):
        try:
            from google.cloud.storage import Client  # noqa: F401,PLC0415
        except ImportError:
            pytest.skip("GCSFeedStorage requires google-cloud-storage")

        settings = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": "publicRead"}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, "gs://mybucket/export.csv")
        assert storage.project_id == "123"
        assert storage.acl == "publicRead"
        assert storage.bucket_name == "mybucket"
        assert storage.blob_name == "export.csv"

    def test_parse_empty_acl(self):
        try:
            from google.cloud.storage import Client  # noqa: F401,PLC0415
        except ImportError:
            pytest.skip("GCSFeedStorage requires google-cloud-storage")

        settings = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": ""}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, "gs://mybucket/export.csv")
        assert storage.acl is None

        settings = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": None}
        crawler = get_crawler(settings_dict=settings)
        storage = GCSFeedStorage.from_crawler(crawler, "gs://mybucket/export.csv")
        assert storage.acl is None

    @deferred_f_from_coro_f
    async def test_store(self):
        try:
            from google.cloud.storage import Client  # noqa: F401,PLC0415
        except ImportError:
            pytest.skip("GCSFeedStorage requires google-cloud-storage")

        uri = "gs://mybucket/export.csv"
        project_id = "myproject-123"
        acl = "publicRead"
        (client_mock, bucket_mock, blob_mock) = mock_google_cloud_storage()
        with mock.patch("google.cloud.storage.Client") as m:
            m.return_value = client_mock

            f = mock.Mock()
            storage = GCSFeedStorage(uri, project_id, acl)
            await maybe_deferred_to_future(storage.store(f))

            f.seek.assert_called_once_with(0)
            m.assert_called_once_with(project=project_id)
            client_mock.get_bucket.assert_called_once_with("mybucket")
            bucket_mock.blob.assert_called_once_with("export.csv")
            blob_mock.upload_from_file.assert_called_once_with(f, predefined_acl=acl)

    def test_overwrite_default(self):
        with LogCapture() as log:
            GCSFeedStorage("gs://mybucket/export.csv", "myproject-123", "custom-acl")
        assert "GCS does not support appending to files" not in str(log)

    def test_overwrite_false(self):
        with LogCapture() as log:
            GCSFeedStorage(
                "gs://mybucket/export.csv",
                "myproject-123",
                "custom-acl",
                feed_options={"overwrite": False},
            )
        assert "GCS does not support appending to files" in str(log)


class TestStdoutFeedStorage:
    def test_store(self):
        out = BytesIO()
        storage = StdoutFeedStorage("stdout:", _stdout=out)
        file = storage.open(scrapy.Spider("default"))
        file.write(b"content")
        storage.store(file)
        assert out.getvalue() == b"content"

    def test_overwrite_default(self):
        with LogCapture() as log:
            StdoutFeedStorage("stdout:")
        assert (
            "Standard output (stdout) storage does not support overwriting"
            not in str(log)
        )

    def test_overwrite_true(self):
        with LogCapture() as log:
            StdoutFeedStorage("stdout:", feed_options={"overwrite": True})
        assert "Standard output (stdout) storage does not support overwriting" in str(
            log
        )


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
        self.path = Path(file_uri_to_path(uri))

    def _store_in_thread(self, file):
        dirname = self.path.parent
        if dirname and not dirname.exists():
            dirname.mkdir(parents=True)
        with self.path.open("ab") as output_file:
            output_file.write(file.read())

        file.close()


class FailingBlockingFeedStorage(DummyBlockingFeedStorage):
    def _store_in_thread(self, file):
        raise OSError("Cannot store")


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
        return tempfile.NamedTemporaryFile(prefix="feed-")

    def store(self, file):
        self.logger.info("Storage.store is called")
        file.close()


class TestFeedExportBase(ABC):
    mockserver: MockServer

    class MyItem(scrapy.Item):
        foo = scrapy.Field()
        egg = scrapy.Field()
        baz = scrapy.Field()

    class MyItem2(scrapy.Item):
        foo = scrapy.Field()
        hello = scrapy.Field()

    def _random_temp_filename(self, inter_dir="") -> Path:
        chars = [random.choice(ascii_letters + digits) for _ in range(15)]
        filename = "".join(chars)
        return Path(self.temp_dir, inter_dir, filename)

    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def exported_data(
        self, items: Iterable[Any], settings: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Return exported data which a spider yielding ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                yield from items

        return await self.run_and_export(TestSpider, settings)

    async def exported_no_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        """
        Return exported data which a spider yielding no ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                pass

        return await self.run_and_export(TestSpider, settings)

    async def assertExported(
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        await self.assertExportedCsv(items, header, rows, settings)
        await self.assertExportedJsonLines(items, rows, settings)
        await self.assertExportedXml(items, rows, settings)
        await self.assertExportedPickle(items, rows, settings)
        await self.assertExportedMarshal(items, rows, settings)
        await self.assertExportedMultiple(items, rows, settings)

    async def assertExportedCsv(  # noqa: B027
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedJsonLines(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedXml(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMultiple(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedPickle(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMarshal(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, Any]:
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


class InstrumentedFeedSlot(FeedSlot):
    """Instrumented FeedSlot subclass for keeping track of calls to
    start_exporting and finish_exporting."""

    def start_exporting(self):
        self.update_listener("start")
        super().start_exporting()

    def finish_exporting(self):
        self.update_listener("finish")
        super().finish_exporting()

    @classmethod
    def subscribe__listener(cls, listener):
        cls.update_listener = listener.update


class IsExportingListener:
    """When subscribed to InstrumentedFeedSlot, keeps track of when
    a call to start_exporting has been made without a closing call to
    finish_exporting and when a call to finish_exporting has been made
    before a call to start_exporting."""

    def __init__(self):
        self.start_without_finish = False
        self.finish_without_start = False

    def update(self, method):
        if method == "start":
            self.start_without_finish = True
        elif method == "finish":
            if self.start_without_finish:
                self.start_without_finish = False
            else:
                self.finish_before_start = True


class ExceptionJsonItemExporter(JsonItemExporter):
    """JsonItemExporter that throws an exception every time export_item is called."""

    def export_item(self, _):
        raise RuntimeError("foo")


class TestFeedExport(TestFeedExportBase):
    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Run spider with specified settings; return exported data."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content: dict[str, Any] = {}
        try:
            spider_cls.start_urls = [self.mockserver.url("/")]
            crawler = get_crawler(spider_cls, settings)
            await maybe_deferred_to_future(crawler.crawl())

            for file_path, feed_options in FEEDS.items():
                content[feed_options["format"]] = (
                    Path(file_path).read_bytes() if Path(file_path).exists() else None
                )

        finally:
            for file_path in FEEDS:
                if not Path(file_path).exists():
                    continue

                Path(file_path).unlink()

        return content

    async def assertExportedCsv(
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "csv"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        reader = csv.DictReader(to_unicode(data["csv"]).splitlines())
        assert reader.fieldnames == list(header)
        assert rows == list(reader)

    async def assertExportedJsonLines(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "jl"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        parsed = [json.loads(to_unicode(line)) for line in data["jl"].splitlines()]
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        assert rows == parsed

    async def assertExportedXml(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "xml"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        root = lxml.etree.fromstring(data["xml"])
        got_rows = [{e.tag: e.text for e in it} for it in root.findall("item")]
        assert rows == got_rows

    async def assertExportedMultiple(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "xml"},
                    self._random_temp_filename(): {"format": "json"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        # XML
        root = lxml.etree.fromstring(data["xml"])
        xml_rows = [{e.tag: e.text for e in it} for it in root.findall("item")]
        assert rows == xml_rows
        # JSON
        json_rows = json.loads(to_unicode(data["json"]))
        assert rows == json_rows

    async def assertExportedPickle(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "pickle"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]

        result = self._load_until_eof(data["pickle"], load_func=pickle.load)
        assert result == expected

    async def assertExportedMarshal(
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename(): {"format": "marshal"},
                },
            }
        )
        data = await self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]

        result = self._load_until_eof(data["marshal"], load_func=marshal.load)
        assert result == expected

    @inlineCallbacks
    def test_stats_file_success(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1

    @inlineCallbacks
    def test_stats_file_failed(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                }
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with mock.patch(
            "scrapy.extensions.feedexport.FileFeedStorage.store",
            side_effect=KeyError("foo"),
        ):
            yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/failed_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/failed_count/FileFeedStorage") == 1

    @inlineCallbacks
    def test_stats_multiple_file(self):
        settings = {
            "FEEDS": {
                printf_escape(path_to_url(str(self._random_temp_filename()))): {
                    "format": "json",
                },
                "stdout:": {
                    "format": "xml",
                },
            },
        }
        crawler = get_crawler(ItemSpider, settings)
        with mock.patch.object(S3FeedStorage, "store"):
            yield crawler.crawl(mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert "feedexport/success_count/StdoutFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 1
        assert (
            crawler.stats.get_value("feedexport/success_count/StdoutFeedStorage") == 1
        )

    @deferred_f_from_coro_f
    async def test_export_items(self):
        # feed exporters use field names from Item
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
        ]
        rows = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
        ]
        header = self.MyItem.fields.keys()
        await self.assertExported(items, header, rows)

    @deferred_f_from_coro_f
    async def test_export_no_items_not_store_empty(self):
        for fmt in ("json", "jsonlines", "xml", "csv"):
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_STORE_EMPTY": False,
            }
            data = await self.exported_no_data(settings)
            assert data[fmt] is None

    @deferred_f_from_coro_f
    async def test_start_finish_exporting_items(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @deferred_f_from_coro_f
    async def test_start_finish_exporting_no_items(self):
        items = []
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @deferred_f_from_coro_f
    async def test_start_finish_exporting_items_exception(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @deferred_f_from_coro_f
    async def test_start_finish_exporting_no_items_exception(self):
        items = []
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
            },
            "FEED_EXPORTERS": {"json": ExceptionJsonItemExporter},
            "FEED_EXPORT_INDENT": None,
        }

        listener = IsExportingListener()
        InstrumentedFeedSlot.subscribe__listener(listener)

        with mock.patch("scrapy.extensions.feedexport.FeedSlot", InstrumentedFeedSlot):
            await self.exported_data(items, settings)
            assert not listener.start_without_finish
            assert not listener.finish_without_start

    @deferred_f_from_coro_f
    async def test_export_no_items_store_empty(self):
        formats = (
            ("json", b"[]"),
            ("jsonlines", b""),
            ("xml", b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ("csv", b""),
        )

        for fmt, expctd in formats:
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_INDENT": None,
            }
            data = await self.exported_no_data(settings)
            assert expctd == data[fmt]

    @deferred_f_from_coro_f
    async def test_export_no_items_multiple_feeds(self):
        """Make sure that `storage.store` is called for every feed."""
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": LogOnStoreFileStorage},
            "FEED_STORE_EMPTY": False,
        }

        with LogCapture() as log:
            await self.exported_no_data(settings)

        assert str(log).count("Storage.store is called") == 0

    @deferred_f_from_coro_f
    async def test_export_multiple_item_classes(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            self.MyItem({"foo": "bar3", "egg": "spam3", "baz": "quux3"}),
            {"hello": "world4", "egg": "spam4"},
        ]

        # by default, Scrapy uses fields of the first Item for CSV and
        # all fields for JSON Lines
        header = self.MyItem.fields.keys()
        rows_csv = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "", "foo": "bar2", "baz": ""},
            {"egg": "spam3", "foo": "bar3", "baz": "quux3"},
            {"egg": "spam4", "foo": "", "baz": ""},
        ]
        rows_jl = [dict(row) for row in items]
        await self.assertExportedCsv(items, header, rows_csv)
        await self.assertExportedJsonLines(items, rows_jl)

    @deferred_f_from_coro_f
    async def test_export_items_empty_field_list(self):
        # FEED_EXPORT_FIELDS==[] means the same as default None
        items = [{"foo": "bar"}]
        header = ["foo"]
        rows = [{"foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": []}
        await self.assertExportedCsv(items, header, rows)
        await self.assertExportedJsonLines(items, rows, settings)

    @deferred_f_from_coro_f
    async def test_export_items_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, header, rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_items_comma_separated_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": ",".join(header)}
        await self.assertExported(items, header, rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_items_json_field_list(self):
        items = [{"foo": "bar"}]
        header = ["foo", "baz"]
        rows = [{"foo": "bar", "baz": ""}]
        settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
        await self.assertExported(items, header, rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_items_field_names(self):
        items = [{"foo": "bar"}]
        header = {"foo": "Foo"}
        rows = [{"Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, list(header.values()), rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_items_dict_field_names(self):
        items = [{"foo": "bar"}]
        header = {
            "baz": "Baz",
            "foo": "Foo",
        }
        rows = [{"Baz": "", "Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": header}
        await self.assertExported(items, ["Baz", "Foo"], rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_items_json_field_names(self):
        items = [{"foo": "bar"}]
        header = {"foo": "Foo"}
        rows = [{"Foo": "bar"}]
        settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
        await self.assertExported(items, list(header.values()), rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_based_on_item_classes(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            {"hello": "world3", "egg": "spam3"},
        ]

        formats = {
            "csv": b"baz,egg,foo\r\n,spam1,bar1\r\n",
            "json": b'[\n{"hello": "world2", "foo": "bar2"}\n]',
            "jsonlines": (
                b'{"foo": "bar1", "egg": "spam1"}\n{"hello": "world2", "foo": "bar2"}\n'
            ),
            "xml": (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>"
                b"world2</hello><foo>bar2</foo></item>\n<item><hello>world3"
                b"</hello><egg>spam3</egg></item>\n</items>"
            ),
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "csv",
                    "item_classes": [self.MyItem],
                },
                self._random_temp_filename(): {
                    "format": "json",
                    "item_classes": [self.MyItem2],
                },
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "item_classes": [self.MyItem, self.MyItem2],
                },
                self._random_temp_filename(): {
                    "format": "xml",
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @deferred_f_from_coro_f
    async def test_export_based_on_custom_filters(self):
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem2({"hello": "world2", "foo": "bar2"}),
            {"hello": "world3", "egg": "spam3"},
        ]

        MyItem = self.MyItem

        class CustomFilter1:
            def __init__(self, feed_options):
                pass

            def accepts(self, item):
                return isinstance(item, MyItem)

        class CustomFilter2(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                return "foo" in item.fields

        class CustomFilter3(scrapy.extensions.feedexport.ItemFilter):
            def accepts(self, item):
                return (
                    isinstance(item, tuple(self.item_classes)) and item["foo"] == "bar1"
                )

        formats = {
            "json": b'[\n{"foo": "bar1", "egg": "spam1"}\n]',
            "xml": (
                b'<?xml version="1.0" encoding="utf-8"?>\n<items>\n<item>'
                b"<foo>bar1</foo><egg>spam1</egg></item>\n<item><hello>"
                b"world2</hello><foo>bar2</foo></item>\n</items>"
            ),
            "jsonlines": b'{"foo": "bar1", "egg": "spam1"}\n',
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "json",
                    "item_filter": CustomFilter1,
                },
                self._random_temp_filename(): {
                    "format": "xml",
                    "item_filter": CustomFilter2,
                },
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "item_classes": [self.MyItem, self.MyItem2],
                    "item_filter": CustomFilter3,
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @deferred_f_from_coro_f
    async def test_export_dicts(self):
        # When dicts are used, only keys from the first row are used as
        # a header for CSV, and all fields are used for JSON Lines.
        items = [
            {"foo": "bar", "egg": "spam"},
            {"foo": "bar", "egg": "spam", "baz": "quux"},
        ]
        rows_csv = [{"egg": "spam", "foo": "bar"}, {"egg": "spam", "foo": "bar"}]
        rows_jl = items
        await self.assertExportedCsv(items, ["foo", "egg"], rows_csv)
        await self.assertExportedJsonLines(items, rows_jl)

    @deferred_f_from_coro_f
    async def test_export_tuple(self):
        items = [
            {"foo": "bar1", "egg": "spam1"},
            {"foo": "bar2", "egg": "spam2", "baz": "quux"},
        ]

        settings = {"FEED_EXPORT_FIELDS": ("foo", "baz")}
        rows = [{"foo": "bar1", "baz": ""}, {"foo": "bar2", "baz": "quux"}]
        await self.assertExported(items, ["foo", "baz"], rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_feed_export_fields(self):
        # FEED_EXPORT_FIELDS option allows to order export fields
        # and to select a subset of fields to export, both for Items and dicts.

        for item_cls in [self.MyItem, dict]:
            items = [
                item_cls({"foo": "bar1", "egg": "spam1"}),
                item_cls({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            ]

            # export all columns
            settings = {"FEED_EXPORT_FIELDS": "foo,baz,egg"}
            rows = [
                {"egg": "spam1", "foo": "bar1", "baz": ""},
                {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
            ]
            await self.assertExported(
                items, ["foo", "baz", "egg"], rows, settings=settings
            )

            # export a subset of columns
            settings = {"FEED_EXPORT_FIELDS": "egg,baz"}
            rows = [{"egg": "spam1", "baz": ""}, {"egg": "spam2", "baz": "quux2"}]
            await self.assertExported(items, ["egg", "baz"], rows, settings=settings)

    @deferred_f_from_coro_f
    async def test_export_encoding(self):
        items = [{"foo": "Test\xd6"}]

        formats = {
            "json": b'[{"foo": "Test\\u00d6"}]',
            "jsonlines": b'{"foo": "Test\\u00d6"}\n',
            "xml": (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<items><item><foo>Test\xd6</foo></item></items>"
            ).encode(),
            "csv": "foo\r\nTest\xd6\r\n".encode(),
        }

        for fmt, expected in formats.items():
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_EXPORT_INDENT": None,
            }
            data = await self.exported_data(items, settings)
            assert data[fmt] == expected

        formats = {
            "json": b'[{"foo": "Test\xd6"}]',
            "jsonlines": b'{"foo": "Test\xd6"}\n',
            "xml": (
                b'<?xml version="1.0" encoding="latin-1"?>\n'
                b"<items><item><foo>Test\xd6</foo></item></items>"
            ),
            "csv": b"foo\r\nTest\xd6\r\n",
        }

        for fmt, expected in formats.items():
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): {"format": fmt},
                },
                "FEED_EXPORT_INDENT": None,
                "FEED_EXPORT_ENCODING": "latin-1",
            }
            data = await self.exported_data(items, settings)
            assert data[fmt] == expected

    @deferred_f_from_coro_f
    async def test_export_multiple_configs(self):
        items = [{"foo": "FOO", "bar": "BAR"}]

        formats = {
            "json": b'[\n{"bar": "BAR"}\n]',
            "xml": (
                b'<?xml version="1.0" encoding="latin-1"?>\n'
                b"<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>"
            ),
            "csv": b"bar,foo\r\nBAR,FOO\r\n",
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "json",
                    "indent": 0,
                    "fields": ["bar"],
                    "encoding": "utf-8",
                },
                self._random_temp_filename(): {
                    "format": "xml",
                    "indent": 2,
                    "fields": ["foo"],
                    "encoding": "latin-1",
                },
                self._random_temp_filename(): {
                    "format": "csv",
                    "indent": None,
                    "fields": ["bar", "foo"],
                    "encoding": "utf-8",
                },
            },
        }

        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            assert data[fmt] == expected

    @deferred_f_from_coro_f
    async def test_export_indentation(self):
        items = [
            {"foo": ["bar"]},
            {"key": "value"},
        ]

        test_cases = [
            # JSON
            {
                "format": "json",
                "indent": None,
                "expected": b'[{"foo": ["bar"]},{"key": "value"}]',
            },
            {
                "format": "json",
                "indent": -1,
                "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                "format": "json",
                "indent": 0,
                "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            },
            {
                "format": "json",
                "indent": 2,
                "expected": b"""[
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
                "format": "json",
                "indent": 4,
                "expected": b"""[
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
                "format": "json",
                "indent": 5,
                "expected": b"""[
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
                "format": "xml",
                "indent": None,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items><item><foo><value>bar</value></foo></item><item><key>value</key></item></items>""",
            },
            {
                "format": "xml",
                "indent": -1,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 0,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            },
            {
                "format": "xml",
                "indent": 2,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
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
                "format": "xml",
                "indent": 4,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
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
                "format": "xml",
                "indent": 5,
                "expected": b"""<?xml version="1.0" encoding="utf-8"?>
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
                "FEEDS": {
                    self._random_temp_filename(): {
                        "format": row["format"],
                        "indent": row["indent"],
                    },
                },
            }
            data = await self.exported_data(items, settings)
            assert data[row["format"]] == row["expected"]

    @deferred_f_from_coro_f
    async def test_init_exporters_storages_with_crawler(self):
        settings = {
            "FEED_EXPORTERS": {"csv": FromCrawlerCsvItemExporter},
            "FEED_STORAGES": {"file": FromCrawlerFileFeedStorage},
            "FEEDS": {
                self._random_temp_filename(): {"format": "csv"},
            },
        }
        await self.exported_data(items=[], settings=settings)
        assert FromCrawlerCsvItemExporter.init_with_crawler
        assert FromCrawlerFileFeedStorage.init_with_crawler

    @deferred_f_from_coro_f
    async def test_str_uri(self):
        settings = {
            "FEED_STORE_EMPTY": True,
            "FEEDS": {str(self._random_temp_filename()): {"format": "csv"}},
        }
        data = await self.exported_no_data(settings)
        assert data["csv"] == b""

    @deferred_f_from_coro_f
    async def test_multiple_feeds_success_logs_blocking_feed_storage(self):
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": DummyBlockingFeedStorage},
        }
        items = [
            {"foo": "bar1", "baz": ""},
            {"foo": "bar2", "baz": "quux"},
        ]
        with LogCapture() as log:
            await self.exported_data(items, settings)

        print(log)
        for fmt in ["json", "xml", "csv"]:
            assert f"Stored {fmt} feed (2 items)" in str(log)

    @deferred_f_from_coro_f
    async def test_multiple_feeds_failing_logs_blocking_feed_storage(self):
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "json"},
                self._random_temp_filename(): {"format": "xml"},
                self._random_temp_filename(): {"format": "csv"},
            },
            "FEED_STORAGES": {"file": FailingBlockingFeedStorage},
        }
        items = [
            {"foo": "bar1", "baz": ""},
            {"foo": "bar2", "baz": "quux"},
        ]
        with LogCapture() as log:
            await self.exported_data(items, settings)

        print(log)
        for fmt in ["json", "xml", "csv"]:
            assert f"Error storing {fmt} feed (2 items)" in str(log)

    @deferred_f_from_coro_f
    async def test_extend_kwargs(self):
        items = [{"foo": "FOO", "bar": "BAR"}]

        expected_with_title_csv = b"foo,bar\r\nFOO,BAR\r\n"
        expected_without_title_csv = b"FOO,BAR\r\n"
        test_cases = [
            # with title
            {
                "options": {
                    "format": "csv",
                    "item_export_kwargs": {"include_headers_line": True},
                },
                "expected": expected_with_title_csv,
            },
            # without title
            {
                "options": {
                    "format": "csv",
                    "item_export_kwargs": {"include_headers_line": False},
                },
                "expected": expected_without_title_csv,
            },
        ]

        for row in test_cases:
            feed_options = row["options"]
            settings = {
                "FEEDS": {
                    self._random_temp_filename(): feed_options,
                },
                "FEED_EXPORT_INDENT": None,
            }

            data = await self.exported_data(items, settings)
            assert data[feed_options["format"]] == row["expected"]

    @deferred_f_from_coro_f
    async def test_storage_file_no_postprocessing(self):
        @implementer(IFeedStorage)
        class Storage:
            def __init__(self, uri, *, feed_options=None):
                pass

            def open(self, spider):
                Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
                return Storage.open_file

            def store(self, file):
                Storage.store_file = file
                file.close()

        settings = {
            "FEEDS": {self._random_temp_filename(): {"format": "jsonlines"}},
            "FEED_STORAGES": {"file": Storage},
        }
        await self.exported_no_data(settings)
        assert Storage.open_file is Storage.store_file

    @deferred_f_from_coro_f
    async def test_storage_file_postprocessing(self):
        @implementer(IFeedStorage)
        class Storage:
            def __init__(self, uri, *, feed_options=None):
                pass

            def open(self, spider):
                Storage.open_file = tempfile.NamedTemporaryFile(prefix="feed-")
                return Storage.open_file

            def store(self, file):
                Storage.store_file = file
                Storage.file_was_closed = file.closed
                file.close()

        settings = {
            "FEEDS": {
                self._random_temp_filename(): {
                    "format": "jsonlines",
                    "postprocessing": [
                        "scrapy.extensions.postprocessing.GzipPlugin",
                    ],
                },
            },
            "FEED_STORAGES": {"file": Storage},
        }
        await self.exported_no_data(settings)
        assert Storage.open_file is Storage.store_file
        assert not Storage.file_was_closed


class TestFeedPostProcessedExports(TestFeedExportBase):
    items = [{"foo": "bar"}]
    expected = b"foo\r\nbar\r\n"

    class MyPlugin1:
        def __init__(self, file, feed_options):
            self.file = file
            self.feed_options = feed_options
            self.char = self.feed_options.get("plugin1_char", b"")

        def write(self, data):
            written_count = self.file.write(data)
            written_count += self.file.write(self.char)
            return written_count

        def close(self):
            self.file.close()

    def _named_tempfile(self, name) -> str:
        return str(Path(self.temp_dir, name))

    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, bytes | None]:
        """Run spider with specified settings; return exported data with filename."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            printf_escape(path_to_url(file_path)): feed_options
            for file_path, feed_options in FEEDS.items()
        }

        content: dict[str, bytes | None] = {}
        try:
            spider_cls.start_urls = [self.mockserver.url("/")]
            crawler = get_crawler(spider_cls, settings)
            await maybe_deferred_to_future(crawler.crawl())

            for file_path in FEEDS:
                content[str(file_path)] = (
                    Path(file_path).read_bytes() if Path(file_path).exists() else None
                )

        finally:
            for file_path in FEEDS:
                if not Path(file_path).exists():
                    continue

                Path(file_path).unlink()

        return content

    def get_gzip_compressed(self, data, compresslevel=9, mtime=0, filename=""):
        data_stream = BytesIO()
        gzipf = gzip.GzipFile(
            fileobj=data_stream,
            filename=filename,
            mtime=mtime,
            compresslevel=compresslevel,
            mode="wb",
        )
        gzipf.write(data)
        gzipf.close()
        data_stream.seek(0)
        return data_stream.read()

    @deferred_f_from_coro_f
    async def test_gzip_plugin(self):
        filename = self._named_tempfile("gzip_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            gzip.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid gzip data.")

    @deferred_f_from_coro_f
    async def test_gzip_plugin_compresslevel(self):
        filename_to_compressed = {
            self._named_tempfile("compresslevel_0"): self.get_gzip_compressed(
                self.expected, compresslevel=0
            ),
            self._named_tempfile("compresslevel_9"): self.get_gzip_compressed(
                self.expected, compresslevel=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("compresslevel_0"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 0,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
                self._named_tempfile("compresslevel_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_compresslevel": 9,
                    "gzip_mtime": 0,
                    "gzip_filename": "",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_gzip_plugin_mtime(self):
        filename_to_compressed = {
            self._named_tempfile("mtime_123"): self.get_gzip_compressed(
                self.expected, mtime=123
            ),
            self._named_tempfile("mtime_123456789"): self.get_gzip_compressed(
                self.expected, mtime=123456789
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("mtime_123"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123,
                    "gzip_filename": "",
                },
                self._named_tempfile("mtime_123456789"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 123456789,
                    "gzip_filename": "",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_gzip_plugin_filename(self):
        filename_to_compressed = {
            self._named_tempfile("filename_FILE1"): self.get_gzip_compressed(
                self.expected, filename="FILE1"
            ),
            self._named_tempfile("filename_FILE2"): self.get_gzip_compressed(
                self.expected, filename="FILE2"
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("filename_FILE1"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE1",
                },
                self._named_tempfile("filename_FILE2"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.GzipPlugin"],
                    "gzip_mtime": 0,
                    "gzip_filename": "FILE2",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = gzip.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_lzma_plugin(self):
        filename = self._named_tempfile("lzma_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            lzma.decompress(data[filename])
        except lzma.LZMAError:
            pytest.fail("Received invalid lzma data.")

    @deferred_f_from_coro_f
    async def test_lzma_plugin_format(self):
        filename_to_compressed = {
            self._named_tempfile("format_FORMAT_XZ"): lzma.compress(
                self.expected, format=lzma.FORMAT_XZ
            ),
            self._named_tempfile("format_FORMAT_ALONE"): lzma.compress(
                self.expected, format=lzma.FORMAT_ALONE
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("format_FORMAT_XZ"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_XZ,
                },
                self._named_tempfile("format_FORMAT_ALONE"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_format": lzma.FORMAT_ALONE,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_lzma_plugin_check(self):
        filename_to_compressed = {
            self._named_tempfile("check_CHECK_NONE"): lzma.compress(
                self.expected, check=lzma.CHECK_NONE
            ),
            self._named_tempfile("check_CHECK_CRC256"): lzma.compress(
                self.expected, check=lzma.CHECK_SHA256
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("check_CHECK_NONE"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_NONE,
                },
                self._named_tempfile("check_CHECK_CRC256"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_check": lzma.CHECK_SHA256,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_lzma_plugin_preset(self):
        filename_to_compressed = {
            self._named_tempfile("preset_PRESET_0"): lzma.compress(
                self.expected, preset=0
            ),
            self._named_tempfile("preset_PRESET_9"): lzma.compress(
                self.expected, preset=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("preset_PRESET_0"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 0,
                },
                self._named_tempfile("preset_PRESET_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_preset": 9,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = lzma.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_lzma_plugin_filters(self):
        if "PyPy" in sys.version:
            # https://foss.heptapod.net/pypy/pypy/-/issues/3527
            pytest.skip("lzma filters doesn't work in PyPy")

        filters = [{"id": lzma.FILTER_LZMA2}]
        compressed = lzma.compress(self.expected, filters=filters)
        filename = self._named_tempfile("filters")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.LZMAPlugin"],
                    "lzma_filters": filters,
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert compressed == data[filename]
        result = lzma.decompress(data[filename])
        assert result == self.expected

    @deferred_f_from_coro_f
    async def test_bz2_plugin(self):
        filename = self._named_tempfile("bz2_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        try:
            bz2.decompress(data[filename])
        except OSError:
            pytest.fail("Received invalid bz2 data.")

    @deferred_f_from_coro_f
    async def test_bz2_plugin_compresslevel(self):
        filename_to_compressed = {
            self._named_tempfile("compresslevel_1"): bz2.compress(
                self.expected, compresslevel=1
            ),
            self._named_tempfile("compresslevel_9"): bz2.compress(
                self.expected, compresslevel=9
            ),
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("compresslevel_1"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 1,
                },
                self._named_tempfile("compresslevel_9"): {
                    "format": "csv",
                    "postprocessing": ["scrapy.extensions.postprocessing.Bz2Plugin"],
                    "bz2_compresslevel": 9,
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, compressed in filename_to_compressed.items():
            result = bz2.decompress(data[filename])
            assert compressed == data[filename]
            assert result == self.expected

    @deferred_f_from_coro_f
    async def test_custom_plugin(self):
        filename = self._named_tempfile("csv_file")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert data[filename] == self.expected

    @deferred_f_from_coro_f
    async def test_custom_plugin_with_parameter(self):
        expected = b"foo\r\n\nbar\r\n\n"
        filename = self._named_tempfile("newline")

        settings = {
            "FEEDS": {
                filename: {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await self.exported_data(self.items, settings)
        assert data[filename] == expected

    @deferred_f_from_coro_f
    async def test_custom_plugin_with_compression(self):
        expected = b"foo\r\n\nbar\r\n\n"

        filename_to_decompressor = {
            self._named_tempfile("bz2"): bz2.decompress,
            self._named_tempfile("lzma"): lzma.decompress,
            self._named_tempfile("gzip"): gzip.decompress,
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("bz2"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.Bz2Plugin",
                    ],
                    "plugin1_char": b"\n",
                },
                self._named_tempfile("lzma"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.LZMAPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
                self._named_tempfile("gzip"): {
                    "format": "csv",
                    "postprocessing": [
                        self.MyPlugin1,
                        "scrapy.extensions.postprocessing.GzipPlugin",
                    ],
                    "plugin1_char": b"\n",
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, decompressor in filename_to_decompressor.items():
            result = decompressor(data[filename])
            assert result == expected

    @deferred_f_from_coro_f
    async def test_exports_compatibility_with_postproc(self):
        filename_to_expected = {
            self._named_tempfile("csv"): b"foo\r\nbar\r\n",
            self._named_tempfile("json"): b'[\n{"foo": "bar"}\n]',
            self._named_tempfile("jsonlines"): b'{"foo": "bar"}\n',
            self._named_tempfile("xml"): b'<?xml version="1.0" encoding="utf-8"?>\n'
            b"<items>\n<item><foo>bar</foo></item>\n</items>",
        }

        settings = {
            "FEEDS": {
                self._named_tempfile("csv"): {
                    "format": "csv",
                    "postprocessing": [self.MyPlugin1],
                    # empty plugin to activate postprocessing.PostProcessingManager
                },
                self._named_tempfile("json"): {
                    "format": "json",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("jsonlines"): {
                    "format": "jsonlines",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("xml"): {
                    "format": "xml",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("marshal"): {
                    "format": "marshal",
                    "postprocessing": [self.MyPlugin1],
                },
                self._named_tempfile("pickle"): {
                    "format": "pickle",
                    "postprocessing": [self.MyPlugin1],
                },
            },
        }

        data = await self.exported_data(self.items, settings)

        for filename, result in data.items():
            if "pickle" in filename:
                expected, result = self.items[0], pickle.loads(result)
            elif "marshal" in filename:
                expected, result = self.items[0], marshal.loads(result)
            else:
                expected = filename_to_expected[filename]
            assert result == expected


class TestBatchDeliveries(TestFeedExportBase):
    _file_mark = "_%(batch_time)s_#%(batch_id)02d_"

    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, list[bytes]]:
        """Run spider with specified settings; return exported data."""

        FEEDS = settings.get("FEEDS") or {}
        settings["FEEDS"] = {
            build_url(file_path): feed for file_path, feed in FEEDS.items()
        }
        content: defaultdict[str, list[bytes]] = defaultdict(list)
        spider_cls.start_urls = [self.mockserver.url("/")]
        crawler = get_crawler(spider_cls, settings)
        await maybe_deferred_to_future(crawler.crawl())

        for path, feed in FEEDS.items():
            dir_name = Path(path).parent
            if not dir_name.exists():
                content[feed["format"]] = []
                continue
            for file in sorted(dir_name.iterdir()):
                content[feed["format"]].append(file.read_bytes())
        return content

    async def assertExportedJsonLines(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "jl" / self._file_mark: {
                        "format": "jl"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        for batch in data["jl"]:
            got_batch = [
                json.loads(to_unicode(batch_item)) for batch_item in batch.splitlines()
            ]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedCsv(self, items, header, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "csv" / self._file_mark: {
                        "format": "csv"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        data = await self.exported_data(items, settings)
        for batch in data["csv"]:
            got_batch = csv.DictReader(to_unicode(batch).splitlines())
            assert list(header) == got_batch.fieldnames
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert list(got_batch) == expected_batch

    async def assertExportedXml(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "xml" / self._file_mark: {
                        "format": "xml"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        for batch in data["xml"]:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall("item")]
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedMultiple(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "xml" / self._file_mark: {
                        "format": "xml"
                    },
                    self._random_temp_filename() / "json" / self._file_mark: {
                        "format": "json"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)
        # XML
        xml_rows = rows.copy()
        for batch in data["xml"]:
            root = lxml.etree.fromstring(batch)
            got_batch = [{e.tag: e.text for e in it} for it in root.findall("item")]
            expected_batch, xml_rows = xml_rows[:batch_size], xml_rows[batch_size:]
            assert got_batch == expected_batch
        # JSON
        json_rows = rows.copy()
        for batch in data["json"]:
            got_batch = json.loads(batch.decode("utf-8"))
            expected_batch, json_rows = json_rows[:batch_size], json_rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedPickle(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "pickle" / self._file_mark: {
                        "format": "pickle"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)

        for batch in data["pickle"]:
            got_batch = self._load_until_eof(batch, load_func=pickle.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    async def assertExportedMarshal(self, items, rows, settings=None):
        settings = settings or {}
        settings.update(
            {
                "FEEDS": {
                    self._random_temp_filename() / "marshal" / self._file_mark: {
                        "format": "marshal"
                    },
                },
            }
        )
        batch_size = Settings(settings).getint("FEED_EXPORT_BATCH_ITEM_COUNT")
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        data = await self.exported_data(items, settings)

        for batch in data["marshal"]:
            got_batch = self._load_until_eof(batch, load_func=marshal.load)
            expected_batch, rows = rows[:batch_size], rows[batch_size:]
            assert got_batch == expected_batch

    @deferred_f_from_coro_f
    async def test_export_items(self):
        """Test partial deliveries in all supported formats"""
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        rows = [
            {"egg": "spam1", "foo": "bar1", "baz": ""},
            {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
            {"foo": "bar3", "baz": "quux3", "egg": ""},
        ]
        settings = {"FEED_EXPORT_BATCH_ITEM_COUNT": 2}
        header = self.MyItem.fields.keys()
        await self.assertExported(items, header, rows, settings=settings)

    def test_wrong_path(self):
        """If path is without %(batch_time)s and %(batch_id) an exception must be raised"""
        settings = {
            "FEEDS": {
                self._random_temp_filename(): {"format": "xml"},
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            FeedExporter(crawler)

    @deferred_f_from_coro_f
    async def test_export_no_items_not_store_empty(self):
        for fmt in ("json", "jsonlines", "xml", "csv"):
            settings = {
                "FEEDS": {
                    self._random_temp_filename() / fmt / self._file_mark: {
                        "format": fmt
                    },
                },
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
                "FEED_STORE_EMPTY": False,
            }
            data = await self.exported_no_data(settings)
            data = dict(data)
            assert len(data[fmt]) == 0

    @deferred_f_from_coro_f
    async def test_export_no_items_store_empty(self):
        formats = (
            ("json", b"[]"),
            ("jsonlines", b""),
            ("xml", b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ("csv", b""),
        )

        for fmt, expctd in formats:
            settings = {
                "FEEDS": {
                    self._random_temp_filename() / fmt / self._file_mark: {
                        "format": fmt
                    },
                },
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_INDENT": None,
                "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
            }
            data = await self.exported_no_data(settings)
            data = dict(data)
            assert data[fmt][0] == expctd

    @deferred_f_from_coro_f
    async def test_export_multiple_configs(self):
        items = [
            {"foo": "FOO", "bar": "BAR"},
            {"foo": "FOO1", "bar": "BAR1"},
        ]

        formats = {
            "json": [
                b'[\n{"bar": "BAR"}\n]',
                b'[\n{"bar": "BAR1"}\n]',
            ],
            "xml": [
                (
                    b'<?xml version="1.0" encoding="latin-1"?>\n'
                    b"<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>"
                ),
                (
                    b'<?xml version="1.0" encoding="latin-1"?>\n'
                    b"<items>\n  <item>\n    <foo>FOO1</foo>\n  </item>\n</items>"
                ),
            ],
            "csv": [
                b"foo,bar\r\nFOO,BAR\r\n",
                b"foo,bar\r\nFOO1,BAR1\r\n",
            ],
        }

        settings = {
            "FEEDS": {
                self._random_temp_filename() / "json" / self._file_mark: {
                    "format": "json",
                    "indent": 0,
                    "fields": ["bar"],
                    "encoding": "utf-8",
                },
                self._random_temp_filename() / "xml" / self._file_mark: {
                    "format": "xml",
                    "indent": 2,
                    "fields": ["foo"],
                    "encoding": "latin-1",
                },
                self._random_temp_filename() / "csv" / self._file_mark: {
                    "format": "csv",
                    "indent": None,
                    "fields": ["foo", "bar"],
                    "encoding": "utf-8",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt]):
                assert got_batch == expected_batch

    @deferred_f_from_coro_f
    async def test_batch_item_count_feeds_setting(self):
        items = [{"foo": "FOO"}, {"foo": "FOO1"}]
        formats = {
            "json": [
                b'[{"foo": "FOO"}]',
                b'[{"foo": "FOO1"}]',
            ],
        }
        settings = {
            "FEEDS": {
                self._random_temp_filename() / "json" / self._file_mark: {
                    "format": "json",
                    "indent": None,
                    "encoding": "utf-8",
                    "batch_item_count": 1,
                },
            },
        }
        data = await self.exported_data(items, settings)
        for fmt, expected in formats.items():
            for expected_batch, got_batch in zip(expected, data[fmt]):
                assert got_batch == expected_batch

    @deferred_f_from_coro_f
    async def test_batch_path_differ(self):
        """
        Test that the name of all batch files differ from each other.
        So %(batch_id)d replaced with the current id.
        """
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]
        settings = {
            "FEEDS": {
                self._random_temp_filename() / "%(batch_id)d": {
                    "format": "json",
                },
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        data = await self.exported_data(items, settings)
        assert len(items) == len(data["json"])

    @inlineCallbacks
    def test_stats_batch_file_success(self):
        settings = {
            "FEEDS": {
                build_url(
                    str(self._random_temp_filename() / "json" / self._file_mark)
                ): {
                    "format": "json",
                }
            },
            "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
        }
        crawler = get_crawler(ItemSpider, settings)
        yield crawler.crawl(total=2, mockserver=self.mockserver)
        assert "feedexport/success_count/FileFeedStorage" in crawler.stats.get_stats()
        assert crawler.stats.get_value("feedexport/success_count/FileFeedStorage") == 12

    @pytest.mark.requires_boto3
    @inlineCallbacks
    def test_s3_export(self):
        bucket = "mybucket"
        items = [
            self.MyItem({"foo": "bar1", "egg": "spam1"}),
            self.MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
            self.MyItem({"foo": "bar3", "baz": "quux3"}),
        ]

        class CustomS3FeedStorage(S3FeedStorage):
            stubs = []

            def open(self, *args, **kwargs):
                from botocore import __version__ as botocore_version  # noqa: PLC0415
                from botocore.stub import ANY, Stubber  # noqa: PLC0415

                expected_params = {
                    "Body": ANY,
                    "Bucket": bucket,
                    "Key": ANY,
                }
                if Version(botocore_version) >= Version("1.36.0"):
                    expected_params["ChecksumAlgorithm"] = ANY

                stub = Stubber(self.s3_client)
                stub.activate()
                CustomS3FeedStorage.stubs.append(stub)
                stub.add_response(
                    "put_object",
                    expected_params=expected_params,
                    service_response={},
                )
                return super().open(*args, **kwargs)

        key = "export.csv"
        uri = f"s3://{bucket}/{key}/%(batch_id)d.json"
        batch_item_count = 1
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "FEED_EXPORT_BATCH_ITEM_COUNT": batch_item_count,
            "FEED_STORAGES": {
                "s3": CustomS3FeedStorage,
            },
            "FEEDS": {
                uri: {
                    "format": "json",
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        storage = S3FeedStorage.from_crawler(crawler, uri)
        verifyObject(IFeedStorage, storage)

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                yield from items

        TestSpider.start_urls = [self.mockserver.url("/")]
        crawler = get_crawler(TestSpider, settings)
        yield crawler.crawl()

        assert len(CustomS3FeedStorage.stubs) == len(items)
        for stub in CustomS3FeedStorage.stubs[:-1]:
            stub.assert_no_pending_responses()


# Test that the FeedExporer sends the feed_exporter_closed and feed_slot_closed signals
class TestFeedExporterSignals:
    items = [
        {"foo": "bar1", "egg": "spam1"},
        {"foo": "bar2", "egg": "spam2", "baz": "quux2"},
        {"foo": "bar3", "baz": "quux3"},
    ]

    with tempfile.NamedTemporaryFile(suffix="json") as tmp:
        settings = {
            "FEEDS": {
                f"file:///{tmp.name}": {
                    "format": "json",
                },
            },
        }

    def feed_exporter_closed_signal_handler(self):
        self.feed_exporter_closed_received = True

    def feed_slot_closed_signal_handler(self, slot):
        self.feed_slot_closed_received = True

    def feed_exporter_closed_signal_handler_deferred(self):
        d = defer.Deferred()
        d.addCallback(lambda _: setattr(self, "feed_exporter_closed_received", True))
        d.callback(None)
        return d

    def feed_slot_closed_signal_handler_deferred(self, slot):
        d = defer.Deferred()
        d.addCallback(lambda _: setattr(self, "feed_slot_closed_received", True))
        d.callback(None)
        return d

    def run_signaled_feed_exporter(
        self, feed_exporter_signal_handler, feed_slot_signal_handler
    ):
        crawler = get_crawler(settings_dict=self.settings)
        feed_exporter = FeedExporter.from_crawler(crawler)
        spider = scrapy.Spider("default")
        spider.crawler = crawler
        crawler.signals.connect(
            feed_exporter_signal_handler,
            signal=signals.feed_exporter_closed,
        )
        crawler.signals.connect(
            feed_slot_signal_handler, signal=signals.feed_slot_closed
        )
        feed_exporter.open_spider(spider)
        for item in self.items:
            feed_exporter.item_scraped(item, spider)
        defer.ensureDeferred(feed_exporter.close_spider(spider))

    def test_feed_exporter_signals_sent(self):
        self.feed_exporter_closed_received = False
        self.feed_slot_closed_received = False

        self.run_signaled_feed_exporter(
            self.feed_exporter_closed_signal_handler,
            self.feed_slot_closed_signal_handler,
        )
        assert self.feed_slot_closed_received
        assert self.feed_exporter_closed_received

    def test_feed_exporter_signals_sent_deferred(self):
        self.feed_exporter_closed_received = False
        self.feed_slot_closed_received = False

        self.run_signaled_feed_exporter(
            self.feed_exporter_closed_signal_handler_deferred,
            self.feed_slot_closed_signal_handler_deferred,
        )
        assert self.feed_slot_closed_received
        assert self.feed_exporter_closed_received


class TestFeedExportInit:
    def test_unsupported_storage(self):
        settings = {
            "FEEDS": {
                "unsupported://uri": {},
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            FeedExporter.from_crawler(crawler)

    def test_unsupported_format(self):
        settings = {
            "FEEDS": {
                "file://path": {
                    "format": "unsupported_format",
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        with pytest.raises(NotConfigured):
            FeedExporter.from_crawler(crawler)

    def test_absolute_pathlib_as_uri(self):
        with tempfile.NamedTemporaryFile(suffix="json") as tmp:
            settings = {
                "FEEDS": {
                    Path(tmp.name).resolve(): {
                        "format": "json",
                    },
                },
            }
            crawler = get_crawler(settings_dict=settings)
            exporter = FeedExporter.from_crawler(crawler)
            assert isinstance(exporter, FeedExporter)

    def test_relative_pathlib_as_uri(self):
        settings = {
            "FEEDS": {
                Path("./items.json"): {
                    "format": "json",
                },
            },
        }
        crawler = get_crawler(settings_dict=settings)
        exporter = FeedExporter.from_crawler(crawler)
        assert isinstance(exporter, FeedExporter)


class TestURIParams(ABC):
    spider_name = "uri_params_spider"
    deprecated_options = False

    @abstractmethod
    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        raise NotImplementedError

    def _crawler_feed_exporter(self, settings):
        if self.deprecated_options:
            with pytest.warns(
                ScrapyDeprecationWarning,
                match="The `FEED_URI` and `FEED_FORMAT` settings have been deprecated",
            ):
                crawler = get_crawler(settings_dict=settings)
        else:
            crawler = get_crawler(settings_dict=settings)
        feed_exporter = crawler.get_extension(FeedExporter)
        return crawler, feed_exporter

    def test_default(self):
        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_none(self):
        def uri_params(params, spider):
            pass

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_empty_dict(self):
        def uri_params(params, spider):
            return {}

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler

        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            with pytest.raises(KeyError):
                feed_exporter.open_spider(spider)

    def test_params_as_is(self):
        def uri_params(params, spider):
            return params

        settings = self.build_settings(
            uri="file:///tmp/%(name)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"

    def test_custom_param(self):
        def uri_params(params, spider):
            return {**params, "foo": self.spider_name}

        settings = self.build_settings(
            uri="file:///tmp/%(foo)s",
            uri_params=uri_params,
        )
        crawler, feed_exporter = self._crawler_feed_exporter(settings)
        spider = scrapy.Spider(self.spider_name)
        spider.crawler = crawler
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            feed_exporter.open_spider(spider)

        assert feed_exporter.slots[0].uri == f"file:///tmp/{self.spider_name}"


class TestURIParamsSetting(TestURIParams):
    deprecated_options = True

    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        extra_settings = {}
        if uri_params:
            extra_settings["FEED_URI_PARAMS"] = uri_params
        return {
            "FEED_URI": uri,
            **extra_settings,
        }


class TestURIParamsFeedOption(TestURIParams):
    deprecated_options = False

    def build_settings(self, uri="file:///tmp/foobar", uri_params=None):
        options = {
            "format": "jl",
        }
        if uri_params:
            options["uri_params"] = uri_params
        return {
            "FEEDS": {
                uri: options,
            },
        }
