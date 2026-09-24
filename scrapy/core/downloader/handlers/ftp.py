"""
An asynchronous FTP file download handler for scrapy which somehow emulates an http response.

FTP connection parameters are passed using the request meta field:
- ftp_user (optional, falls back to FTP_USER)
- ftp_password (optional, falls back to FTP_PASSWORD)
- ftp_passive (optional, falls back to FTP_PASSIVE_MODE) sets FTP connection passive mode
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

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, ClassVar
from urllib.parse import unquote

from twisted.internet.protocol import ClientCreator, Protocol

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.exceptions import DownloadCancelledError, NotConfigured
from scrapy.http import Response
from scrapy.responsetypes import responsetypes
from scrapy.utils._download_handlers import (
    get_maxsize_msg,
    get_warnsize,
    get_warnsize_msg,
)
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from twisted.protocols.ftp import FTPClient

    from scrapy import Request
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class ReceivedDataProtocol(Protocol):
    def __init__(
        self,
        filename: bytes | None = None,
        *,
        request: Request | None = None,
        maxsize: int = 0,
        warnsize: int = 0,
    ):
        self.__filename: bytes | None = filename
        self.body: BinaryIO = (
            Path(filename.decode()).open("wb") if filename else BytesIO()
        )
        self.size: int = 0
        self._request: Request | None = request
        self._maxsize: int = maxsize
        self._warnsize: int = warnsize
        self._exceeded_maxsize: bool = False
        self._reached_warnsize: bool = False

    def dataReceived(self, data: bytes) -> None:
        self.body.write(data)
        self.size += len(data)
        if self._maxsize and self.size > self._maxsize:
            self._exceeded_maxsize = True
            self.body.truncate(0)
            assert self.transport
            self.transport.loseConnection()
        elif (
            self._warnsize and self.size > self._warnsize and not self._reached_warnsize
        ):
            self._reached_warnsize = True
            assert self._request is not None
            logger.warning(
                get_warnsize_msg(
                    self.size, self._warnsize, self._request, expected=False
                )
            )

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
        self._default_maxsize: int = crawler.settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize: int = crawler.settings.getint("DOWNLOAD_WARNSIZE")

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
        maxsize: int = request.meta.get("download_maxsize", self._default_maxsize)
        protocol = ReceivedDataProtocol(
            request.meta.get("ftp_local_filename"),
            request=request,
            maxsize=maxsize,
            warnsize=get_warnsize(request.meta, self._default_warnsize),
        )
        try:
            await maybe_deferred_to_future(client.retrieveFile(filepath, protocol))
        except CommandFailed as e:
            if not protocol._exceeded_maxsize:
                message = str(e)
                # Twisted only raises CommandFailed for a reply whose numeric
                # code it has parsed, so the message always carries that code.
                m = _CODE_RE.search(message)
                assert m
                httpcode = self.CODE_MAPPING.get(
                    m.group(), self.CODE_MAPPING["default"]
                )
                return Response(url=request.url, status=httpcode, body=message.encode())
        finally:
            protocol.close()
            assert client.transport
            client.transport.loseConnection()
        if protocol._exceeded_maxsize:
            warning_msg = get_maxsize_msg(
                protocol.size, maxsize, request, expected=False
            )
            logger.warning(warning_msg)
            raise DownloadCancelledError(warning_msg)
        headers = {"local filename": protocol.filename or b"", "size": protocol.size}
        body = protocol.filename or protocol.body.read()
        respcls = responsetypes.from_args(url=request.url, body=body)
        return respcls(url=request.url, status=200, body=body, headers=headers)
