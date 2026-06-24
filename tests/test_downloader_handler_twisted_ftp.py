from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import mkstemp
from typing import TYPE_CHECKING, Any

import pytest
from pytest_twisted import async_yield_fixture
from twisted.cred import checkers, credentials, portal
from twisted.internet import defer

from scrapy import Spider
from scrapy.core.downloader.handlers.ftp import FTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse, Request, Response
from scrapy.http.response.text import TextResponse
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator

    from twisted.protocols.ftp import FTPFactory


pytestmark = pytest.mark.requires_reactor  # FTPDownloadHandler requires a reactor


class _FakeTransport:
    def __init__(self) -> None:
        self.closed = False

    def loseConnection(self) -> None:
        self.closed = True


class _FakeFTPClient:
    def __init__(self, retrieve_result: Callable[[Any], defer.Deferred[Any]]):
        self.retrieve_result = retrieve_result
        self.transport = _FakeTransport()
        self.protocol: Any = None
        self.filepath: str | None = None
        self.host: str | None = None
        self.port: int | None = None

    def retrieveFile(self, filepath: str, protocol: Any) -> defer.Deferred[Any]:
        self.filepath = filepath
        self.protocol = protocol
        return self.retrieve_result(protocol)


def _patch_client_creator(
    monkeypatch: pytest.MonkeyPatch, client: _FakeFTPClient
) -> None:
    class FakeClientCreator:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def connectTCP(self, host: str | None, port: int) -> defer.Deferred[Any]:
            client.host = host
            client.port = port
            return defer.succeed(client)

    monkeypatch.setattr(
        "scrapy.core.downloader.handlers.ftp.ClientCreator", FakeClientCreator
    )


class TestFTPBase(ABC):
    username = "scrapy"
    password = "passwd"
    req_meta: dict[str, Any] = {"ftp_user": username, "ftp_password": password}

    test_files = (
        ("file.txt", b"I have the power!"),
        ("file with spaces.txt", b"Moooooooooo power!"),
        ("html-file-without-extension", b"<!DOCTYPE html>\n<title>.</title>"),
    )

    @abstractmethod
    def _create_files(self, root: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def _get_factory(self, tmp_path: Path) -> FTPFactory:
        raise NotImplementedError

    @async_yield_fixture  # type: ignore[untyped-decorator]
    async def server_url(self, tmp_path: Path) -> AsyncGenerator[str]:
        from twisted.internet import reactor

        self._create_files(tmp_path)
        factory = self._get_factory(tmp_path)
        port = reactor.listenTCP(0, factory, interface="127.0.0.1")
        portno = port.getHost().port

        yield f"ftp://127.0.0.1:{portno}/"

        await port.stopListening()

    @staticmethod
    @pytest.fixture
    def dh() -> Generator[FTPDownloadHandler]:
        crawler = get_crawler()
        dh = build_from_crawler(FTPDownloadHandler, crawler)

        yield dh

        # if the test was skipped, there will be no client attribute
        if hasattr(dh, "client"):
            assert dh.client.transport
            dh.client.transport.loseConnection()

    @deferred_f_from_coro_f
    async def test_ftp_download_success(
        self, server_url: str, dh: FTPDownloadHandler
    ) -> None:
        request = Request(url=server_url + "file.txt", meta=self.req_meta)
        r = await dh.download_request(request)
        assert r.status == 200
        assert r.body == b"I have the power!"
        assert r.headers == {b"Local Filename": [b""], b"Size": [b"17"]}
        assert r.protocol is None

    @deferred_f_from_coro_f
    async def test_ftp_download_path_with_spaces(
        self, server_url: str, dh: FTPDownloadHandler
    ) -> None:
        request = Request(
            url=server_url + "file with spaces.txt",
            meta=self.req_meta,
        )
        r = await dh.download_request(request)
        assert r.status == 200
        assert r.body == b"Moooooooooo power!"
        assert r.headers == {b"Local Filename": [b""], b"Size": [b"18"]}

    @deferred_f_from_coro_f
    async def test_ftp_download_nonexistent(
        self, server_url: str, dh: FTPDownloadHandler
    ) -> None:
        request = Request(url=server_url + "nonexistent.txt", meta=self.req_meta)
        r = await dh.download_request(request)
        assert r.status == 404
        assert r.body == b"['550 nonexistent.txt: No such file or directory.']"

    @deferred_f_from_coro_f
    async def test_ftp_local_filename(
        self, server_url: str, dh: FTPDownloadHandler
    ) -> None:
        f, local_fname = mkstemp()
        fname_bytes = to_bytes(local_fname)
        local_path = Path(local_fname)
        os.close(f)
        meta = {"ftp_local_filename": fname_bytes}
        meta.update(self.req_meta)
        request = Request(url=server_url + "file.txt", meta=meta)
        r = await dh.download_request(request)
        assert r.body == fname_bytes
        assert r.headers == {b"Local Filename": [fname_bytes], b"Size": [b"17"]}
        assert local_path.exists()
        assert local_path.read_bytes() == b"I have the power!"
        local_path.unlink()

    @pytest.mark.parametrize(
        ("filename", "response_class"),
        [
            ("file.txt", TextResponse),
            ("html-file-without-extension", HtmlResponse),
        ],
    )
    @deferred_f_from_coro_f
    async def test_response_class(
        self,
        filename: str,
        response_class: type[Response],
        server_url: str,
        dh: FTPDownloadHandler,
    ) -> None:
        meta = {}
        meta.update(self.req_meta)
        request = Request(url=server_url + filename, meta=meta)
        r = await dh.download_request(request)
        assert type(r) is response_class  # pylint: disable=unidiomatic-typecheck

    @deferred_f_from_coro_f
    async def test_ftp_download_closes_client_connection(
        self, monkeypatch: pytest.MonkeyPatch, dh: FTPDownloadHandler
    ) -> None:
        def retrieve_file(protocol: Any) -> defer.Deferred[None]:
            protocol.dataReceived(b"I have the power!")
            return defer.succeed(None)

        client = _FakeFTPClient(retrieve_file)
        _patch_client_creator(monkeypatch, client)
        request = Request(url="ftp://example.com/file.txt", meta=self.req_meta)

        r = await dh.download_request(request)

        assert r.status == 200
        assert r.body == b"I have the power!"
        assert client.filepath == "/file.txt"
        assert client.transport.closed is True

    @deferred_f_from_coro_f
    async def test_ftp_download_closes_resources_after_command_failed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dh: FTPDownloadHandler,
    ) -> None:
        from twisted.protocols.ftp import CommandFailed

        def retrieve_file(protocol: Any) -> defer.Deferred[None]:
            protocol.dataReceived(b"partial")
            return defer.fail(CommandFailed(["550 missing.txt"]))

        local_path = tmp_path / "partial.txt"
        client = _FakeFTPClient(retrieve_file)
        _patch_client_creator(monkeypatch, client)
        meta = {"ftp_local_filename": to_bytes(str(local_path))}
        meta.update(self.req_meta)
        request = Request(url="ftp://example.com/missing.txt", meta=meta)

        r = await dh.download_request(request)

        assert r.status == 404
        assert r.body == b"['550 missing.txt']"
        assert client.protocol.body.closed is True
        assert client.transport.closed is True


