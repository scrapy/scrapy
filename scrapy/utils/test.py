"""
This module contains some assorted functions used in tests
"""

from __future__ import annotations

import asyncio
import os
import warnings
from importlib import import_module
from pathlib import Path
from posixpath import split
from typing import TYPE_CHECKING, Any, TypeVar
from unittest import TestCase, mock

from twisted.trial.unittest import SkipTest

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.boto import is_botocore_available

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from twisted.internet.defer import Deferred
    from twisted.web.client import Response as TxResponse


_T = TypeVar("_T")


def assert_gcs_environ() -> None:
    if "GCS_PROJECT_ID" not in os.environ:
        raise SkipTest("GCS_PROJECT_ID not found")


def skip_if_no_boto() -> None:
    if not is_botocore_available():
        raise SkipTest("missing botocore library")


def get_gcs_content_and_delete(
    bucket: Any, path: str
) -> tuple[bytes, list[dict[str, str]], Any]:
    from google.cloud import storage

    client = storage.Client(project=os.environ.get("GCS_PROJECT_ID"))
    bucket = client.get_bucket(bucket)
    blob = bucket.get_blob(path)
    content = blob.download_as_string()
    acl = list(blob.acl)  # loads acl before it will be deleted
    bucket.delete_blob(path)
    return content, acl, blob


def get_ftp_content_and_delete(
    path: str,
    host: str,
    port: int,
    username: str,
    password: str,
    use_active_mode: bool = False,
) -> bytes:
    from ftplib import FTP

    ftp = FTP()
    ftp.connect(host, port)
    ftp.login(username, password)
    if use_active_mode:
        ftp.set_pasv(False)
    ftp_data: list[bytes] = []

    def buffer_data(data: bytes) -> None:
        ftp_data.append(data)

    ftp.retrbinary(f"RETR {path}", buffer_data)
    dirname, filename = split(path)
    ftp.cwd(dirname)
    ftp.delete(filename)
    return b"".join(ftp_data)


class TestSpider(Spider):
    name = "test"


def get_crawler(
    spidercls: type[Spider] | None = None,
    settings_dict: dict[str, Any] | None = None,
    prevent_warnings: bool = True,
) -> Crawler:
    """Return an unconfigured Crawler object. If settings_dict is given, it
    will be used to populate the crawler settings with a project level
    priority.
    """
    from scrapy.crawler import CrawlerRunner

    # Set by default settings that prevent deprecation warnings.
    settings: dict[str, Any] = {}
    settings.update(settings_dict or {})
    runner = CrawlerRunner(settings)
    crawler = runner.create_crawler(spidercls or TestSpider)
    crawler._apply_settings()
    return crawler


def get_pythonpath() -> str:
    """Return a PYTHONPATH suitable to use in processes so that they find this
    installation of Scrapy"""
    scrapy_path = import_module("scrapy").__path__[0]
    return str(Path(scrapy_path).parent) + os.pathsep + os.environ.get("PYTHONPATH", "")


def get_testenv() -> dict[str, str]:
    """Return a OS environment dict suitable to fork processes that need to import
    this installation of Scrapy, instead of a system installed one.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = get_pythonpath()
    return env


def assert_samelines(
    testcase: TestCase, text1: str, text2: str, msg: str | None = None
) -> None:
    """Asserts text1 and text2 have the same lines, ignoring differences in
    line endings between platforms
    """
    warnings.warn(
        "'assert_samelines' is deprecated and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
    )
    testcase.assertEqual(text1.splitlines(), text2.splitlines(), msg)


def get_from_asyncio_queue(value: _T) -> Awaitable[_T]:
    q: asyncio.Queue[_T] = asyncio.Queue()
    getter = q.get()
    q.put_nowait(value)
    return getter


def mock_google_cloud_storage() -> tuple[Any, Any, Any]:
    """Creates autospec mocks for google-cloud-storage Client, Bucket and Blob
    classes and set their proper return values.
    """
    from google.cloud.storage import Blob, Bucket, Client

    client_mock = mock.create_autospec(Client)

    bucket_mock = mock.create_autospec(Bucket)
    client_mock.get_bucket.return_value = bucket_mock

    blob_mock = mock.create_autospec(Blob)
    bucket_mock.blob.return_value = blob_mock

    return (client_mock, bucket_mock, blob_mock)


def get_web_client_agent_req(url: str) -> Deferred[TxResponse]:
    from twisted.internet import reactor
    from twisted.web.client import Agent  # imports twisted.internet.reactor

    agent = Agent(reactor)
    return agent.request(b"GET", url.encode("utf-8"))
