from __future__ import annotations

import os
import string
import tempfile
from io import BytesIO
from pathlib import Path
from typing import IO, Any
from unittest import mock
from urllib.parse import quote

import pytest
from testfixtures import LogCapture
from w3lib.url import path_to_file_uri
from zope.interface.verify import verifyObject

import scrapy
from scrapy.extensions.feedexport import (
    BlockingFeedStorage,
    FileFeedStorage,
    FTPFeedStorage,
    GCSFeedStorage,
    IFeedStorage,
    S3FeedStorage,
    StdoutFeedStorage,
)
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.mockserver.ftp import MockFTPServer
from tests.utils.decorators import coroutine_test


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

    @coroutine_test
    async def test_append(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"overwrite": False}
            await self._store(url, b"foo", feed_options=feed_options)
            await self._store(url, b"bar", feed_options=feed_options)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @coroutine_test
    async def test_overwrite(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            await self._store(url, b"foo")
            await self._store(url, b"bar")
            self._assert_stored(ftp_server.path / filename, b"bar")

    @coroutine_test
    async def test_append_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {"FEED_STORAGE_FTP_ACTIVE": True}
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"overwrite": False}
            await self._store(url, b"foo", feed_options=feed_options, settings=settings)
            await self._store(url, b"bar", feed_options=feed_options, settings=settings)
            self._assert_stored(ftp_server.path / filename, b"foobar")

    @coroutine_test
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

    @coroutine_test
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

    @coroutine_test
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

    @coroutine_test
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

    @coroutine_test
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
