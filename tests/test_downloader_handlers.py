"""Tests for DownloadHandlers and for specific non-HTTP download handlers."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from tempfile import mkdtemp, mkstemp
from unittest import mock

import pytest
from w3lib.url import path_to_file_uri

from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.handlers.datauri import DataURIDownloadHandler
from scrapy.core.downloader.handlers.file import FileDownloadHandler
from scrapy.core.downloader.handlers.s3 import S3DownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler


class DummyDH:
    lazy = False


class DummyLazyDH:
    # Default is lazy for backward compatibility
    pass


class OffDH:
    lazy = False

    def __init__(self, crawler):
        raise NotConfigured

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


class TestLoad:
    def test_enabled_handler(self):
        handlers = {"scheme": DummyDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" in dh._handlers
        assert "scheme" not in dh._notconfigured

    def test_not_configured_handler(self):
        handlers = {"scheme": OffDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" not in dh._handlers
        assert "scheme" in dh._notconfigured

    def test_disabled_handler(self):
        handlers = {"scheme": None}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" not in dh._schemes
        for scheme in handlers:  # force load handlers
            dh._get_handler(scheme)
        assert "scheme" not in dh._handlers
        assert "scheme" in dh._notconfigured

    def test_lazy_handlers(self):
        handlers = {"scheme": DummyLazyDH}
        crawler = get_crawler(settings_dict={"DOWNLOAD_HANDLERS": handlers})
        dh = DownloadHandlers(crawler)
        assert "scheme" in dh._schemes
        assert "scheme" not in dh._handlers
        for scheme in handlers:  # force load lazy handler
            dh._get_handler(scheme)
        assert "scheme" in dh._handlers
        assert "scheme" not in dh._notconfigured


class TestFile:
    def setup_method(self):
        # add a special char to check that they are handled correctly
        self.fd, self.tmpname = mkstemp(suffix="^")
        Path(self.tmpname).write_text("0123456789", encoding="utf-8")
        self.download_handler = build_from_crawler(FileDownloadHandler, get_crawler())

    def teardown_method(self):
        os.close(self.fd)
        Path(self.tmpname).unlink()

    async def download_request(self, request: Request) -> Response:
        return await maybe_deferred_to_future(
            self.download_handler.download_request(request, DefaultSpider())
        )

    @deferred_f_from_coro_f
    async def test_download(self):
        request = Request(path_to_file_uri(self.tmpname))
        assert request.url.upper().endswith("%5E")
        response = await self.download_request(request)
        assert response.url == request.url
        assert response.status == 200
        assert response.body == b"0123456789"
        assert response.protocol is None

    @deferred_f_from_coro_f
    async def test_non_existent(self):
        request = Request(path_to_file_uri(mkdtemp()))
        # the specific exception differs between platforms
        with pytest.raises(OSError):  # noqa: PT011
            await self.download_request(request)


class HttpDownloadHandlerMock:
    def __init__(self, *args, **kwargs):
        pass

    def download_request(self, request, spider):
        return request


@pytest.mark.requires_botocore
class TestS3Anon:
    def setup_method(self):
        crawler = get_crawler()
        self.s3reqh = build_from_crawler(
            S3DownloadHandler,
            crawler,
            httpdownloadhandler=HttpDownloadHandlerMock,
            # anon=True, # implicit
        )
        self.download_request = self.s3reqh.download_request
        self.spider = DefaultSpider()

    def test_anon_request(self):
        req = Request("s3://aws-publicdatasets/")
        httpreq = self.download_request(req, self.spider)
        assert hasattr(self.s3reqh, "anon")
        assert self.s3reqh.anon
        assert httpreq.url == "http://aws-publicdatasets.s3.amazonaws.com/"


@pytest.mark.requires_botocore
class TestS3:
    download_handler_cls: type = S3DownloadHandler

    # test use same example keys than amazon developer guide
    # http://s3.amazonaws.com/awsdocs/S3/20060301/s3-dg-20060301.pdf
    # and the tests described here are the examples from that manual

    AWS_ACCESS_KEY_ID = "0PN5J17HBGZHT7JJ3X82"
    AWS_SECRET_ACCESS_KEY = "uV3F3YluFJax1cknvbcGwgjvx4QpvB+leU8dUj2o"

    def setup_method(self):
        crawler = get_crawler()
        s3reqh = build_from_crawler(
            S3DownloadHandler,
            crawler,
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            httpdownloadhandler=HttpDownloadHandlerMock,
        )
        self.download_request = s3reqh.download_request
        self.spider = DefaultSpider()

    @contextlib.contextmanager
    def _mocked_date(self, date):
        try:
            import botocore.auth  # noqa: F401,PLC0415
        except ImportError:
            yield
        else:
            # We need to mock botocore.auth.formatdate, because otherwise
            # botocore overrides Date header with current date and time
            # and Authorization header is different each time
            with mock.patch("botocore.auth.formatdate") as mock_formatdate:
                mock_formatdate.return_value = date
                yield

    def test_extra_kw(self):
        crawler = get_crawler()
        with pytest.raises((TypeError, NotConfigured)):
            build_from_crawler(
                S3DownloadHandler,
                crawler,
                extra_kw=True,
            )

    def test_request_signing1(self):
        # gets an object from the johnsmith bucket.
        date = "Tue, 27 Mar 2007 19:36:42 +0000"
        req = Request("s3://johnsmith/photos/puppy.jpg", headers={"Date": date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:xXjDGYUmKxnwqr5KXNPGldn5LbA="
        )

    def test_request_signing2(self):
        # puts an object into the johnsmith bucket.
        date = "Tue, 27 Mar 2007 21:15:45 +0000"
        req = Request(
            "s3://johnsmith/photos/puppy.jpg",
            method="PUT",
            headers={
                "Content-Type": "image/jpeg",
                "Date": date,
                "Content-Length": "94328",
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:hcicpDDvL9SsO6AkvxqmIWkmOuQ="
        )

    def test_request_signing3(self):
        # lists the content of the johnsmith bucket.
        date = "Tue, 27 Mar 2007 19:42:41 +0000"
        req = Request(
            "s3://johnsmith/?prefix=photos&max-keys=50&marker=puppy",
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Date": date,
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:jsRt/rhG+Vtp88HrYL706QhE4w4="
        )

    def test_request_signing4(self):
        # fetches the access control policy sub-resource for the 'johnsmith' bucket.
        date = "Tue, 27 Mar 2007 19:44:46 +0000"
        req = Request("s3://johnsmith/?acl", method="GET", headers={"Date": date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:thdUi9VAkzhkniLj96JIrOPGi0g="
        )

    def test_request_signing6(self):
        # uploads an object to a CNAME style virtual hosted bucket with metadata.
        date = "Tue, 27 Mar 2007 21:06:08 +0000"
        req = Request(
            "s3://static.johnsmith.net:8080/db-backup.dat.gz",
            method="PUT",
            headers={
                "User-Agent": "curl/7.15.5",
                "Host": "static.johnsmith.net:8080",
                "Date": date,
                "x-amz-acl": "public-read",
                "content-type": "application/x-download",
                "Content-MD5": "4gJE4saaMU4BqNR0kLY+lw==",
                "X-Amz-Meta-ReviewedBy": "joe@johnsmith.net,jane@johnsmith.net",
                "X-Amz-Meta-FileChecksum": "0x02661779",
                "X-Amz-Meta-ChecksumAlgorithm": "crc32",
                "Content-Disposition": "attachment; filename=database.dat",
                "Content-Encoding": "gzip",
                "Content-Length": "5913339",
            },
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:C0FlOtU8Ylb9KDTpZqYkZPX91iI="
        )

    def test_request_signing7(self):
        # ensure that spaces are quoted properly before signing
        date = "Tue, 27 Mar 2007 19:42:41 +0000"
        req = Request(
            "s3://johnsmith/photos/my puppy.jpg?response-content-disposition=my puppy.jpg",
            method="GET",
            headers={"Date": date},
        )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        assert (
            httpreq.headers["Authorization"]
            == b"AWS 0PN5J17HBGZHT7JJ3X82:+CfvG8EZ3YccOrRVMXNaK2eKZmM="
        )


class TestDataURI:
    def setup_method(self):
        crawler = get_crawler()
        self.download_handler = build_from_crawler(DataURIDownloadHandler, crawler)

    async def download_request(self, request: Request) -> Response:
        return await maybe_deferred_to_future(
            self.download_handler.download_request(request, DefaultSpider())
        )

    @deferred_f_from_coro_f
    async def test_response_attrs(self):
        uri = "data:,A%20brief%20note"
        request = Request(uri)
        response = await self.download_request(request)
        assert response.url == uri
        assert not response.headers

    @deferred_f_from_coro_f
    async def test_default_mediatype_encoding(self):
        request = Request("data:,A%20brief%20note")
        response = await self.download_request(request)
        assert response.text == "A brief note"
        assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
        assert response.encoding == "US-ASCII"

    @deferred_f_from_coro_f
    async def test_default_mediatype(self):
        request = Request("data:;charset=iso-8859-7,%be%d3%be")
        response = await self.download_request(request)
        assert response.text == "\u038e\u03a3\u038e"
        assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
        assert response.encoding == "iso-8859-7"

    @deferred_f_from_coro_f
    async def test_text_charset(self):
        request = Request("data:text/plain;charset=iso-8859-7,%be%d3%be")
        response = await self.download_request(request)
        assert response.text == "\u038e\u03a3\u038e"
        assert response.body == b"\xbe\xd3\xbe"
        assert response.encoding == "iso-8859-7"

    @deferred_f_from_coro_f
    async def test_mediatype_parameters(self):
        request = Request(
            "data:text/plain;foo=%22foo;bar%5C%22%22;"
            "charset=utf-8;bar=%22foo;%5C%22 foo ;/,%22"
            ",%CE%8E%CE%A3%CE%8E"
        )
        response = await self.download_request(request)
        assert response.text == "\u038e\u03a3\u038e"
        assert type(response) is responsetypes.from_mimetype("text/plain")  # pylint: disable=unidiomatic-typecheck
        assert response.encoding == "utf-8"

    @deferred_f_from_coro_f
    async def test_base64(self):
        request = Request("data:text/plain;base64,SGVsbG8sIHdvcmxkLg%3D%3D")
        response = await self.download_request(request)
        assert response.text == "Hello, world."

    @deferred_f_from_coro_f
    async def test_protocol(self):
        request = Request("data:,")
        response = await self.download_request(request)
        assert response.protocol is None
