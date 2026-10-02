from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any

import pytest
from w3lib.http import basic_auth_header

from scrapy.core.downloader.handlers._aioftp import _HAS_SOCKS, AioftpDownloadHandler
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
    ResponseDataLossError,
)
from scrapy.http import HtmlResponse, Request, TextResponse
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.mockserver.ftp import MockFTPServer
from tests.utils.decorators import coroutine_test

try:
    from siosocks.io.asyncio import socks_server_handler
except ImportError:
    socks_server_handler = None

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator
    from pathlib import Path

    from scrapy.http import Response

pytestmark = pytest.mark.only_asyncio

FILES = {
    "file.txt": b"I have the power!",
    "file with spaces.txt": b"Moooooooooo power!",
    "html-file-without-extension": b"<!DOCTYPE html>\n<title>.</title>",
}


def _write_files(server: MockFTPServer) -> MockFTPServer:
    for name, content in FILES.items():
        (server.path / name).write_bytes(content)
    return server


@pytest.fixture(scope="module")
def ftp_server() -> Generator[MockFTPServer]:
    with MockFTPServer() as server:
        yield _write_files(server)


@pytest.fixture(scope="module")
def ftps_server() -> Generator[MockFTPServer]:
    with MockFTPServer(tls=True) as server:
        yield _write_files(server)


async def _download(
    request: Request, settings: dict[str, Any] | None = None
) -> Response:
    crawler = get_crawler(settings_dict=settings)
    dh = build_from_crawler(AioftpDownloadHandler, crawler)
    try:
        return await dh.download_request(request)
    finally:
        await dh.close()


@pytest.mark.parametrize(
    ("path", "response_class"),
    [
        ("file.txt", TextResponse),
        ("file with spaces.txt", TextResponse),
        ("html-file-without-extension", HtmlResponse),
    ],
)
@coroutine_test
async def test_download(
    ftp_server: MockFTPServer, path: str, response_class: type[Response]
) -> None:
    response = await _download(Request(ftp_server.url(path)))
    assert type(response) is response_class
    assert response.status == 200
    assert response.body == FILES[path]
    assert response.headers == {
        b"Local Filename": [b""],
        b"Size": [str(len(FILES[path])).encode()],
    }
    assert response.protocol == "FTP"
    assert response.ip_address == ip_address("127.0.0.1")
    assert response.certificate is None


