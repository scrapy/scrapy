from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, ClassVar
from urllib.parse import unquote

from twisted.internet.protocol import ClientCreator, Protocol

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from twisted.protocols.ftp import FTPClient

    from scrapy import Request
    from scrapy.crawler import Crawler


class ReceivedDataProtocol(Protocol):
    def __init__(self, filename: bytes | None = None):
        self.__filename: bytes | None = filename
        self.body: BinaryIO = (
            Path(filename.decode()).open("wb") if filename else BytesIO()
        )
        self.size: int = 0

    def dataReceived(self, data: bytes) -> None:
        self.body.write(data)
        self.size += len(data)

    @property
    def filename(self) -> bytes | None:
        return self.__filename

    def close(self) -> None:
        if self.filename:
            self.body.close()
        else:
            self.body.seek(0)


_CODE_RE = re.compile(r"\d+")


class FTPDownloadHandler(BaseDownloadHandler):
    CODE_MAPPING: ClassVar[dict[str, int]] = {
        "550": 404,
        "default": 503,
    }

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("TWISTED_REACTOR_ENABLED"):
            raise NotConfigured(f"{type(self).__name__} requires a Twisted reactor.")
        super().__init__(crawler)
        self.default_user = crawler.settings["FTP_USER"]
        self.default_password = crawler.settings["FTP_PASSWORD"]
        self.passive_mode = crawler.settings["FTP_PASSIVE_MODE"]

    async def download_request(self, request: Request) -> Response:
        from twisted.internet import reactor
        from twisted.protocols.ftp import CommandFailed, FTPClient

        parsed_url = urlparse_cached(request)
        user = request.meta.get("ftp_user", self.default_user)
        password = request.meta.get("ftp_password", self.default_password)
        passive_mode = (
            1 if bool(request.meta.get("ftp_passive", self.passive_mode)) else 0
        )
        creator = ClientCreator(
            reactor, FTPClient, user, password, passive=passive_mode
        )
        client: FTPClient = await maybe_deferred_to_future(
            creator.connectTCP(parsed_url.hostname, parsed_url.port or 21)
        )
        filepath = unquote(parsed_url.path)
        protocol = ReceivedDataProtocol(request.meta.get("ftp_local_filename"))
        try:
            await maybe_deferred_to_future(client.retrieveFile(filepath, protocol))
        except CommandFailed as e:
            message = str(e)
            if m := _CODE_RE.search(message):
                ftpcode = m.group()
                httpcode = self.CODE_MAPPING.get(ftpcode, self.CODE_MAPPING["default"])
                return Response(url=request.url, status=httpcode, body=message.encode())
            raise
        finally:
            protocol.close()
            assert client.transport
            client.transport.loseConnection()
        headers = {"local filename": protocol.filename or b"", "size": protocol.size}
        body = protocol.filename or protocol.body.read()
        respcls = responsetypes.from_args(url=request.url, body=body)
        # hints for Headers-related types may need to be fixed to not use AnyStr
        return respcls(url=request.url, status=200, body=body, headers=headers)  # type: ignore[arg-type]
