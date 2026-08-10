from __future__ import annotations

import logging
import os
import string
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from ssl import SSLCertVerificationError
from typing import IO, Any
from unittest import mock
from urllib.parse import quote

import pytest
from w3lib.url import path_to_file_uri

import scrapy
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.extensions.feedexport import (
    FEED_MODES,
    BlockingFeedStorage,
    FileFeedStorage,
    FTPFeedStorage,
    GCSFeedStorage,
    S3FeedStorage,
    StdoutFeedStorage,
)
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.mockserver.ftp import MockFTPServer
from tests.utils.cloud import mock_google_cloud_storage
from tests.utils.decorators import coroutine_test


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
        self._store(path, {"mode": "overwrite"})
        self._assert_stores(
            FileFeedStorage(str(path), feed_options={"mode": "overwrite"}), path
        )

    def test_create(self, tmp_path):
        path = tmp_path / "file.txt"
        self._assert_stores(
            FileFeedStorage(str(path), feed_options={"mode": "create"}), path
        )

    def test_create_existing(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_bytes(b"content")
        storage = FileFeedStorage(str(path), feed_options={"mode": "create"})
        with pytest.raises(FileExistsError):
            storage.open(scrapy.Spider("default"))
        assert path.read_bytes() == b"content"

    @pytest.mark.parametrize(
        ("feed_options", "expected_write_mode"),
        [
            (None, "ab"),
            ({}, "ab"),
            ({"mode": "create"}, "xb"),
            ({"overwrite": True}, "wb"),
            ({"overwrite": False}, "ab"),
        ],
    )
    def test_mode(self, tmp_path, feed_options, expected_write_mode):
        storage = FileFeedStorage(str(tmp_path / "file.txt"), feed_options=feed_options)
        assert storage.write_mode == expected_write_mode

    def test_invalid_mode(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid feed mode: 'x'"):
            FileFeedStorage(str(tmp_path / "file.txt"), feed_options={"mode": "x"})

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


def get_test_spider(settings: dict[str, Any] | None = None) -> scrapy.Spider:
    class TestSpider(scrapy.Spider):
        name = "test_spider"

    crawler = get_crawler(settings_dict=settings)
    return TestSpider.from_crawler(crawler)


class TestFTPFeedStorage:
    async def _store(
        self,
        uri: str,
        content: bytes,
        feed_options: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        crawler = get_crawler(settings_dict=settings or {})
        storage = build_from_crawler(
            FTPFeedStorage,
            crawler,
            uri,
            feed_options=feed_options,
        )
        spider = get_test_spider()
        file = storage.open(spider)
        file.write(content)
        await maybe_deferred_to_future(storage.store(file))

    def _assert_stored(self, path: Path, content: bytes, unlink: bool = True) -> None:
        assert path.exists()
        try:
            assert path.read_bytes() == content
        finally:
            if unlink:
                path.unlink()

    @coroutine_test
    async def test_append(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"mode": "append"}
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
    async def test_create(self):
        with MockFTPServer() as ftp_server:
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"mode": "create"}
            await self._store(url, b"foo", feed_options=feed_options)
            self._assert_stored(ftp_server.path / filename, b"foo", unlink=False)
            with pytest.raises(FileExistsError):
                await self._store(url, b"bar", feed_options=feed_options)
            self._assert_stored(ftp_server.path / filename, b"foo")

    @coroutine_test
    async def test_append_active_mode(self):
        with MockFTPServer() as ftp_server:
            settings = {"FEED_STORAGE_FTP_ACTIVE": True}
            filename = "file"
            url = ftp_server.url(filename)
            feed_options = {"mode": "append"}
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

    def test_overwrite_deprecated(self):
        storage = FTPFeedStorage.from_crawler(get_crawler(), "ftp://localhost/file")
        with pytest.warns(
            ScrapyDeprecationWarning, match="FTPFeedStorage.overwrite is deprecated"
        ):
            assert storage.overwrite is True

    @coroutine_test
    async def test_tls(self, monkeypatch):
        monkeypatch.setenv(
            "SSL_CERT_FILE", str(Path(__file__).parent / "keys" / "localhost.crt")
        )
        with MockFTPServer(tls=True) as ftp_server:
            filename = "file"
            await self._store(ftp_server.url(filename), b"foo")
            self._assert_stored(ftp_server.path / filename, b"foo")

    @coroutine_test
    async def test_tls_untrusted_certificate(self):
        with (
            MockFTPServer(tls=True) as ftp_server,
            pytest.raises(SSLCertVerificationError),
        ):
            await self._store(ftp_server.url("file"), b"foo")

    def test_uri_auth_quote(self):
        # RFC3986: 3.2.1. User Information
        pw_quoted = quote(string.punctuation, safe="")
        st = FTPFeedStorage(f"ftp://foo:{pw_quoted}@example.com/some_path")
        assert st.password == string.punctuation

    def test_uri_without_hostname(self):
        with pytest.raises(
            ValueError, match="Got a storage URI without a hostname: ftp:///some_path"
        ):
            FTPFeedStorage("ftp:///some_path")


class MyBlockingFeedStorage(BlockingFeedStorage):
    def _store_in_thread(self, file: IO[bytes]) -> None:
        return


class TestBlockingFeedStorage:
    def test_default_temp_dir(self):
        b = MyBlockingFeedStorage()

        storage_file = b.open(get_test_spider())
        storage_dir = Path(storage_file.name).parent
        assert str(storage_dir) == tempfile.gettempdir()

    def test_temp_file(self, tmp_path):
        b = MyBlockingFeedStorage()

        spider = get_test_spider({"FEED_TEMPDIR": str(tmp_path)})
        storage_file = b.open(spider)
        storage_dir = Path(storage_file.name).parent
        assert storage_dir == tmp_path

    def test_invalid_folder(self, tmp_path):
        b = MyBlockingFeedStorage()

        invalid_path = tmp_path / "invalid_path"
        spider = get_test_spider({"FEED_TEMPDIR": str(invalid_path)})

        with pytest.raises(OSError, match="Not a Directory:"):
            b.open(spider=spider)


def test_s3_without_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)
    monkeypatch.setitem(sys.modules, "boto3.session", None)
    with pytest.raises(NotConfigured, match="missing boto3 library"):
        S3FeedStorage("s3://mybucket/export.csv", "access_key", "secret_key")


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
        storage = build_from_crawler(
            S3FeedStorage,
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
        storage = build_from_crawler(S3FeedStorage, crawler, f"s3://{bucket}/{key}")

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
        assert storage.s3_client._client_config.region_name == region_name  # type: ignore[attr-defined]

    def test_from_crawler_without_acl(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(
            S3FeedStorage,
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
        storage = build_from_crawler(
            S3FeedStorage,
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
        storage = build_from_crawler(
            S3FeedStorage,
            crawler,
            "s3://mybucket/export.csv",
        )
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.s3_client._client_config.region_name == "us-east-1"  # type: ignore[attr-defined]

    def test_from_crawler_with_acl(self):
        settings = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "FEED_STORAGE_S3_ACL": "custom-acl",
        }
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(
            S3FeedStorage,
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
        storage = build_from_crawler(S3FeedStorage, crawler, "s3://mybucket/export.csv")
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
        storage = build_from_crawler(S3FeedStorage, crawler, "s3://mybucket/export.csv")
        assert storage.access_key == "access_key"
        assert storage.secret_key == "secret_key"
        assert storage.region_name == region_name
        assert storage.s3_client._client_config.region_name == region_name  # type: ignore[attr-defined]

    def test_init_without_max_pool_connections(self) -> None:
        storage = S3FeedStorage("s3://mybucket/export.csv", "access_key", "secret_key")
        assert storage.max_pool_connections is None
        config: Any = storage.s3_client.meta.config
        assert config.max_pool_connections == 10

    def test_init_with_max_pool_connections(self) -> None:
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            max_pool_connections=30,
        )
        assert storage.max_pool_connections == 30
        config: Any = storage.s3_client.meta.config
        assert config.max_pool_connections == 30

    @pytest.mark.parametrize(
        ("settings", "expected"),
        [
            ({}, 10),
            ({"REACTOR_THREADPOOL_MAXSIZE": 20}, 20),
            ({"AWS_MAX_POOL_CONNECTIONS": 30}, 30),
            ({"AWS_MAX_POOL_CONNECTIONS": 30, "REACTOR_THREADPOOL_MAXSIZE": 20}, 30),
        ],
    )
    def test_from_crawler_max_pool_connections(
        self, settings: dict[str, Any], expected: int
    ) -> None:
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(S3FeedStorage, crawler, "s3://mybucket/export.csv")
        assert storage.max_pool_connections == expected
        config: Any = storage.s3_client.meta.config
        assert config.max_pool_connections == expected

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

    def test_mode_append(self) -> None:
        with pytest.raises(
            ValueError, match="S3FeedStorage does not support the 'append' feed mode"
        ):
            S3FeedStorage(
                "s3://mybucket/export.csv",
                "access_key",
                "secret_key",
                "custom-acl",
                feed_options={"mode": "append"},
            )

    @coroutine_test
    async def test_store_create(self) -> None:
        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            "custom-acl",
            feed_options={"mode": "create"},
        )
        storage.s3_client = mock.MagicMock()
        file = BytesIO(b"test file")
        stored = storage.store(file)
        assert stored is not None
        await maybe_deferred_to_future(stored)
        storage.s3_client.upload_fileobj.assert_not_called()
        assert storage.s3_client.put_object.call_args == mock.call(
            Bucket="mybucket",
            Key="export.csv",
            Body=file,
            IfNoneMatch="*",
            ACL="custom-acl",
        )

    @coroutine_test
    async def test_store_create_existing(self) -> None:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            feed_options={"mode": "create"},
        )
        storage.s3_client = mock.MagicMock()
        storage.s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "PreconditionFailed"}}, "PutObject"
        )
        stored = storage.store(BytesIO(b"test file"))
        assert stored is not None
        with pytest.raises(FileExistsError):
            await maybe_deferred_to_future(stored)

    @coroutine_test
    async def test_store_create_error(self) -> None:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        storage = S3FeedStorage(
            "s3://mybucket/export.csv",
            "access_key",
            "secret_key",
            feed_options={"mode": "create"},
        )
        storage.s3_client = mock.MagicMock()
        storage.s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "PutObject"
        )
        stored = storage.store(BytesIO(b"test file"))
        assert stored is not None
        with pytest.raises(ClientError):
            await maybe_deferred_to_future(stored)


