"""
An asynchronous FTP file download handler for scrapy which somehow emulates an http response.

FTP connection parameters are passed using the request meta field:
- ftp_user (required)
- ftp_password (required)
- ftp_passive (by default, enabled) sets FTP connection passive mode
- ftp_local_filename
        - If not given, file data will come in the response.body, as a normal scrapy Response,
        which will imply that the entire file will be on memory.
        - if given, file data will be saved in a local file with the given name
        This helps when downloading very big files to avoid memory issues. In addition, for
        convenience the local file name will also be given in the response body.

The status of the built html response will be, by default
- 200 in case of success
- 404 in case specified file was not found in the server (ftp code 550)

or raise corresponding ftp exception otherwise

The matching from server ftp command return codes to html response codes is defined in the
CODE_MAPPING attribute of the handler class. The key 'default' is used for any code
that is not explicitly present among the map keys. You may need to overwrite this
mapping if want a different behaviour than default.

In case of status 200 request, response.headers will come with two keys:
    'Local Filename' - with the value of the local filename if given
    'Size' - with size of the downloaded data
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from urllib.parse import unquote

from twisted.internet.protocol import ClientCreator, Protocol
from twisted.protocols.ftp import CommandFailed, FTPClient

from scrapy.http import Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred
    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


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


class FTPDownloadHandler:
    lazy = False

    CODE_MAPPING: dict[str, int] = {
        "550": 404,
        "default": 503,
    }

    def __init__(self, settings: BaseSettings):
        self.default_user = settings["FTP_USER"]
        self.default_password = settings["FTP_PASSWORD"]
        self.passive_mode = settings["FTP_PASSIVE_MODE"]

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        from twisted.internet import reactor

        parsed_url = urlparse_cached(request)
        user = request.meta.get("ftp_user", self.default_user)
        password = request.meta.get("ftp_password", self.default_password)
        passive_mode = (
            1 if bool(request.meta.get("ftp_passive", self.passive_mode)) else 0
        )
        creator = ClientCreator(
            reactor, FTPClient, user, password, passive=passive_mode
        )
        dfd: Deferred[FTPClient] = creator.connectTCP(
            parsed_url.hostname, parsed_url.port or 21
        )
        return dfd.addCallback(self.gotClient, request, unquote(parsed_url.path))

    def gotClient(
        self, client: FTPClient, request: Request, filepath: str
    ) -> Deferred[Response]:
        self.client = client
        protocol = ReceivedDataProtocol(request.meta.get("ftp_local_filename"))
        d = client.retrieveFile(filepath, protocol)
        d.addCallback(self._build_response, request, protocol)
        d.addErrback(self._failed, request)
        return d

    def _build_response(
        self, result: Any, request: Request, protocol: ReceivedDataProtocol
    ) -> Response:
        self.result = result
        protocol.close()
        headers = {"local filename": protocol.filename or b"", "size": protocol.size}
        body = protocol.filename or protocol.body.read()
        respcls = responsetypes.from_args(url=request.url, body=body)
        # hints for Headers-related types may need to be fixed to not use AnyStr
        return respcls(url=request.url, status=200, body=body, headers=headers)  # type: ignore[arg-type]

    def _failed(self, result: Failure, request: Request) -> Response:
        message = result.getErrorMessage()
        if result.type == CommandFailed:
            m = _CODE_RE.search(message)
            if m:
                ftpcode = m.group()
                httpcode = self.CODE_MAPPING.get(ftpcode, self.CODE_MAPPING["default"])
                return Response(
                    url=request.url, status=httpcode, body=to_bytes(message)
                )
        assert result.type
        raise result.type(result.value)