@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="Explicit FTPS requires Python 3.11+"
)
@coroutine_test
async def test_download_ftps(
    ftps_server: MockFTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    settings = {"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
    with caplog.at_level(logging.DEBUG):
        response = await _download(Request(ftps_server.url("file.txt")), settings)
    assert response.body == FILES["file.txt"]
    assert isinstance(response.certificate, bytes)
    assert "SSL connection to 127.0.0.1 using protocol" in caplog.text


@coroutine_test
async def test_tls_verbose_logging_without_tls(ftp_server: MockFTPServer) -> None:
    settings = {"DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING": True}
    response = await _download(Request(ftp_server.url("file.txt")), settings)
    assert response.body == FILES["file.txt"]


@coroutine_test
async def test_nonexistent(ftp_server: MockFTPServer) -> None:
    response = await _download(Request(ftp_server.url("nonexistent.txt")))
    assert response.status == 404
    assert response.body == b""


@coroutine_test
async def test_invalid_credentials(ftp_server: MockFTPServer) -> None:
    request = Request(ftp_server.url("file.txt"), meta={"ftp_user": "invalid"})
    with pytest.raises(DownloadFailedError):
        await _download(request)


@pytest.mark.parametrize("local", [False, True])
@coroutine_test
async def test_maxsize(ftp_server: MockFTPServer, tmp_path: Path, local: bool) -> None:
    meta: dict[str, Any] = {"download_maxsize": 10}
    if local:
        meta["ftp_local_filename"] = str(tmp_path / "file.txt").encode()
    request = Request(ftp_server.url("file.txt"), meta=meta)
    with pytest.raises(DownloadCancelledError):
        await _download(request)


@coroutine_test
async def test_maxsize_disabled(ftp_server: MockFTPServer) -> None:
    request = Request(ftp_server.url("file.txt"), meta={"download_maxsize": 0})
    response = await _download(request, {"DOWNLOAD_MAXSIZE": 10})
    assert response.body == FILES["file.txt"]


@coroutine_test
async def test_warnsize(
    ftp_server: MockFTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    request = Request(ftp_server.url("file.txt"), meta={"download_warnsize": 10})
    response = await _download(request)
    assert response.body == FILES["file.txt"]
    assert "which is larger than download warn size (10)" in caplog.text


@coroutine_test
async def test_active_mode_meta(
    ftp_server: MockFTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    request = Request(ftp_server.url("file.txt"), meta={"ftp_passive": False})
    response = await _download(request)
    assert response.body == FILES["file.txt"]
    assert "does not support active mode" in caplog.text


@coroutine_test
async def test_active_mode() -> None:
    crawler = get_crawler(settings_dict={"FTP_PASSIVE_MODE": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(AioftpDownloadHandler, crawler)


@coroutine_test
async def test_connection_refused() -> None:
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    with pytest.raises(DownloadConnectionRefusedError):
        await _download(Request(f"ftp://127.0.0.1:{port}/file.txt"))


@coroutine_test
async def test_cannot_resolve_host() -> None:
    with pytest.raises(CannotResolveHostError):
        await _download(Request("ftp://nonexistent.invalid/file.txt"))


@coroutine_test
async def test_timeout() -> None:
    async def never_greet(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await reader.read()
        writer.close()

    async with _serve(never_greet) as url:
        request = Request(url, meta={"download_timeout": 0.1})
        with pytest.raises(DownloadTimeoutError):
            await _download(request)


@coroutine_test
async def test_connection_lost() -> None:
    async with _serve(lambda r, w: w.close()) as url:
        with pytest.raises(DownloadFailedError):
            await _download(Request(url))


def _fake_ftp(
    retr_reply: bytes, data: bytes = b""
) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], Any]:
    """Return a minimal FTP server connection handler that sends *data*, if
    any, and then answers RETR with *retr_reply*."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        data_writer: asyncio.Future[asyncio.StreamWriter] = (
            asyncio.get_running_loop().create_future()
        )

        def on_data_connection(_: asyncio.StreamReader, w: asyncio.StreamWriter):
            data_writer.set_result(w)

        writer.write(b"220 Ready\r\n")
        while line := await reader.readline():
            command = line.split()[0].upper()
            if command == b"USER":
                writer.write(b"230 Logged in\r\n")
            elif command == b"TYPE":
                writer.write(b"200 OK\r\n")
            elif command == b"EPSV":
                data_server = await asyncio.start_server(
                    on_data_connection, "127.0.0.1", 0
                )
                port = data_server.sockets[0].getsockname()[1]
                writer.write(f"229 Entering passive mode (|||{port}|)\r\n".encode())
            elif command == b"RETR":
                w = await data_writer
                if data:
                    writer.write(b"150 Sending\r\n")
                    w.write(data)
                w.close()
                data_server.close()
                writer.write(retr_reply)
            await writer.drain()
        writer.close()

    return handle


@asynccontextmanager
async def _serve(
    handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Any],
) -> AsyncGenerator[str]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"ftp://127.0.0.1:{port}/file.txt"
    finally:
        server.close()


@coroutine_test
async def test_retr_failure() -> None:
    async with _serve(_fake_ftp(b"450 Busy\r\n")) as url:
        response = await _download(Request(url))
    assert response.status == 503


_TRUNCATED = _fake_ftp(b"426 Transfer aborted\r\n", data=b"partial")


@coroutine_test
async def test_dataloss() -> None:
    async with _serve(_TRUNCATED) as url:
        with pytest.raises(ResponseDataLossError):
            await _download(Request(url))


@coroutine_test
async def test_dataloss_allowed() -> None:
    async with _serve(_TRUNCATED) as url:
        response = await _download(
            Request(url, meta={"download_fail_on_dataloss": False})
        )
    assert response.body == b"partial"
    assert response.flags == ["dataloss"]


@coroutine_test
async def test_local_filename(ftp_server: MockFTPServer, tmp_path: Path) -> None:
    local_filename = str(tmp_path / "file.txt").encode()
    request = Request(
        ftp_server.url("file.txt"), meta={"ftp_local_filename": local_filename}
    )
    response = await _download(request)
    assert response.body == local_filename
    assert response.headers == {
        b"Local Filename": [local_filename],
        b"Size": [b"17"],
    }
    assert (tmp_path / "file.txt").read_bytes() == FILES["file.txt"]


@asynccontextmanager
async def _socks_proxy(**kwargs: Any) -> AsyncGenerator[str]:
    server = await asyncio.start_server(
        lambda r, w: socks_server_handler(r, w, **kwargs), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.close()


requires_socks = pytest.mark.skipif(
    not _HAS_SOCKS or socks_server_handler is None,
    reason="Requires python-socks and siosocks",
)


@requires_socks
@pytest.mark.parametrize("scheme", ["socks4", "socks5"])
@coroutine_test
async def test_socks_proxy(ftp_server: MockFTPServer, scheme: str) -> None:
    async with _socks_proxy() as proxy:
        request = Request(
            ftp_server.url("file.txt"), meta={"proxy": f"{scheme}://{proxy}"}
        )
        response = await _download(request)
    assert response.body == FILES["file.txt"]


@requires_socks
@coroutine_test
async def test_socks_proxy_credentials(ftp_server: MockFTPServer) -> None:
    async with _socks_proxy(
        allowed_versions={5}, username="user", password="pass"
    ) as proxy:
        request = Request(
            ftp_server.url("file.txt"),
            meta={"proxy": f"socks5://{proxy}"},
            headers={"Proxy-Authorization": basic_auth_header("user", "pass")},
        )
        response = await _download(request)
    assert response.body == FILES["file.txt"]


@requires_socks
@coroutine_test
async def test_socks_proxy_wrong_credentials(ftp_server: MockFTPServer) -> None:
    async with _socks_proxy(
        allowed_versions={5}, username="user", password="pass"
    ) as proxy:
        request = Request(
            ftp_server.url("file.txt"),
            meta={"proxy": f"socks5://{proxy}"},
            headers={"Proxy-Authorization": basic_auth_header("user", "wrong")},
        )
        with pytest.raises(DownloadFailedError):
            await _download(request)


@requires_socks
@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="Explicit FTPS requires Python 3.11+"
)
@coroutine_test
async def test_socks_proxy_ftps(ftps_server: MockFTPServer) -> None:
    async with _socks_proxy() as proxy:
        request = Request(
            ftps_server.url("file.txt"), meta={"proxy": f"socks5://{proxy}"}
        )
        response = await _download(request)
    assert response.body == FILES["file.txt"]
    assert isinstance(response.certificate, bytes)


@coroutine_test
async def test_http_proxy(ftp_server: MockFTPServer) -> None:
    request = Request(ftp_server.url("file.txt"), meta={"proxy": "http://127.0.0.1:1"})
    with pytest.raises(NotImplementedError):
        await _download(request)