class TestGCSFeedStorage:
    def test_parse_settings(self):
        pytest.importorskip("google.cloud.storage")

        settings = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": "publicRead"}
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(
            GCSFeedStorage, crawler, "gs://mybucket/export.csv"
        )
        assert storage.project_id == "123"
        assert storage.acl == "publicRead"
        assert storage.bucket_name == "mybucket"
        assert storage.blob_name == "export.csv"

    def test_parse_empty_acl(self):
        pytest.importorskip("google.cloud.storage")

        settings: dict[str, Any] = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": ""}
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(
            GCSFeedStorage, crawler, "gs://mybucket/export.csv"
        )
        assert storage.acl is None

        settings = {"GCS_PROJECT_ID": "123", "FEED_STORAGE_GCS_ACL": None}
        crawler = get_crawler(settings_dict=settings)
        storage = build_from_crawler(
            GCSFeedStorage, crawler, "gs://mybucket/export.csv"
        )
        assert storage.acl is None

    @coroutine_test
    async def test_store(self):
        pytest.importorskip("google.cloud.storage")

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
            client_mock.bucket.assert_called_once_with("mybucket")
            bucket_mock.blob.assert_called_once_with("export.csv")
            blob_mock.upload_from_file.assert_called_once_with(f, predefined_acl=acl)
            f.close.assert_called_once_with()

    @coroutine_test
    async def test_store_closes_file_on_upload_error(self):
        pytest.importorskip("google.cloud.storage")

        uri = "gs://mybucket/export.csv"
        project_id = "myproject-123"
        acl = "publicRead"
        (client_mock, bucket_mock, blob_mock) = mock_google_cloud_storage()
        blob_mock.upload_from_file.side_effect = OSError("Upload failed")
        with mock.patch("google.cloud.storage.Client") as m:
            m.return_value = client_mock

            f = mock.Mock()
            storage = GCSFeedStorage(uri, project_id, acl)
            with pytest.raises(OSError, match="Upload failed"):
                await maybe_deferred_to_future(storage.store(f))

            f.seek.assert_called_once_with(0)
            m.assert_called_once_with(project=project_id)
            client_mock.bucket.assert_called_once_with("mybucket")
            bucket_mock.blob.assert_called_once_with("export.csv")
            blob_mock.upload_from_file.assert_called_once_with(f, predefined_acl=acl)
            f.close.assert_called_once_with()

    def test_mode_append(self):
        with pytest.raises(
            ValueError, match="GCSFeedStorage does not support the 'append' feed mode"
        ):
            GCSFeedStorage(
                "gs://mybucket/export.csv",
                "myproject-123",
                "custom-acl",
                feed_options={"mode": "append"},
            )

    @coroutine_test
    async def test_store_create(self):
        pytest.importorskip("google.cloud.storage")

        (client_mock, _, blob_mock) = mock_google_cloud_storage()
        with mock.patch("google.cloud.storage.Client") as m:
            m.return_value = client_mock
            f = mock.Mock()
            storage = GCSFeedStorage(
                "gs://mybucket/export.csv",
                "myproject-123",
                "publicRead",
                feed_options={"mode": "create"},
            )
            await maybe_deferred_to_future(storage.store(f))
            blob_mock.upload_from_file.assert_called_once_with(
                f, predefined_acl="publicRead", if_generation_match=0
            )
            f.close.assert_called_once_with()

    @coroutine_test
    async def test_store_create_existing(self):
        pytest.importorskip("google.cloud.storage")
        from google.api_core.exceptions import PreconditionFailed  # noqa: PLC0415

        (client_mock, _, blob_mock) = mock_google_cloud_storage()
        blob_mock.upload_from_file.side_effect = PreconditionFailed("exists")
        with mock.patch("google.cloud.storage.Client") as m:
            m.return_value = client_mock
            f = mock.Mock()
            storage = GCSFeedStorage(
                "gs://mybucket/export.csv",
                "myproject-123",
                None,
                feed_options={"mode": "create"},
            )
            with pytest.raises(FileExistsError):
                await maybe_deferred_to_future(storage.store(f))
            f.close.assert_called_once_with()


class TestStdoutFeedStorage:
    def test_store(self):
        out = BytesIO()
        storage = StdoutFeedStorage("stdout:", _stdout=out)
        file = storage.open(scrapy.Spider("default"))
        file.write(b"content")
        storage.store(file)
        assert out.getvalue() == b"content"

    @pytest.mark.parametrize("mode", sorted(FEED_MODES))
    def test_mode_ignored(self, mode: str, caplog: pytest.LogCaptureFixture):
        out = BytesIO()
        with caplog.at_level(logging.DEBUG):
            storage = StdoutFeedStorage(
                "stdout:", _stdout=out, feed_options={"mode": mode}
            )
            file = storage.open(scrapy.Spider("default"))
            file.write(b"content")
            storage.store(file)
        assert out.getvalue() == b"content"
        assert not caplog.text