class TestFTP(TestFTPBase):
    def _create_files(self, root: Path) -> None:
        userdir = root / self.username
        userdir.mkdir()
        for filename, content in self.test_files:
            (userdir / filename).write_bytes(content)

    def _get_factory(self, root):
        from twisted.protocols.ftp import FTPFactory, FTPRealm

        realm = FTPRealm(anonymousRoot=str(root), userHome=str(root))
        p = portal.Portal(realm)
        users_checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        users_checker.addUser(self.username, self.password)
        p.registerChecker(users_checker, credentials.IUsernamePassword)
        return FTPFactory(portal=p)

    @deferred_f_from_coro_f
    async def test_invalid_credentials(
        self, server_url: str, dh: FTPDownloadHandler, reactor_pytest: str
    ) -> None:
        if reactor_pytest == "asyncio" and sys.platform == "win32":
            pytest.skip(
                "This test produces DirtyReactorAggregateError on Windows with asyncio"
            )

        from twisted.protocols.ftp import ConnectionLost

        meta = dict(self.req_meta)
        meta.update({"ftp_password": "invalid"})
        request = Request(url=server_url + "file.txt", meta=meta)
        with pytest.raises(ConnectionLost):
            await dh.download_request(request)


class TestAnonymousFTP(TestFTPBase):
    username = "anonymous"
    req_meta = {}

    def _create_files(self, root: Path) -> None:
        for filename, content in self.test_files:
            (root / filename).write_bytes(content)

    def _get_factory(self, tmp_path):
        from twisted.protocols.ftp import FTPFactory, FTPRealm

        realm = FTPRealm(anonymousRoot=str(tmp_path))
        p = portal.Portal(realm)
        p.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)
        return FTPFactory(portal=p, userAnonymous=self.username)


def test_not_configured_without_reactor() -> None:
    crawler = Crawler(Spider, {"TWISTED_REACTOR_ENABLED": False})
    with pytest.raises(NotConfigured):
        FTPDownloadHandler.from_crawler(crawler)
