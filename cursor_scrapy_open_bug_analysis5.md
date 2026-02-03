# Scrapy open bug analysis
_Exported on 2/3/2026 at 12:19:08 GMT+5:30 from Cursor (2.2.44)_

---

**User**

@scrapy this is the main project 
https://github.com/scrapy/scrapy/issues?q=state%3Aopen%20label%3Abug do the deep analysis of this one and give me outcome then we will  move forward with the excution

---

**Cursor**

```plaintext
```676:689:scrapy/scrapy/pipelines/files.py
    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum
```

```plaintext

- `ImagesPipeline.image_downloaded()` does the same for each image and thumbnail.

```

```python
    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        assert checksum is not None
        return checksum
```

```plaintext

- `_process_request()` awaits `media_to_download()` but `_check_media_to_download()` returns `media_downloaded()` directly without awaiting it, so any Deferred chain is lost.

```

```python
            file_info: FileInfo | None = await ensure_awaitable(
                self.media_to_download(request, info, item=item)
            )
            ...
            response = await self.crawler.engine.download_async(request)
            return self.media_downloaded(response, request, info, item=item)
```

```plaintext

- Result: items can complete and results can be cached before storage writes finish; failures in `persist_file()` are not propagated and surface as unhandled Deferred errors.

## Outcome / fix direction

- Await `media_downloaded()` via `ensure_awaitable()` in `_check_media_to_download()` to make async media handling first-class while keeping sync compatibility.

- Make `FilesPipeline.media_downloaded()` (or `file_downloaded()`) return an awaitable that only resolves after `persist_file()` completes; use `maybeDeferred()` + `maybe_deferred_to_future()` to stay reactor-agnostic.

- In `ImagesPipeline.image_downloaded()`, await all `persist_file()` operations together (using `DeferredList` or `asyncio.gather` with `ensure_awaitable`) to preserve parallelism for thumbnails.

- Add tests with a custom store whose `persist_file()` returns a Deferred that resolves later; assert `process_item()` doesn’t finish early and failures show in results.

- Optionally update docs to note `media_downloaded()` can be coroutine or Deferred like other media pipeline hooks.

Net effect: media results won’t be marked “downloaded” until storage writes succeed, and errors will propagate properly. I can implement this fix and tests next if desired.
```

Assumption: you want issue #7182 “Await `persist_file()` in media pipelines” from the open bug list. [link](https://github.com/scrapy/scrapy/issues?q=state%3Aopen%20label%3Abug)

## Deep Analysis
The media pipeline is async, but the persistence step is currently outside the awaited execution path. `persist_file()` is explicitly allowed to be asynchronous, and the current implementation can return before writes finish.

- `persist_file()` is defined to return `Deferred | None`, so async stores are supported by design.

```84:95:scrapy/scrapy/pipelines/files.py
class FilesStoreProtocol(Protocol):
    def __init__(self, basedir: str): ...

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any] | None: ...
```

- `FilesPipeline.file_downloaded()` calls `persist_file()` and immediately returns the checksum.

```676:689:scrapy/scrapy/pipelines/files.py
    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum
```

- `ImagesPipeline.image_downloaded()` does the same for each image/thumb.

```128:149:scrapy/scrapy/pipelines/images.py
    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        assert checksum is not None
        return checksum
```

- `_process_request()` awaits `media_to_download()`, but `_check_media_to_download()` returns `media_downloaded()` directly without awaiting it, so any Deferred chain is lost.

```184:213:scrapy/scrapy/pipelines/media.py
            file_info: FileInfo | None = await ensure_awaitable(
                self.media_to_download(request, info, item=item)
            )
            ...
            response = await self.crawler.engine.download_async(request)
            return self.media_downloaded(response, request, info, item=item)
```

- Result: items can complete and results can be cached before storage writes finish; failures inside `persist_file()` are not propagated and can surface as unhandled Deferred errors.

## Outcome / Fix Direction
- Await `media_downloaded()` via `ensure_awaitable()` in `_check_media_to_download()` to make async media handling first-class while keeping sync compatibility.
- Make `FilesPipeline.media_downloaded()` (or `file_downloaded()`) return an awaitable that only resolves after `persist_file()` completes; use `maybeDeferred()` + `maybe_deferred_to_future()` to stay reactor-agnostic.
- In `ImagesPipeline.image_downloaded()`, await all `persist_file()` operations together (e.g., `DeferredList` or `asyncio.gather`) to preserve parallelism for thumbnails.
- Add tests with a custom store whose `persist_file()` returns a Deferred that resolves later; assert `process_item()` doesn’t finish early and failures show in results.
- Optional docs update: list `media_downloaded()` as coroutine-capable alongside other media pipeline hooks.

Net effect: media results won’t be marked “downloaded” until the storage write succeeds, and errors become visible to the pipeline. Ready to implement when you want to proceed.

```python
class FilesStoreProtocol(Protocol):
    def __init__(self, basedir: str): ...

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any] | None: ...
```

```python
    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum
```

```python
    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        assert checksum is not None
        return checksum
```

```python
            file_info: FileInfo | None = await ensure_awaitable(
                self.media_to_download(request, info, item=item)
            )
            ...
            response = await self.crawler.engine.download_async(request)
            return self.media_downloaded(response, request, info, item=item)
```

---

**User**

https://github.com/scrapy/scrapy/issues?q=state%3Aopen%20label%3Abug now find the most difficult issue that have 3,4 file changes

---

**Cursor**

Picked issue: **#7182 “Await `persist_file()` in media pipelines”** from the open bug list [https://github.com/scrapy/scrapy/issues?q=state%3Aopen%20label%3Abug](https://github.com/scrapy/scrapy/issues?q=state%3Aopen%20label%3Abug).

Why this is the most difficult while still staying within ~3–4 file changes:
- It touches the core async contract between Twisted `Deferred` and asyncio `Future`, so correctness depends on cross-reactor behavior, not just a local bug fix.
- It changes when media results are considered “done”, which affects cache, item completion timing, and error propagation.
- The fix needs to preserve concurrency (especially in image thumbnails) while adding awaited persistence.

Likely 3–4 file changes to fix it:
- `scrapy/pipelines/media.py` to await `media_downloaded()` (so coroutine-based implementations are respected).
- `scrapy/pipelines/files.py` to await or convert the `persist_file()` result inside `file_downloaded()`.
- `scrapy/pipelines/images.py` to await all `persist_file()` calls for original + thumbs.
- One test file (e.g., `scrapy/tests/test_pipeline_files.py` or `scrapy/tests/test_pipeline_media.py`) to validate awaiting and error propagation.

Outcome: This issue is the hardest in the list that can still be solved cleanly within a small, 3–4 file patch, and it directly addresses async correctness in a central pipeline path.

---

**User**

now your task is to resolve that bug with 3,4 file changes 

---

**Cursor**

```python
from __future__ import annotations

import asyncio
import functools
import logging
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, cast

from twisted import version as twisted_version
from twisted.internet.defer import Deferred, DeferredList
from twisted.python.failure import Failure
from twisted.python.versions import Version

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.request import NO_CALLBACK, Request
from scrapy.utils.asyncio import call_later, is_asyncio_available
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _DEFER_DELAY,
    _defer_sleep_async,
    deferred_from_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import Settings
    from scrapy.utils.request import RequestFingerprinterProtocol


class FileInfo(TypedDict):
    url: str
    path: str
    checksum: str | None
    status: str


FileInfoOrError: TypeAlias = (
    tuple[Literal[True], FileInfo] | tuple[Literal[False], Failure]
)

logger = logging.getLogger(__name__)


class MediaPipeline(ABC):
    LOG_FAILED_RESULTS: bool = True

    class SpiderInfo:
        def __init__(self, spider: Spider):
            self.spider: Spider = spider
            self.downloading: set[bytes] = set()
            self.downloaded: dict[bytes, FileInfo | Failure] = {}
            self.waiting: defaultdict[bytes, list[Deferred[FileInfo]]] = defaultdict(
                list
            )

    def __init__(
        self,
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of MediaPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        self.crawler: Crawler = crawler
        assert crawler.request_fingerprinter
        self._fingerprinter: RequestFingerprinterProtocol = (
            crawler.request_fingerprinter
        )

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe, base_class_name="MediaPipeline", settings=settings
        )
        self.allow_redirects: bool = settings.getbool(
            resolve("MEDIA_ALLOW_REDIRECTS"), False
        )
        self._handle_statuses(self.allow_redirects)

    def _handle_statuses(self, allow_redirects: bool) -> None:
        self.handle_httpstatus_list = None
        if allow_redirects:
            self.handle_httpstatus_list = SequenceExclude(range(300, 400))

    def _key_for_pipe(
        self,
        key: str,
        base_class_name: str | None = None,
        settings: Settings | None = None,
    ) -> str:
        class_name = self.__class__.__name__
        formatted_key = f"{class_name.upper()}_{key}"
        if (
            not base_class_name
            or class_name == base_class_name
            or (settings and not settings.get(formatted_key))
        ):
            return key
        return formatted_key

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler=crawler)

    @_warn_spider_arg
    def open_spider(self, spider: Spider | None = None) -> None:
        assert self.crawler.spider
        self.spiderinfo = self.SpiderInfo(self.crawler.spider)

    @_warn_spider_arg
    async def process_item(self, item: Any, spider: Spider | None = None) -> Any:
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        coros = [self._process_request(r, info, item) for r in requests]
        results: list[FileInfoOrError] = []
        if coros:
            if is_asyncio_available():
                results_asyncio = await asyncio.gather(*coros, return_exceptions=True)
                for res in results_asyncio:
                    if isinstance(res, BaseException):
                        results.append((False, Failure(res)))
                    else:
                        results.append((True, res))
            else:
                results = await cast(
                    "Deferred[list[FileInfoOrError]]",
                    DeferredList(
                        (deferred_from_coro(coro) for coro in coros), consumeErrors=True
                    ),
                )
        return self.item_completed(results, item, info)

    async def _process_request(
        self, request: Request, info: SpiderInfo, item: Any
    ) -> FileInfo:
        fp = self._fingerprinter.fingerprint(request)

        eb = request.errback
        request.callback = NO_CALLBACK
        request.errback = None

        # Return cached result if request was already seen
        if fp in info.downloaded:
            await _defer_sleep_async()
            cached_result = info.downloaded[fp]
            if isinstance(cached_result, Failure):
                if eb:
                    return eb(cached_result)
                cached_result.raiseException()
            return cached_result

        # Otherwise, wait for result
        wad: Deferred[FileInfo] = Deferred()
        if eb:
            wad.addErrback(eb)
        info.waiting[fp].append(wad)

        # Check if request is downloading right now to avoid doing it twice
        if fp in info.downloading:
            return await maybe_deferred_to_future(wad)

        # Download request checking media_to_download hook output first
        info.downloading.add(fp)
        await _defer_sleep_async()
        result: FileInfo | Failure
        try:
            file_info: FileInfo | None = await ensure_awaitable(
                self.media_to_download(request, info, item=item)
            )
            if file_info:
                # got a result without downloading
                result = file_info
            else:
                # download the result
                result = await self._check_media_to_download(request, info, item=item)
        except Exception:
            result = Failure()
            logger.exception(result)
        self._cache_result_and_execute_waiters(result, fp, info)
        return await maybe_deferred_to_future(wad)  # it must return wad at last

    def _modify_media_request(self, request: Request) -> None:
        if self.handle_httpstatus_list:
            request.meta["handle_httpstatus_list"] = self.handle_httpstatus_list
        else:
            request.meta["handle_httpstatus_all"] = True

    async def _check_media_to_download(
        self, request: Request, info: SpiderInfo, item: Any
    ) -> FileInfo:
        try:
            self._modify_media_request(request)
            assert self.crawler.engine
            response = await self.crawler.engine.download_async(request)
            return await ensure_awaitable(
                self.media_downloaded(response, request, info, item=item)
            )
        except Exception:
            failure = self.media_failed(Failure(), request, info)
            if isinstance(failure, Failure):
                warnings.warn(
                    f"{global_object_name(self.media_failed)} returned a Failure instance."
                    f" This is deprecated, please raise an exception instead, e.g. via failure.raiseException().",
                    category=ScrapyDeprecationWarning,
                    stacklevel=2,
                )
                failure.raiseException()

    def _cache_result_and_execute_waiters(
        self, result: FileInfo | Failure, fp: bytes, info: SpiderInfo
    ) -> None:
        if isinstance(result, Failure):
            # minimize cached information for failure
            result.cleanFailure()
            result.frames = []
            if twisted_version < Version("twisted", 24, 10, 0):
                result.stack = []  # type: ignore[method-assign]
            # This code fixes a memory leak by avoiding to keep references to
            # the Request and Response objects on the Media Pipeline cache.
            #
            # What happens when the media_downloaded callback raises an
            # exception, for example a FileException('download-error') when
            # the Response status code is not 200 OK, is that the original
            # StopIteration exception (which in turn contains the failed
            # Response and by extension, the original Request) gets encapsulated
            # within the FileException context.
            #
            # Originally, Scrapy was using twisted.internet.defer.returnValue
            # inside functions decorated with twisted.internet.defer.inlineCallbacks,
            # encapsulating the returned Response in a _DefGen_Return exception
            # instead of a StopIteration.
            #
            # To avoid keeping references to the Response and therefore Request
            # objects on the Media Pipeline cache, we should wipe the context of
            # the encapsulated exception when it is a StopIteration instance
            context = getattr(result.value, "__context__", None)
            if isinstance(context, StopIteration):
                result.value.__context__ = None

        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            if isinstance(result, Failure):
                call_later(_DEFER_DELAY, wad.errback, result)
            else:
                call_later(_DEFER_DELAY, wad.callback, result)

    # Overridable Interface
    @abstractmethod
    def media_to_download(
        self, request: Request, info: SpiderInfo, *, item: Any = None
    ) -> Deferred[FileInfo | None] | None:
        """Check request before starting download"""
        raise NotImplementedError

    @abstractmethod
    def get_media_requests(self, item: Any, info: SpiderInfo) -> list[Request]:
        """Returns the media requests to download"""
        raise NotImplementedError

    @abstractmethod
    def media_downloaded(
        self,
        response: Response,
        request: Request,
        info: SpiderInfo,
        *,
        item: Any = None,
    ) -> FileInfo:
        """Handler for success downloads"""
        raise NotImplementedError

    @abstractmethod
    def media_failed(
        self, failure: Failure, request: Request, info: SpiderInfo
    ) -> Failure:
        """Handler for failed downloads"""
        raise NotImplementedError

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: SpiderInfo
    ) -> Any:
        """Called per item when all media requests has been processed"""
        if self.LOG_FAILED_RESULTS:
            for ok, value in results:
                if not ok:
                    assert isinstance(value, Failure)
                    logger.error(
                        "%(class)s found errors processing %(item)s",
                        {"class": self.__class__.__name__, "item": item},
                        exc_info=failure_to_exc_info(value),
                        extra={"spider": info.spider},
                    )
        return item

    @abstractmethod
    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        """Returns the path where downloaded media should be stored"""
        raise NotImplementedError

```

```python
"""
Files Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import mimetypes
import time
import warnings
from collections import defaultdict
from contextlib import suppress
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, NoReturn, Protocol, TypedDict, cast
from urllib.parse import urlparse

from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.threads import deferToThread

from scrapy.exceptions import IgnoreRequest, NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.media import FileInfo, FileInfoOrError, MediaPipeline
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.datatypes import CaseInsensitiveDict
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import to_bytes
from scrapy.utils.request import referer_str

if TYPE_CHECKING:
    from os import PathLike

    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


def _to_string(path: str | PathLike[str]) -> str:
    return str(path)  # convert a Path object to string


def _md5sum(file: IO[bytes]) -> str:
    """Calculate the md5 checksum of a file-like object without reading its
    whole content in memory.

    >>> from io import BytesIO
    >>> _md5sum(BytesIO(b'file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'
    """
    m = hashlib.md5()  # noqa: S324
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


class FileException(Exception):
    """General media error exception"""


class StatInfo(TypedDict, total=False):
    checksum: str
    last_modified: float


class FilesStoreProtocol(Protocol):
    def __init__(self, basedir: str): ...

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any] | None: ...

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> StatInfo | Deferred[StatInfo]: ...


class FSFilesStore:
    def __init__(self, basedir: str | PathLike[str]):
        basedir = _to_string(basedir)
        if "://" in basedir:
            basedir = basedir.split("://", 1)[1]
        self.basedir: str = basedir
        self._mkdir(Path(self.basedir))
        self.created_directories: defaultdict[MediaPipeline.SpiderInfo, set[str]] = (
            defaultdict(set)
        )

    def persist_file(
        self,
        path: str | PathLike[str],
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        absolute_path = self._get_filesystem_path(path)
        self._mkdir(absolute_path.parent, info)
        absolute_path.write_bytes(buf.getvalue())

    def stat_file(
        self, path: str | PathLike[str], info: MediaPipeline.SpiderInfo
    ) -> StatInfo:
        absolute_path = self._get_filesystem_path(path)
        try:
            last_modified = absolute_path.stat().st_mtime
        except OSError:
            return {}

        with absolute_path.open("rb") as f:
            checksum = _md5sum(f)

        return {"last_modified": last_modified, "checksum": checksum}

    def _get_filesystem_path(self, path: str | PathLike[str]) -> Path:
        path_comps = _to_string(path).split("/")
        return Path(self.basedir, *path_comps)

    def _mkdir(
        self, dirname: Path, domain: MediaPipeline.SpiderInfo | None = None
    ) -> None:
        seen: set[str] = self.created_directories[domain] if domain else set()
        if str(dirname) not in seen:
            if not dirname.exists():
                dirname.mkdir(parents=True)
            seen.add(str(dirname))


class S3FilesStore:
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_SESSION_TOKEN = None
    AWS_ENDPOINT_URL = None
    AWS_REGION_NAME = None
    AWS_USE_SSL = None
    AWS_VERIFY = None

    POLICY = "private"  # Overridden from settings.FILES_STORE_S3_ACL in FilesPipeline.from_crawler()
    HEADERS = {
        "Cache-Control": "max-age=172800",
    }

    def __init__(self, uri: str):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")
        import botocore.session  # noqa: PLC0415

        session = botocore.session.get_session()
        self.s3_client = session.create_client(
            "s3",
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            aws_session_token=self.AWS_SESSION_TOKEN,
            endpoint_url=self.AWS_ENDPOINT_URL,
            region_name=self.AWS_REGION_NAME,
            use_ssl=self.AWS_USE_SSL,
            verify=self.AWS_VERIFY,
        )
        if not uri.startswith("s3://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 's3'")
        self.bucket, self.prefix = uri[5:].split("/", 1)

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(boto_key: dict[str, Any]) -> StatInfo:
            checksum = boto_key["ETag"].strip('"')
            last_modified = boto_key["LastModified"]
            modified_stamp = time.mktime(last_modified.timetuple())
            return {"checksum": checksum, "last_modified": modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_key(self, path: str) -> Deferred[dict[str, Any]]:
        key_name = f"{self.prefix}{path}"
        return cast(
            "Deferred[dict[str, Any]]",
            deferToThread(
                self.s3_client.head_object,  # type: ignore[attr-defined]
                Bucket=self.bucket,
                Key=key_name,
            ),
        )

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        """Upload file to S3 storage"""
        key_name = f"{self.prefix}{path}"
        buf.seek(0)
        extra = self._headers_to_botocore_kwargs(self.HEADERS)
        if headers:
            extra.update(self._headers_to_botocore_kwargs(headers))
        return deferToThread(
            self.s3_client.put_object,  # type: ignore[attr-defined]
            Bucket=self.bucket,
            Key=key_name,
            Body=buf,
            Metadata={k: str(v) for k, v in (meta or {}).items()},
            ACL=self.POLICY,
            **extra,
        )

    def _headers_to_botocore_kwargs(self, headers: dict[str, Any]) -> dict[str, Any]:
        """Convert headers to botocore keyword arguments."""
        # This is required while we need to support both boto and botocore.
        mapping = CaseInsensitiveDict(
            {
                "Content-Type": "ContentType",
                "Cache-Control": "CacheControl",
                "Content-Disposition": "ContentDisposition",
                "Content-Encoding": "ContentEncoding",
                "Content-Language": "ContentLanguage",
                "Content-Length": "ContentLength",
                "Content-MD5": "ContentMD5",
                "Expires": "Expires",
                "X-Amz-Grant-Full-Control": "GrantFullControl",
                "X-Amz-Grant-Read": "GrantRead",
                "X-Amz-Grant-Read-ACP": "GrantReadACP",
                "X-Amz-Grant-Write-ACP": "GrantWriteACP",
                "X-Amz-Object-Lock-Legal-Hold": "ObjectLockLegalHoldStatus",
                "X-Amz-Object-Lock-Mode": "ObjectLockMode",
                "X-Amz-Object-Lock-Retain-Until-Date": "ObjectLockRetainUntilDate",
                "X-Amz-Request-Payer": "RequestPayer",
                "X-Amz-Server-Side-Encryption": "ServerSideEncryption",
                "X-Amz-Server-Side-Encryption-Aws-Kms-Key-Id": "SSEKMSKeyId",
                "X-Amz-Server-Side-Encryption-Context": "SSEKMSEncryptionContext",
                "X-Amz-Server-Side-Encryption-Customer-Algorithm": "SSECustomerAlgorithm",
                "X-Amz-Server-Side-Encryption-Customer-Key": "SSECustomerKey",
                "X-Amz-Server-Side-Encryption-Customer-Key-Md5": "SSECustomerKeyMD5",
                "X-Amz-Storage-Class": "StorageClass",
                "X-Amz-Tagging": "Tagging",
                "X-Amz-Website-Redirect-Location": "WebsiteRedirectLocation",
            }
        )
        extra: dict[str, Any] = {}
        for key, value in headers.items():
            try:
                kwarg = mapping[key]
            except KeyError:
                raise TypeError(f'Header "{key}" is not supported by botocore')
            extra[kwarg] = value
        return extra


class GCSFilesStore:
    GCS_PROJECT_ID = None

    CACHE_CONTROL = "max-age=172800"

    # The bucket's default object ACL will be applied to the object.
    # Overridden from settings.FILES_STORE_GCS_ACL in FilesPipeline.from_crawler().
    POLICY = None

    def __init__(self, uri: str):
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client(project=self.GCS_PROJECT_ID)
        bucket, prefix = uri[5:].split("/", 1)
        self.bucket = client.bucket(bucket)
        self.prefix: str = prefix
        permissions = self.bucket.test_iam_permissions(
            ["storage.objects.get", "storage.objects.create"]
        )
        if "storage.objects.get" not in permissions:
            logger.warning(
                "No 'storage.objects.get' permission for GSC bucket %(bucket)s. "
                "Checking if files are up to date will be impossible. Files will be downloaded every time.",
                {"bucket": bucket},
            )
        if "storage.objects.create" not in permissions:
            logger.error(
                "No 'storage.objects.create' permission for GSC bucket %(bucket)s. Saving files will be impossible!",
                {"bucket": bucket},
            )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(blob) -> StatInfo:
            if blob:
                checksum = base64.b64decode(blob.md5_hash).hex()
                last_modified = time.mktime(blob.updated.timetuple())
                return {"checksum": checksum, "last_modified": last_modified}
            return {}

        blob_path = self._get_blob_path(path)
        return cast(
            "Deferred[StatInfo]",
            deferToThread(self.bucket.get_blob, blob_path).addCallback(_onsuccess),
        )

    def _get_content_type(self, headers: dict[str, str] | None) -> str:
        if headers and "Content-Type" in headers:
            return headers["Content-Type"]
        return "application/octet-stream"

    def _get_blob_path(self, path: str) -> str:
        return self.prefix + path

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        blob_path = self._get_blob_path(path)
        blob = self.bucket.blob(blob_path)
        blob.cache_control = self.CACHE_CONTROL
        blob.metadata = {k: str(v) for k, v in (meta or {}).items()}
        return deferToThread(
            blob.upload_from_string,
            data=buf.getvalue(),
            content_type=self._get_content_type(headers),
            predefined_acl=self.POLICY,
        )


class FTPFilesStore:
    FTP_USERNAME: str | None = None
    FTP_PASSWORD: str | None = None
    USE_ACTIVE_MODE: bool | None = None

    def __init__(self, uri: str):
        if not uri.startswith("ftp://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 'ftp'")
        u = urlparse(uri)
        assert u.port
        assert u.hostname
        self.port: int = u.port
        self.host: str = u.hostname
        self.port = int(u.port or 21)
        assert self.FTP_USERNAME
        assert self.FTP_PASSWORD
        self.username: str = u.username or self.FTP_USERNAME
        self.password: str = u.password or self.FTP_PASSWORD
        self.basedir: str = u.path.rstrip("/")

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        path = f"{self.basedir}/{path}"
        return deferToThread(
            ftp_store_file,
            path=path,
            file=buf,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_active_mode=self.USE_ACTIVE_MODE,
        )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _stat_file(path: str) -> StatInfo:
            try:
                ftp = FTP()
                ftp.connect(self.host, self.port)
                ftp.login(self.username, self.password)
                if self.USE_ACTIVE_MODE:
                    ftp.set_pasv(False)
                file_path = f"{self.basedir}/{path}"
                last_modified = float(ftp.voidcmd(f"MDTM {file_path}")[4:].strip())
                m = hashlib.md5()  # noqa: S324
                ftp.retrbinary(f"RETR {file_path}", m.update)
                return {"last_modified": last_modified, "checksum": m.hexdigest()}
            # The file doesn't exist
            except Exception:
                return {}

        return cast("Deferred[StatInfo]", deferToThread(_stat_file, path))


class FilesPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading

    This pipeline tries to minimize network transfers and file processing,
    doing stat of the files and determining if file is new, up-to-date or
    expired.

    ``new`` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    ``uptodate`` files are the ones that the pipeline processed and are still
        valid files.

    ``expired`` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME: str = "file"
    EXPIRES: int = 90
    STORE_SCHEMES: dict[str, type[FilesStoreProtocol]] = {
        "": FSFilesStore,
        "file": FSFilesStore,
        "s3": S3FilesStore,
        "gs": GCSFilesStore,
        "ftp": FTPFilesStore,
    }
    DEFAULT_FILES_URLS_FIELD: str = "file_urls"
    DEFAULT_FILES_RESULT_FIELD: str = "files"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of FilesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        if not (store_uri and (store_uri := _to_string(store_uri))):
            from scrapy.pipelines.images import ImagesPipeline  # noqa: PLC0415

            setting_name = (
                "IMAGES_STORE" if isinstance(self, ImagesPipeline) else "FILES_STORE"
            )
            raise NotConfigured(
                f"{setting_name} setting must be set to a valid path (not empty) "
                f"to enable {self.__class__.__name__}."
            )

        settings = crawler.settings
        cls_name = "FilesPipeline"
        self.store: FilesStoreProtocol = self._get_store(store_uri)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name=cls_name, settings=settings
        )
        self.expires: int = settings.getint(resolve("FILES_EXPIRES"), self.EXPIRES)
        if not hasattr(self, "FILES_URLS_FIELD"):
            self.FILES_URLS_FIELD = self.DEFAULT_FILES_URLS_FIELD
        if not hasattr(self, "FILES_RESULT_FIELD"):
            self.FILES_RESULT_FIELD = self.DEFAULT_FILES_RESULT_FIELD
        self.files_urls_field: str = settings.get(
            resolve("FILES_URLS_FIELD"), self.FILES_URLS_FIELD
        )
        self.files_result_field: str = settings.get(
            resolve("FILES_RESULT_FIELD"), self.FILES_RESULT_FIELD
        )

        super().__init__(crawler=crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["FILES_STORE"]
        return cls(store_uri, crawler=crawler)

    @classmethod
    def _update_stores(cls, settings: BaseSettings) -> None:
        s3store: type[S3FilesStore] = cast(
            "type[S3FilesStore]", cls.STORE_SCHEMES["s3"]
        )
        s3store.AWS_ACCESS_KEY_ID = settings["AWS_ACCESS_KEY_ID"]
        s3store.AWS_SECRET_ACCESS_KEY = settings["AWS_SECRET_ACCESS_KEY"]
        s3store.AWS_SESSION_TOKEN = settings["AWS_SESSION_TOKEN"]
        s3store.AWS_ENDPOINT_URL = settings["AWS_ENDPOINT_URL"]
        s3store.AWS_REGION_NAME = settings["AWS_REGION_NAME"]
        s3store.AWS_USE_SSL = settings["AWS_USE_SSL"]
        s3store.AWS_VERIFY = settings["AWS_VERIFY"]
        s3store.POLICY = settings["FILES_STORE_S3_ACL"]

        gcs_store: type[GCSFilesStore] = cast(
            "type[GCSFilesStore]", cls.STORE_SCHEMES["gs"]
        )
        gcs_store.GCS_PROJECT_ID = settings["GCS_PROJECT_ID"]
        gcs_store.POLICY = settings["FILES_STORE_GCS_ACL"] or None

        ftp_store: type[FTPFilesStore] = cast(
            "type[FTPFilesStore]", cls.STORE_SCHEMES["ftp"]
        )
        ftp_store.FTP_USERNAME = settings["FTP_USER"]
        ftp_store.FTP_PASSWORD = settings["FTP_PASSWORD"]
        ftp_store.USE_ACTIVE_MODE = settings.getbool("FEED_STORAGE_FTP_ACTIVE")

    def _get_store(self, uri: str) -> FilesStoreProtocol:
        # to support win32 paths like: C:\\some\dir
        scheme = "file" if Path(uri).is_absolute() else urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_to_download(
        self, request: Request, info: MediaPipeline.SpiderInfo, *, item: Any = None
    ) -> Deferred[FileInfo | None] | None:
        def _onsuccess(result: StatInfo) -> FileInfo | None:
            if not result:
                return None  # returning None force download

            last_modified = result.get("last_modified", None)
            if not last_modified:
                return None  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.expires:
                return None  # returning None force download

            referer = referer_str(request)
            logger.debug(
                "File (uptodate): Downloaded %(medianame)s from %(request)s "
                "referred in <%(referer)s>",
                {"medianame": self.MEDIA_NAME, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            self.inc_stats("uptodate")

            checksum = result.get("checksum", None)
            return {
                "url": request.url,
                "path": path,
                "checksum": checksum,
                "status": "uptodate",
            }

        path = self.file_path(request, info=info, item=item)
        # maybeDeferred() overloads don't seem to support a Union[_T, Deferred[_T]] return type
        dfd: Deferred[StatInfo] = maybeDeferred(self.store.stat_file, path, info)  # type: ignore[call-overload]
        dfd2: Deferred[FileInfo | None] = dfd.addCallback(_onsuccess)
        dfd2.addErrback(lambda _: None)
        dfd2.addErrback(
            lambda f: logger.error(
                self.__class__.__name__ + ".store.stat_file",
                exc_info=failure_to_exc_info(f),
                extra={"spider": info.spider},
            )
        )
        return dfd2

    def media_failed(
        self, failure: Failure, request: Request, info: MediaPipeline.SpiderInfo
    ) -> NoReturn:
        if not isinstance(failure.value, IgnoreRequest):
            referer = referer_str(request)
            logger.warning(
                "File (unknown-error): Error downloading %(medianame)s from "
                "%(request)s referred in <%(referer)s>: %(exception)s",
                {
                    "medianame": self.MEDIA_NAME,
                    "request": request,
                    "referer": referer,
                    "exception": failure.value,
                },
                extra={"spider": info.spider},
            )

        raise FileException

    def media_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> FileInfo:
        referer = referer_str(request)

        if response.status != 200:
            logger.warning(
                "File (code: %(status)s): Error downloading file from "
                "%(request)s referred in <%(referer)s>",
                {"status": response.status, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("download-error")

        if not response.body:
            logger.warning(
                "File (empty-content): Empty file from %(request)s referred "
                "in <%(referer)s>: no-content",
                {"request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("empty-content")

        status = "cached" if "cached" in response.flags else "downloaded"
        logger.debug(
            "File (%(status)s): Downloaded file from %(request)s referred in "
            "<%(referer)s>",
            {"status": status, "request": request, "referer": referer},
            extra={"spider": info.spider},
        )
        self.inc_stats(status)

        try:
            path = self.file_path(request, response=response, info=info, item=item)
            checksum = self.file_downloaded(response, request, info, item=item)
        except FileException as exc:
            logger.warning(
                "File (error): Error processing file from %(request)s "
                "referred in <%(referer)s>: %(errormsg)s",
                {"request": request, "referer": referer, "errormsg": str(exc)},
                extra={"spider": info.spider},
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "File (unknown-error): Error processing file from %(request)s "
                "referred in <%(referer)s>",
                {"request": request, "referer": referer},
                exc_info=True,
                extra={"spider": info.spider},
            )
            raise FileException(str(exc))

        return {
            "url": request.url,
            "path": path,
            "checksum": checksum,
            "status": status,
        }

    def inc_stats(self, status: str) -> None:
        assert self.crawler.stats
        self.crawler.stats.inc_value("file_count")
        self.crawler.stats.inc_value(f"file_status_count/{status}")

    # Overridable Interface
    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.files_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.files_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.files_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        media_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        media_ext = Path(request.url).suffix
        # Handles empty and wild extensions by trying to guess the
        # mime type then extension or default to empty string otherwise
        if media_ext not in mimetypes.types_map:
            media_ext = ""
            media_type = mimetypes.guess_type(request.url)[0]
            if media_type:
                media_ext = cast("str", mimetypes.guess_extension(media_type))
        return f"full/{media_guid}{media_ext}"

```

```python
"""
Files Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import mimetypes
import time
import warnings
from collections import defaultdict
from contextlib import suppress
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, NoReturn, Protocol, TypedDict, cast
from urllib.parse import urlparse

from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.threads import deferToThread

from scrapy.exceptions import IgnoreRequest, NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.media import FileInfo, FileInfoOrError, MediaPipeline
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.datatypes import CaseInsensitiveDict
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import to_bytes
from scrapy.utils.request import referer_str

if TYPE_CHECKING:
    from os import PathLike

    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


def _to_string(path: str | PathLike[str]) -> str:
    return str(path)  # convert a Path object to string


def _md5sum(file: IO[bytes]) -> str:
    """Calculate the md5 checksum of a file-like object without reading its
    whole content in memory.

    >>> from io import BytesIO
    >>> _md5sum(BytesIO(b'file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'
    """
    m = hashlib.md5()  # noqa: S324
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


class FileException(Exception):
    """General media error exception"""


class StatInfo(TypedDict, total=False):
    checksum: str
    last_modified: float


class FilesStoreProtocol(Protocol):
    def __init__(self, basedir: str): ...

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any] | None: ...

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> StatInfo | Deferred[StatInfo]: ...


class FSFilesStore:
    def __init__(self, basedir: str | PathLike[str]):
        basedir = _to_string(basedir)
        if "://" in basedir:
            basedir = basedir.split("://", 1)[1]
        self.basedir: str = basedir
        self._mkdir(Path(self.basedir))
        self.created_directories: defaultdict[MediaPipeline.SpiderInfo, set[str]] = (
            defaultdict(set)
        )

    def persist_file(
        self,
        path: str | PathLike[str],
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        absolute_path = self._get_filesystem_path(path)
        self._mkdir(absolute_path.parent, info)
        absolute_path.write_bytes(buf.getvalue())

    def stat_file(
        self, path: str | PathLike[str], info: MediaPipeline.SpiderInfo
    ) -> StatInfo:
        absolute_path = self._get_filesystem_path(path)
        try:
            last_modified = absolute_path.stat().st_mtime
        except OSError:
            return {}

        with absolute_path.open("rb") as f:
            checksum = _md5sum(f)

        return {"last_modified": last_modified, "checksum": checksum}

    def _get_filesystem_path(self, path: str | PathLike[str]) -> Path:
        path_comps = _to_string(path).split("/")
        return Path(self.basedir, *path_comps)

    def _mkdir(
        self, dirname: Path, domain: MediaPipeline.SpiderInfo | None = None
    ) -> None:
        seen: set[str] = self.created_directories[domain] if domain else set()
        if str(dirname) not in seen:
            if not dirname.exists():
                dirname.mkdir(parents=True)
            seen.add(str(dirname))


class S3FilesStore:
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_SESSION_TOKEN = None
    AWS_ENDPOINT_URL = None
    AWS_REGION_NAME = None
    AWS_USE_SSL = None
    AWS_VERIFY = None

    POLICY = "private"  # Overridden from settings.FILES_STORE_S3_ACL in FilesPipeline.from_crawler()
    HEADERS = {
        "Cache-Control": "max-age=172800",
    }

    def __init__(self, uri: str):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")
        import botocore.session  # noqa: PLC0415

        session = botocore.session.get_session()
        self.s3_client = session.create_client(
            "s3",
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            aws_session_token=self.AWS_SESSION_TOKEN,
            endpoint_url=self.AWS_ENDPOINT_URL,
            region_name=self.AWS_REGION_NAME,
            use_ssl=self.AWS_USE_SSL,
            verify=self.AWS_VERIFY,
        )
        if not uri.startswith("s3://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 's3'")
        self.bucket, self.prefix = uri[5:].split("/", 1)

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(boto_key: dict[str, Any]) -> StatInfo:
            checksum = boto_key["ETag"].strip('"')
            last_modified = boto_key["LastModified"]
            modified_stamp = time.mktime(last_modified.timetuple())
            return {"checksum": checksum, "last_modified": modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_key(self, path: str) -> Deferred[dict[str, Any]]:
        key_name = f"{self.prefix}{path}"
        return cast(
            "Deferred[dict[str, Any]]",
            deferToThread(
                self.s3_client.head_object,  # type: ignore[attr-defined]
                Bucket=self.bucket,
                Key=key_name,
            ),
        )

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        """Upload file to S3 storage"""
        key_name = f"{self.prefix}{path}"
        buf.seek(0)
        extra = self._headers_to_botocore_kwargs(self.HEADERS)
        if headers:
            extra.update(self._headers_to_botocore_kwargs(headers))
        return deferToThread(
            self.s3_client.put_object,  # type: ignore[attr-defined]
            Bucket=self.bucket,
            Key=key_name,
            Body=buf,
            Metadata={k: str(v) for k, v in (meta or {}).items()},
            ACL=self.POLICY,
            **extra,
        )

    def _headers_to_botocore_kwargs(self, headers: dict[str, Any]) -> dict[str, Any]:
        """Convert headers to botocore keyword arguments."""
        # This is required while we need to support both boto and botocore.
        mapping = CaseInsensitiveDict(
            {
                "Content-Type": "ContentType",
                "Cache-Control": "CacheControl",
                "Content-Disposition": "ContentDisposition",
                "Content-Encoding": "ContentEncoding",
                "Content-Language": "ContentLanguage",
                "Content-Length": "ContentLength",
                "Content-MD5": "ContentMD5",
                "Expires": "Expires",
                "X-Amz-Grant-Full-Control": "GrantFullControl",
                "X-Amz-Grant-Read": "GrantRead",
                "X-Amz-Grant-Read-ACP": "GrantReadACP",
                "X-Amz-Grant-Write-ACP": "GrantWriteACP",
                "X-Amz-Object-Lock-Legal-Hold": "ObjectLockLegalHoldStatus",
                "X-Amz-Object-Lock-Mode": "ObjectLockMode",
                "X-Amz-Object-Lock-Retain-Until-Date": "ObjectLockRetainUntilDate",
                "X-Amz-Request-Payer": "RequestPayer",
                "X-Amz-Server-Side-Encryption": "ServerSideEncryption",
                "X-Amz-Server-Side-Encryption-Aws-Kms-Key-Id": "SSEKMSKeyId",
                "X-Amz-Server-Side-Encryption-Context": "SSEKMSEncryptionContext",
                "X-Amz-Server-Side-Encryption-Customer-Algorithm": "SSECustomerAlgorithm",
                "X-Amz-Server-Side-Encryption-Customer-Key": "SSECustomerKey",
                "X-Amz-Server-Side-Encryption-Customer-Key-Md5": "SSECustomerKeyMD5",
                "X-Amz-Storage-Class": "StorageClass",
                "X-Amz-Tagging": "Tagging",
                "X-Amz-Website-Redirect-Location": "WebsiteRedirectLocation",
            }
        )
        extra: dict[str, Any] = {}
        for key, value in headers.items():
            try:
                kwarg = mapping[key]
            except KeyError:
                raise TypeError(f'Header "{key}" is not supported by botocore')
            extra[kwarg] = value
        return extra


class GCSFilesStore:
    GCS_PROJECT_ID = None

    CACHE_CONTROL = "max-age=172800"

    # The bucket's default object ACL will be applied to the object.
    # Overridden from settings.FILES_STORE_GCS_ACL in FilesPipeline.from_crawler().
    POLICY = None

    def __init__(self, uri: str):
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client(project=self.GCS_PROJECT_ID)
        bucket, prefix = uri[5:].split("/", 1)
        self.bucket = client.bucket(bucket)
        self.prefix: str = prefix
        permissions = self.bucket.test_iam_permissions(
            ["storage.objects.get", "storage.objects.create"]
        )
        if "storage.objects.get" not in permissions:
            logger.warning(
                "No 'storage.objects.get' permission for GSC bucket %(bucket)s. "
                "Checking if files are up to date will be impossible. Files will be downloaded every time.",
                {"bucket": bucket},
            )
        if "storage.objects.create" not in permissions:
            logger.error(
                "No 'storage.objects.create' permission for GSC bucket %(bucket)s. Saving files will be impossible!",
                {"bucket": bucket},
            )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(blob) -> StatInfo:
            if blob:
                checksum = base64.b64decode(blob.md5_hash).hex()
                last_modified = time.mktime(blob.updated.timetuple())
                return {"checksum": checksum, "last_modified": last_modified}
            return {}

        blob_path = self._get_blob_path(path)
        return cast(
            "Deferred[StatInfo]",
            deferToThread(self.bucket.get_blob, blob_path).addCallback(_onsuccess),
        )

    def _get_content_type(self, headers: dict[str, str] | None) -> str:
        if headers and "Content-Type" in headers:
            return headers["Content-Type"]
        return "application/octet-stream"

    def _get_blob_path(self, path: str) -> str:
        return self.prefix + path

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        blob_path = self._get_blob_path(path)
        blob = self.bucket.blob(blob_path)
        blob.cache_control = self.CACHE_CONTROL
        blob.metadata = {k: str(v) for k, v in (meta or {}).items()}
        return deferToThread(
            blob.upload_from_string,
            data=buf.getvalue(),
            content_type=self._get_content_type(headers),
            predefined_acl=self.POLICY,
        )


class FTPFilesStore:
    FTP_USERNAME: str | None = None
    FTP_PASSWORD: str | None = None
    USE_ACTIVE_MODE: bool | None = None

    def __init__(self, uri: str):
        if not uri.startswith("ftp://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 'ftp'")
        u = urlparse(uri)
        assert u.port
        assert u.hostname
        self.port: int = u.port
        self.host: str = u.hostname
        self.port = int(u.port or 21)
        assert self.FTP_USERNAME
        assert self.FTP_PASSWORD
        self.username: str = u.username or self.FTP_USERNAME
        self.password: str = u.password or self.FTP_PASSWORD
        self.basedir: str = u.path.rstrip("/")

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        path = f"{self.basedir}/{path}"
        return deferToThread(
            ftp_store_file,
            path=path,
            file=buf,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_active_mode=self.USE_ACTIVE_MODE,
        )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _stat_file(path: str) -> StatInfo:
            try:
                ftp = FTP()
                ftp.connect(self.host, self.port)
                ftp.login(self.username, self.password)
                if self.USE_ACTIVE_MODE:
                    ftp.set_pasv(False)
                file_path = f"{self.basedir}/{path}"
                last_modified = float(ftp.voidcmd(f"MDTM {file_path}")[4:].strip())
                m = hashlib.md5()  # noqa: S324
                ftp.retrbinary(f"RETR {file_path}", m.update)
                return {"last_modified": last_modified, "checksum": m.hexdigest()}
            # The file doesn't exist
            except Exception:
                return {}

        return cast("Deferred[StatInfo]", deferToThread(_stat_file, path))


class FilesPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading

    This pipeline tries to minimize network transfers and file processing,
    doing stat of the files and determining if file is new, up-to-date or
    expired.

    ``new`` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    ``uptodate`` files are the ones that the pipeline processed and are still
        valid files.

    ``expired`` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME: str = "file"
    EXPIRES: int = 90
    STORE_SCHEMES: dict[str, type[FilesStoreProtocol]] = {
        "": FSFilesStore,
        "file": FSFilesStore,
        "s3": S3FilesStore,
        "gs": GCSFilesStore,
        "ftp": FTPFilesStore,
    }
    DEFAULT_FILES_URLS_FIELD: str = "file_urls"
    DEFAULT_FILES_RESULT_FIELD: str = "files"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of FilesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        if not (store_uri and (store_uri := _to_string(store_uri))):
            from scrapy.pipelines.images import ImagesPipeline  # noqa: PLC0415

            setting_name = (
                "IMAGES_STORE" if isinstance(self, ImagesPipeline) else "FILES_STORE"
            )
            raise NotConfigured(
                f"{setting_name} setting must be set to a valid path (not empty) "
                f"to enable {self.__class__.__name__}."
            )

        settings = crawler.settings
        cls_name = "FilesPipeline"
        self.store: FilesStoreProtocol = self._get_store(store_uri)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name=cls_name, settings=settings
        )
        self.expires: int = settings.getint(resolve("FILES_EXPIRES"), self.EXPIRES)
        if not hasattr(self, "FILES_URLS_FIELD"):
            self.FILES_URLS_FIELD = self.DEFAULT_FILES_URLS_FIELD
        if not hasattr(self, "FILES_RESULT_FIELD"):
            self.FILES_RESULT_FIELD = self.DEFAULT_FILES_RESULT_FIELD
        self.files_urls_field: str = settings.get(
            resolve("FILES_URLS_FIELD"), self.FILES_URLS_FIELD
        )
        self.files_result_field: str = settings.get(
            resolve("FILES_RESULT_FIELD"), self.FILES_RESULT_FIELD
        )

        super().__init__(crawler=crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["FILES_STORE"]
        return cls(store_uri, crawler=crawler)

    @classmethod
    def _update_stores(cls, settings: BaseSettings) -> None:
        s3store: type[S3FilesStore] = cast(
            "type[S3FilesStore]", cls.STORE_SCHEMES["s3"]
        )
        s3store.AWS_ACCESS_KEY_ID = settings["AWS_ACCESS_KEY_ID"]
        s3store.AWS_SECRET_ACCESS_KEY = settings["AWS_SECRET_ACCESS_KEY"]
        s3store.AWS_SESSION_TOKEN = settings["AWS_SESSION_TOKEN"]
        s3store.AWS_ENDPOINT_URL = settings["AWS_ENDPOINT_URL"]
        s3store.AWS_REGION_NAME = settings["AWS_REGION_NAME"]
        s3store.AWS_USE_SSL = settings["AWS_USE_SSL"]
        s3store.AWS_VERIFY = settings["AWS_VERIFY"]
        s3store.POLICY = settings["FILES_STORE_S3_ACL"]

        gcs_store: type[GCSFilesStore] = cast(
            "type[GCSFilesStore]", cls.STORE_SCHEMES["gs"]
        )
        gcs_store.GCS_PROJECT_ID = settings["GCS_PROJECT_ID"]
        gcs_store.POLICY = settings["FILES_STORE_GCS_ACL"] or None

        ftp_store: type[FTPFilesStore] = cast(
            "type[FTPFilesStore]", cls.STORE_SCHEMES["ftp"]
        )
        ftp_store.FTP_USERNAME = settings["FTP_USER"]
        ftp_store.FTP_PASSWORD = settings["FTP_PASSWORD"]
        ftp_store.USE_ACTIVE_MODE = settings.getbool("FEED_STORAGE_FTP_ACTIVE")

    def _get_store(self, uri: str) -> FilesStoreProtocol:
        # to support win32 paths like: C:\\some\dir
        scheme = "file" if Path(uri).is_absolute() else urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_to_download(
        self, request: Request, info: MediaPipeline.SpiderInfo, *, item: Any = None
    ) -> Deferred[FileInfo | None] | None:
        def _onsuccess(result: StatInfo) -> FileInfo | None:
            if not result:
                return None  # returning None force download

            last_modified = result.get("last_modified", None)
            if not last_modified:
                return None  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.expires:
                return None  # returning None force download

            referer = referer_str(request)
            logger.debug(
                "File (uptodate): Downloaded %(medianame)s from %(request)s "
                "referred in <%(referer)s>",
                {"medianame": self.MEDIA_NAME, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            self.inc_stats("uptodate")

            checksum = result.get("checksum", None)
            return {
                "url": request.url,
                "path": path,
                "checksum": checksum,
                "status": "uptodate",
            }

        path = self.file_path(request, info=info, item=item)
        # maybeDeferred() overloads don't seem to support a Union[_T, Deferred[_T]] return type
        dfd: Deferred[StatInfo] = maybeDeferred(self.store.stat_file, path, info)  # type: ignore[call-overload]
        dfd2: Deferred[FileInfo | None] = dfd.addCallback(_onsuccess)
        dfd2.addErrback(lambda _: None)
        dfd2.addErrback(
            lambda f: logger.error(
                self.__class__.__name__ + ".store.stat_file",
                exc_info=failure_to_exc_info(f),
                extra={"spider": info.spider},
            )
        )
        return dfd2

    def media_failed(
        self, failure: Failure, request: Request, info: MediaPipeline.SpiderInfo
    ) -> NoReturn:
        if not isinstance(failure.value, IgnoreRequest):
            referer = referer_str(request)
            logger.warning(
                "File (unknown-error): Error downloading %(medianame)s from "
                "%(request)s referred in <%(referer)s>: %(exception)s",
                {
                    "medianame": self.MEDIA_NAME,
                    "request": request,
                    "referer": referer,
                    "exception": failure.value,
                },
                extra={"spider": info.spider},
            )

        raise FileException

    async def media_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> FileInfo:
        referer = referer_str(request)

        if response.status != 200:
            logger.warning(
                "File (code: %(status)s): Error downloading file from "
                "%(request)s referred in <%(referer)s>",
                {"status": response.status, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("download-error")

        if not response.body:
            logger.warning(
                "File (empty-content): Empty file from %(request)s referred "
                "in <%(referer)s>: no-content",
                {"request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("empty-content")

        status = "cached" if "cached" in response.flags else "downloaded"
        logger.debug(
            "File (%(status)s): Downloaded file from %(request)s referred in "
            "<%(referer)s>",
            {"status": status, "request": request, "referer": referer},
            extra={"spider": info.spider},
        )
        self.inc_stats(status)

        try:
            path = self.file_path(request, response=response, info=info, item=item)
            checksum = await ensure_awaitable(
                self.file_downloaded(response, request, info, item=item)
            )
        except FileException as exc:
            logger.warning(
                "File (error): Error processing file from %(request)s "
                "referred in <%(referer)s>: %(errormsg)s",
                {"request": request, "referer": referer, "errormsg": str(exc)},
                extra={"spider": info.spider},
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "File (unknown-error): Error processing file from %(request)s "
                "referred in <%(referer)s>",
                {"request": request, "referer": referer},
                exc_info=True,
                extra={"spider": info.spider},
            )
            raise FileException(str(exc))

        return {
            "url": request.url,
            "path": path,
            "checksum": checksum,
            "status": status,
        }

    def inc_stats(self, status: str) -> None:
        assert self.crawler.stats
        self.crawler.stats.inc_value("file_count")
        self.crawler.stats.inc_value(f"file_status_count/{status}")

    # Overridable Interface
    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.files_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.files_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    async def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        dfd = maybeDeferred(self.store.persist_file, path, buf, info)
        await maybe_deferred_to_future(dfd)
        return checksum

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.files_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        media_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        media_ext = Path(request.url).suffix
        # Handles empty and wild extensions by trying to guess the
        # mime type then extension or default to empty string otherwise
        if media_ext not in mimetypes.types_map:
            media_ext = ""
            media_type = mimetypes.guess_type(request.url)[0]
            if media_type:
                media_ext = cast("str", mimetypes.guess_extension(media_type))
        return f"full/{media_guid}{media_ext}"

```

```python
"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import functools
import hashlib
import warnings
from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter
from twisted.internet.defer import maybeDeferred

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline, _md5sum
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from PIL import Image

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.pipelines.media import FileInfoOrError, MediaPipeline


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic"""

    MEDIA_NAME: str = "image"

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH: int = 0
    MIN_HEIGHT: int = 0
    EXPIRES: int = 90
    THUMBS: dict[str, tuple[int, int]] = {}
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of ImagesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        try:
            from PIL import Image, ImageOps  # noqa: PLC0415

            self._Image = Image
            self._ImageOps = ImageOps
        except ImportError:
            raise NotConfigured(
                "ImagesPipeline requires installing Pillow 8.3.2 or later"
            )

        super().__init__(store_uri, crawler=crawler)

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe,
            base_class_name="ImagesPipeline",
            settings=settings,
        )
        self.expires: int = settings.getint(resolve("IMAGES_EXPIRES"), self.EXPIRES)

        if not hasattr(self, "IMAGES_RESULT_FIELD"):
            self.IMAGES_RESULT_FIELD: str = self.DEFAULT_IMAGES_RESULT_FIELD
        if not hasattr(self, "IMAGES_URLS_FIELD"):
            self.IMAGES_URLS_FIELD: str = self.DEFAULT_IMAGES_URLS_FIELD

        self.images_urls_field: str = settings.get(
            resolve("IMAGES_URLS_FIELD"), self.IMAGES_URLS_FIELD
        )
        self.images_result_field: str = settings.get(
            resolve("IMAGES_RESULT_FIELD"), self.IMAGES_RESULT_FIELD
        )
        self.min_width: int = settings.getint(
            resolve("IMAGES_MIN_WIDTH"), self.MIN_WIDTH
        )
        self.min_height: int = settings.getint(
            resolve("IMAGES_MIN_HEIGHT"), self.MIN_HEIGHT
        )
        self.thumbs: dict[str, tuple[int, int]] = settings.get(
            resolve("IMAGES_THUMBS"), self.THUMBS
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, crawler=crawler)

    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        return self.image_downloaded(response, request, info, item=item)

    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        assert checksum is not None
        return checksum

    def get_images(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> Iterable[tuple[str, Image.Image, BytesIO]]:
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = self._Image.open(BytesIO(response.body))
        transposed_image = self._ImageOps.exif_transpose(orig_image)

        width, height = transposed_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            transposed_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, response_body=buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(
        self,
        image: Image.Image,
        size: tuple[int, int] | None = None,
        *,
        response_body: BytesIO,
    ) -> tuple[Image.Image, BytesIO]:
        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS  # type: ignore[attr-defined]
            image.thumbnail(size, resampling_filter)
        elif image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.images_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"full/{image_guid}.jpg"

    def thumb_path(
        self,
        request: Request,
        thumb_id: str,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        thumb_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"

```

```python
"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import functools
import hashlib
import warnings
from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter
from twisted.internet.defer import maybeDeferred

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline, _md5sum
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from PIL import Image

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.pipelines.media import FileInfoOrError, MediaPipeline


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic"""

    MEDIA_NAME: str = "image"

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH: int = 0
    MIN_HEIGHT: int = 0
    EXPIRES: int = 90
    THUMBS: dict[str, tuple[int, int]] = {}
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of ImagesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        try:
            from PIL import Image, ImageOps  # noqa: PLC0415

            self._Image = Image
            self._ImageOps = ImageOps
        except ImportError:
            raise NotConfigured(
                "ImagesPipeline requires installing Pillow 8.3.2 or later"
            )

        super().__init__(store_uri, crawler=crawler)

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe,
            base_class_name="ImagesPipeline",
            settings=settings,
        )
        self.expires: int = settings.getint(resolve("IMAGES_EXPIRES"), self.EXPIRES)

        if not hasattr(self, "IMAGES_RESULT_FIELD"):
            self.IMAGES_RESULT_FIELD: str = self.DEFAULT_IMAGES_RESULT_FIELD
        if not hasattr(self, "IMAGES_URLS_FIELD"):
            self.IMAGES_URLS_FIELD: str = self.DEFAULT_IMAGES_URLS_FIELD

        self.images_urls_field: str = settings.get(
            resolve("IMAGES_URLS_FIELD"), self.IMAGES_URLS_FIELD
        )
        self.images_result_field: str = settings.get(
            resolve("IMAGES_RESULT_FIELD"), self.IMAGES_RESULT_FIELD
        )
        self.min_width: int = settings.getint(
            resolve("IMAGES_MIN_WIDTH"), self.MIN_WIDTH
        )
        self.min_height: int = settings.getint(
            resolve("IMAGES_MIN_HEIGHT"), self.MIN_HEIGHT
        )
        self.thumbs: dict[str, tuple[int, int]] = settings.get(
            resolve("IMAGES_THUMBS"), self.THUMBS
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, crawler=crawler)

    async def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        return await ensure_awaitable(
            self.image_downloaded(response, request, info, item=item)
        )

    async def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            dfd = maybeDeferred(
                self.store.persist_file,
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
            await maybe_deferred_to_future(dfd)
        assert checksum is not None
        return checksum

    def get_images(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> Iterable[tuple[str, Image.Image, BytesIO]]:
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = self._Image.open(BytesIO(response.body))
        transposed_image = self._ImageOps.exif_transpose(orig_image)

        width, height = transposed_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            transposed_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, response_body=buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(
        self,
        image: Image.Image,
        size: tuple[int, int] | None = None,
        *,
        response_body: BytesIO,
    ) -> tuple[Image.Image, BytesIO]:
        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS  # type: ignore[attr-defined]
            image.thumbnail(size, resampling_filter)
        elif image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.images_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"full/{image_guid}.jpg"

    def thumb_path(
        self,
        request: Request,
        thumb_id: str,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        thumb_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"

```

```python
import dataclasses
import os
import random
import time
import warnings
from abc import ABC, abstractmethod
from datetime import datetime
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from posixpath import split
from shutil import rmtree
from tempfile import mkdtemp
from typing import Any
from unittest import mock
from unittest.mock import MagicMock
from urllib.parse import urlparse

import attr
import pytest
from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred

from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.pipelines.files import (
    FilesPipeline,
    FSFilesStore,
    FTPFilesStore,
    GCSFilesStore,
    S3FilesStore,
)
from scrapy.settings import Settings
from scrapy.utils.defer import _defer_sleep_async, deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.ftp import MockFTPServer
from tests.utils.decorators import deferred_f_from_coro_f, inlineCallbacks

from .test_pipeline_media import _mocked_download_func


def get_gcs_content_and_delete(
    bucket: Any, path: str
) -> tuple[bytes, list[dict[str, str]], Any]:
    from google.cloud import storage  # noqa: PLC0415

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


class TestFilesPipeline:
    def setup_method(self):
        self.tempdir = mkdtemp()
        settings_dict = {"FILES_STORE": self.tempdir}
        crawler = get_crawler(DefaultSpider, settings_dict=settings_dict)
        crawler.spider = crawler._create_spider()
        crawler.engine = MagicMock(download_async=_mocked_download_func)
        self.pipeline = FilesPipeline.from_crawler(crawler)
        self.pipeline.open_spider()

    def teardown_method(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        assert (
            file_path(Request("https://dev.mydeco.com/mydeco.pdf"))
            == "full/c9b564df929f4bc635bdd19fde4f3d4847c757c5.pdf"
        )
        assert (
            file_path(
                Request(
                    "http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.txt"
                )
            )
            == "full/4ce274dd83db0368bafd7e406f382ae088e39219.txt"
        )
        assert (
            file_path(
                Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.doc")
            )
            == "full/94ccc495a17b9ac5d40e3eabf3afcb8c2c9b9e1a.doc"
        )
        assert (
            file_path(
                Request(
                    "http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg"
                )
            )
            == "full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532/"))
            == "full/97ee6f8a46cbbb418ea91502fd24176865cf39b2"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532"))
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1"
        )
        assert (
            file_path(
                Request("http://www.dorma.co.uk/images/product_details/2532"),
                response=Response("http://www.dorma.co.uk/images/product_details/2532"),
                info=object(),
            )
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1"
        )
        assert (
            file_path(
                Request(
                    "http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg.bohaha"
                )
            )
            == "full/76c00cef2ef669ae65052661f68d451162829507"
        )
        assert (
            file_path(
                Request(
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAR0AAACxCAMAAADOHZloAAACClBMVEX/\
                                    //+F0tzCwMK76ZKQ21AMqr7oAAC96JvD5aWM2kvZ78J0N7fmAAC46Y4Ap7y"
                )
            )
            == "full/178059cbeba2e34120a67f2dc1afc3ecc09b61cb.png"
        )

    def test_fs_store(self):
        assert isinstance(self.pipeline.store, FSFilesStore)
        assert self.pipeline.store.basedir == self.tempdir

        path = "some/image/key.jpg"
        fullpath = Path(self.tempdir, "some", "image", "key.jpg")
        assert self.pipeline.store._get_filesystem_path(path) == fullpath

    @deferred_f_from_coro_f
    async def test_file_not_expired(self):
        item_url = "http://example.com/file.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={"checksum": "abc", "last_modified": time.time()},
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url)],
            ),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] == "abc"
        assert result["files"][0]["status"] == "uptodate"

        for p in patchers:
            p.stop()

    @deferred_f_from_coro_f
    async def test_file_expired(self):
        item_url = "http://example.com/file2.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={
                    "checksum": "abc",
                    "last_modified": time.time()
                    - (self.pipeline.expires * 60 * 60 * 24 * 2),
                },
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url)],
            ),
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] != "abc"
        assert result["files"][0]["status"] == "downloaded"

        for p in patchers:
            p.stop()

    @deferred_f_from_coro_f
    async def test_file_cached(self):
        item_url = "http://example.com/file3.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={
                    "checksum": "abc",
                    "last_modified": time.time()
                    - (self.pipeline.expires * 60 * 60 * 24 * 2),
                },
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url, flags=["cached"])],
            ),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] != "abc"
        assert result["files"][0]["status"] == "cached"

        for p in patchers:
            p.stop()

    def test_file_path_from_item(self):
        """
        Custom file path based on item data, overriding default implementation
        """

        class CustomFilesPipeline(FilesPipeline):
            def file_path(self, request, response=None, info=None, item=None):
                return f"full/{item.get('path')}"

        file_path = CustomFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": self.tempdir})
        ).file_path
        item = {"path": "path-to-store-file"}
        request = Request("http://example.com")
        assert file_path(request, item=item) == "full/path-to-store-file"

    @pytest.mark.parametrize(
        "bad_type",
        [
            "http://example.com/file.pdf",
            ("http://example.com/file.pdf",),
            {"url": "http://example.com/file.pdf"},
            123,
            None,
        ],
    )
    def test_rejects_non_list_file_urls(self, tmp_path, bad_type):
        pipeline = FilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": str(tmp_path)})
        )
        item = ItemWithFiles()
        item["file_urls"] = bad_type

        with pytest.raises(TypeError, match="file_urls must be a list of URLs"):
            list(pipeline.get_media_requests(item, None))


class TestFilesPipelineFieldsMixin(ABC):
    @property
    @abstractmethod
    def item_class(self) -> Any:
        raise NotImplementedError

    def test_item_fields_default(self, tmp_path):
        url = "http://www.example.com/files/1.txt"
        item = self.item_class(name="item1", file_urls=[url])
        pipeline = FilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        files = ItemAdapter(item).get("files")
        assert files == [results[0][1]]
        assert isinstance(item, self.item_class)

    def test_item_fields_override_settings(self, tmp_path):
        url = "http://www.example.com/files/1.txt"
        item = self.item_class(name="item1", custom_file_urls=[url])
        pipeline = FilesPipeline.from_crawler(
            get_crawler(
                None,
                {
                    "FILES_STORE": tmp_path,
                    "FILES_URLS_FIELD": "custom_file_urls",
                    "FILES_RESULT_FIELD": "custom_files",
                },
            )
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        custom_files = ItemAdapter(item).get("custom_files")
        assert custom_files == [results[0][1]]
        assert isinstance(item, self.item_class)


class TestFilesPipelineFieldsDict(TestFilesPipelineFieldsMixin):
    item_class = dict


class FilesPipelineTestItem(Item):
    name = Field()
    # default fields
    file_urls = Field()
    files = Field()
    # overridden fields
    custom_file_urls = Field()
    custom_files = Field()


class TestFilesPipelineFieldsItem(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestItem


@dataclasses.dataclass
class FilesPipelineTestDataClass:
    name: str
    # default fields
    file_urls: list = dataclasses.field(default_factory=list)
    files: list = dataclasses.field(default_factory=list)
    # overridden fields
    custom_file_urls: list = dataclasses.field(default_factory=list)
    custom_files: list = dataclasses.field(default_factory=list)


class TestFilesPipelineFieldsDataClass(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestDataClass


@attr.s
class FilesPipelineTestAttrsItem:
    name = attr.ib(default="")
    # default fields
    file_urls: list[str] = attr.ib(default=list)
    files: list[dict[str, str]] = attr.ib(default=list)
    # overridden fields
    custom_file_urls: list[str] = attr.ib(default=list)
    custom_files: list[dict[str, str]] = attr.ib(default=list)


class TestFilesPipelineFieldsAttrsItem(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestAttrsItem


class TestFilesPipelineCustomSettings:
    default_cls_settings = {
        "EXPIRES": 90,
        "FILES_URLS_FIELD": "file_urls",
        "FILES_RESULT_FIELD": "files",
    }
    file_cls_attr_settings_map = {
        ("EXPIRES", "FILES_EXPIRES", "expires"),
        ("FILES_URLS_FIELD", "FILES_URLS_FIELD", "files_urls_field"),
        ("FILES_RESULT_FIELD", "FILES_RESULT_FIELD", "files_result_field"),
    }

    def _generate_fake_settings(self, tmp_path, prefix=None):
        def random_string():
            return "".join([chr(random.randint(97, 123)) for _ in range(10)])

        settings = {
            "FILES_EXPIRES": random.randint(100, 1000),
            "FILES_URLS_FIELD": random_string(),
            "FILES_RESULT_FIELD": random_string(),
            "FILES_STORE": tmp_path,
        }
        if not prefix:
            return settings

        return {
            prefix.upper() + "_" + k if k != "FILES_STORE" else k: v
            for k, v in settings.items()
        }

    def _generate_fake_pipeline(self):
        class UserDefinedFilePipeline(FilesPipeline):
            EXPIRES = 1001
            FILES_URLS_FIELD = "alfa"
            FILES_RESULT_FIELD = "beta"

        return UserDefinedFilePipeline

    def test_different_settings_for_different_instances(self, tmp_path):
        """
        If there are different instances with different settings they should keep
        different settings.
        """
        custom_settings = self._generate_fake_settings(tmp_path)
        another_pipeline = FilesPipeline.from_crawler(
            get_crawler(None, custom_settings)
        )
        one_pipeline = FilesPipeline(tmp_path, crawler=get_crawler(None))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            default_value = self.default_cls_settings[pipe_attr]
            assert getattr(one_pipeline, pipe_attr) == default_value
            custom_value = custom_settings[settings_attr]
            assert default_value != custom_value
            assert getattr(another_pipeline, pipe_ins_attr) == custom_value

    def test_subclass_attributes_preserved_if_no_settings(self, tmp_path):
        """
        If subclasses override class attributes and there are no special settings those values should be kept.
        """
        pipe_cls = self._generate_fake_pipeline()
        pipe = pipe_cls.from_crawler(get_crawler(None, {"FILES_STORE": tmp_path}))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            custom_value = getattr(pipe, pipe_ins_attr)
            assert custom_value != self.default_cls_settings[pipe_attr]
            assert getattr(pipe, pipe_ins_attr) == getattr(pipe, pipe_attr)

    def test_subclass_attrs_preserved_custom_settings(self, tmp_path):
        """
        If file settings are defined but they are not defined for subclass
        settings should be preserved.
        """
        pipeline_cls = self._generate_fake_pipeline()
        settings = self._generate_fake_settings(tmp_path)
        pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            value = getattr(pipeline, pipe_ins_attr)
            setting_value = settings.get(settings_attr)
            assert value != self.default_cls_settings[pipe_attr]
            assert value == setting_value

    def test_no_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are no settings for subclass and no subclass attributes, pipeline should use
        attributes of base class.
        """

        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        user_pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = self.default_cls_settings.get(pipe_attr.upper())
            assert getattr(user_pipeline, pipe_ins_attr) == custom_value

    def test_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass and NO class attributes, pipeline should use custom
        settings.
        """

        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        prefix = UserDefinedFilesPipeline.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, settings)
        )
        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_cls_settings[pipe_attr]
            assert getattr(user_pipeline, pipe_inst_attr) == custom_value

    def test_custom_settings_and_class_attrs_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass AND class attributes
        setting keys are preferred and override attributes.
        """
        pipeline_cls = self._generate_fake_pipeline()
        prefix = pipeline_cls.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for (
            pipe_cls_attr,
            settings_attr,
            pipe_inst_attr,
        ) in self.file_cls_attr_settings_map:
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_cls_settings[pipe_cls_attr]
            assert getattr(user_pipeline, pipe_inst_attr) == custom_value

    def test_cls_attrs_with_DEFAULT_prefix(self, tmp_path):
        class UserDefinedFilesPipeline(FilesPipeline):
            DEFAULT_FILES_RESULT_FIELD = "this"
            DEFAULT_FILES_URLS_FIELD = "that"

        pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        assert (
            pipeline.files_result_field
            == UserDefinedFilesPipeline.DEFAULT_FILES_RESULT_FIELD
        )
        assert (
            pipeline.files_urls_field
            == UserDefinedFilesPipeline.DEFAULT_FILES_URLS_FIELD
        )

    def test_user_defined_subclass_default_key_names(self, tmp_path):
        """Test situation when user defines subclass of FilesPipeline,
        but uses attribute names for default pipeline (without prefixing
        them with pipeline class name).
        """
        settings = self._generate_fake_settings(tmp_path)

        class UserPipe(FilesPipeline):
            pass

        pipeline_cls = UserPipe.from_crawler(get_crawler(None, settings))

        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            expected_value = settings.get(settings_attr)
            assert getattr(pipeline_cls, pipe_inst_attr) == expected_value

    def test_file_pipeline_using_pathlike_objects(self, tmp_path):
        class CustomFilesPipelineWithPathLikeDir(FilesPipeline):
            def file_path(self, request, response=None, info=None, *, item=None):
                return Path("subdir") / Path(request.url).name

        pipeline = CustomFilesPipelineWithPathLikeDir.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        request = Request("http://example.com/image01.jpg")
        assert pipeline.file_path(request) == Path("subdir/image01.jpg")

    def test_files_store_constructor_with_pathlike_object(self, tmp_path):
        fs_store = FSFilesStore(tmp_path)
        assert fs_store.basedir == str(tmp_path)


@pytest.mark.requires_botocore
class TestS3FilesStore:
    @inlineCallbacks
    def test_persist(self):
        bucket = "mybucket"
        key = "export.csv"
        uri = f"s3://{bucket}/{key}"
        buffer = mock.MagicMock()
        meta = {"foo": "bar"}
        path = ""
        content_type = "image/png"

        store = S3FilesStore(uri)
        from botocore.stub import Stubber  # noqa: PLC0415

        with Stubber(store.s3_client) as stub:
            stub.add_response(
                "put_object",
                expected_params={
                    "ACL": S3FilesStore.POLICY,
                    "Body": buffer,
                    "Bucket": bucket,
                    "CacheControl": S3FilesStore.HEADERS["Cache-Control"],
                    "ContentType": content_type,
                    "Key": key,
                    "Metadata": meta,
                },
                service_response={},
            )

            yield store.persist_file(
                path,
                buffer,
                info=None,
                meta=meta,
                headers={"Content-Type": content_type},
            )

            stub.assert_no_pending_responses()
            # The call to read does not happen with Stubber
            assert buffer.method_calls == [mock.call.seek(0)]

    @inlineCallbacks
    def test_stat(self):
        bucket = "mybucket"
        key = "export.csv"
        uri = f"s3://{bucket}/{key}"
        checksum = "3187896a9657a28163abb31667df64c8"
        last_modified = datetime(2019, 12, 1)

        store = S3FilesStore(uri)
        from botocore.stub import Stubber  # noqa: PLC0415

        with Stubber(store.s3_client) as stub:
            stub.add_response(
                "head_object",
                expected_params={
                    "Bucket": bucket,
                    "Key": key,
                },
                service_response={
                    "ETag": f'"{checksum}"',
                    "LastModified": last_modified,
                },
            )

            file_stats = yield store.stat_file("", info=None)
            assert file_stats == {
                "checksum": checksum,
                "last_modified": last_modified.timestamp(),
            }

            stub.assert_no_pending_responses()


@pytest.mark.skipif(
    "GCS_PROJECT_ID" not in os.environ, reason="GCS_PROJECT_ID not found"
)
class TestGCSFilesStore:
    @inlineCallbacks
    def test_persist(self):
        uri = os.environ.get("GCS_TEST_FILE_URI")
        if not uri:
            pytest.skip("No GCS URI available for testing")
        data = b"TestGCSFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {"foo": "bar"}
        path = "full/filename"
        store = GCSFilesStore(uri)
        store.POLICY = "authenticatedRead"
        expected_policy = {"role": "READER", "entity": "allAuthenticatedUsers"}
        yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
        s = yield store.stat_file(path, info=None)
        assert "last_modified" in s
        assert "checksum" in s
        assert s["checksum"] == "cdcda85605e46d0af6110752770dce3c"
        u = urlparse(uri)
        content, acl, blob = get_gcs_content_and_delete(u.hostname, u.path[1:] + path)
        assert content == data
        assert blob.metadata == {"foo": "bar"}
        assert blob.cache_control == GCSFilesStore.CACHE_CONTROL
        assert blob.content_type == "application/octet-stream"
        assert expected_policy in acl

    @inlineCallbacks
    def test_blob_path_consistency(self):
        """Test to make sure that paths used to store files is the same as the one used to get
        already uploaded files.
        """
        try:
            import google.cloud.storage  # noqa: F401,PLC0415
        except ModuleNotFoundError:
            pytest.skip("google-cloud-storage is not installed")
        with (
            mock.patch("google.cloud.storage"),
            mock.patch("scrapy.pipelines.files.time"),
        ):
            uri = "gs://my_bucket/my_prefix/"
            store = GCSFilesStore(uri)
            store.bucket = mock.Mock()
            path = "full/my_data.txt"
            yield store.persist_file(
                path, mock.Mock(), info=None, meta=None, headers=None
            )
            yield store.stat_file(path, info=None)
            expected_blob_path = store.prefix + path
            store.bucket.blob.assert_called_with(expected_blob_path)
            store.bucket.get_blob.assert_called_with(expected_blob_path)


@pytest.mark.requires_reactor  # needs a reactor for FTPFilesStore
class TestFTPFileStore:
    @inlineCallbacks
    def test_persist(self):
        data = b"TestFTPFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {"foo": "bar"}
        path = "full/filename"
        with MockFTPServer() as ftp_server:
            store = FTPFilesStore(ftp_server.url("/"))
            empty_dict = yield store.stat_file(path, info=None)
            assert empty_dict == {}
            yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
            stat = yield store.stat_file(path, info=None)
            assert "last_modified" in stat
            assert "checksum" in stat
            assert stat["checksum"] == "d113d66b2ec7258724a268bd88eef6b6"
            path = f"{store.basedir}/{path}"
            content = get_ftp_content_and_delete(
                path,
                store.host,
                store.port,
                store.username,
                store.password,
                store.USE_ACTIVE_MODE,
            )
        assert data == content


class ItemWithFiles(Item):
    file_urls = Field()
    files = Field()


def _create_item_with_files(*files):
    item = ItemWithFiles()
    item["file_urls"] = files
    return item


def _prepare_request_object(item_url, flags=None):
    return Request(
        item_url,
        meta={"response": Response(item_url, status=200, body=b"data", flags=flags)},
    )


# this is separate from the one in test_pipeline_media.py to specifically test FilesPipeline subclasses
class TestBuildFromCrawler:
    def setup_method(self):
        self.tempdir = mkdtemp()
        self.crawler = get_crawler(None, {"FILES_STORE": self.tempdir})

    def teardown_method(self):
        rmtree(self.tempdir)

    def test_simple(self):
        class Pipeline(FilesPipeline):
            pass

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe.store

    def test_has_from_crawler_and_init(self):
        class Pipeline(FilesPipeline):
            _from_crawler_called = False

            @classmethod
            def from_crawler(cls, crawler):
                settings = crawler.settings
                store_uri = settings["FILES_STORE"]
                o = cls(store_uri, crawler=crawler)
                o._from_crawler_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe.store
            assert pipe._from_crawler_called


@pytest.mark.parametrize("store", [None, ""])
def test_files_pipeline_raises_notconfigured_when_files_store_invalid(store):
    settings = Settings()
    settings.clear()
    settings.set("FILES_STORE", store, priority="cmdline")
    crawler = get_crawler(settings_dict=settings)

    with pytest.raises(NotConfigured):
        FilesPipeline.from_crawler(crawler)

```

```python
import dataclasses
import os
import random
import time
import warnings
from abc import ABC, abstractmethod
from datetime import datetime
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from posixpath import split
from shutil import rmtree
from tempfile import mkdtemp
from typing import Any
from unittest import mock
from unittest.mock import MagicMock
from urllib.parse import urlparse

import attr
import pytest
from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred

from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.pipelines.files import (
    FilesPipeline,
    FSFilesStore,
    FTPFilesStore,
    GCSFilesStore,
    S3FilesStore,
)
from scrapy.settings import Settings
from scrapy.utils.defer import _defer_sleep_async, deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.mockserver.ftp import MockFTPServer
from tests.utils.decorators import deferred_f_from_coro_f, inlineCallbacks

from .test_pipeline_media import _mocked_download_func


def get_gcs_content_and_delete(
    bucket: Any, path: str
) -> tuple[bytes, list[dict[str, str]], Any]:
    from google.cloud import storage  # noqa: PLC0415

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


class TestFilesPipeline:
    def setup_method(self):
        self.tempdir = mkdtemp()
        settings_dict = {"FILES_STORE": self.tempdir}
        crawler = get_crawler(DefaultSpider, settings_dict=settings_dict)
        crawler.spider = crawler._create_spider()
        crawler.engine = MagicMock(download_async=_mocked_download_func)
        self.pipeline = FilesPipeline.from_crawler(crawler)
        self.pipeline.open_spider()

    def teardown_method(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        assert (
            file_path(Request("https://dev.mydeco.com/mydeco.pdf"))
            == "full/c9b564df929f4bc635bdd19fde4f3d4847c757c5.pdf"
        )
        assert (
            file_path(
                Request(
                    "http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.txt"
                )
            )
            == "full/4ce274dd83db0368bafd7e406f382ae088e39219.txt"
        )
        assert (
            file_path(
                Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.doc")
            )
            == "full/94ccc495a17b9ac5d40e3eabf3afcb8c2c9b9e1a.doc"
        )
        assert (
            file_path(
                Request(
                    "http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg"
                )
            )
            == "full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532/"))
            == "full/97ee6f8a46cbbb418ea91502fd24176865cf39b2"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532"))
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1"
        )
        assert (
            file_path(
                Request("http://www.dorma.co.uk/images/product_details/2532"),
                response=Response("http://www.dorma.co.uk/images/product_details/2532"),
                info=object(),
            )
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1"
        )
        assert (
            file_path(
                Request(
                    "http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg.bohaha"
                )
            )
            == "full/76c00cef2ef669ae65052661f68d451162829507"
        )
        assert (
            file_path(
                Request(
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAR0AAACxCAMAAADOHZloAAACClBMVEX/\
                                    //+F0tzCwMK76ZKQ21AMqr7oAAC96JvD5aWM2kvZ78J0N7fmAAC46Y4Ap7y"
                )
            )
            == "full/178059cbeba2e34120a67f2dc1afc3ecc09b61cb.png"
        )

    def test_fs_store(self):
        assert isinstance(self.pipeline.store, FSFilesStore)
        assert self.pipeline.store.basedir == self.tempdir

        path = "some/image/key.jpg"
        fullpath = Path(self.tempdir, "some", "image", "key.jpg")
        assert self.pipeline.store._get_filesystem_path(path) == fullpath

    @deferred_f_from_coro_f
    async def test_persist_file_is_awaited(self):
        item_url = "http://example.com/file.pdf"
        item = _create_item_with_files(item_url)
        persist_dfd = Deferred()
        persist_calls: list[str] = []

        def _persist_file(path, buf, info, meta=None, headers=None):
            persist_calls.append(path)
            return persist_dfd

        self.pipeline.store.persist_file = _persist_file  # type: ignore[method-assign]

        with mock.patch.object(
            FilesPipeline,
            "get_media_requests",
            return_value=[_prepare_request_object(item_url)],
        ):
            item_dfd = deferred_from_coro(self.pipeline.process_item(item))
            for _ in range(3):
                await _defer_sleep_async()
                if persist_calls:
                    break
            assert persist_calls
            assert not item_dfd.called

            persist_dfd.callback(None)
            result = await maybe_deferred_to_future(item_dfd)

        assert result["files"][0]["status"] == "downloaded"

    @deferred_f_from_coro_f
    async def test_file_not_expired(self):
        item_url = "http://example.com/file.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={"checksum": "abc", "last_modified": time.time()},
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url)],
            ),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] == "abc"
        assert result["files"][0]["status"] == "uptodate"

        for p in patchers:
            p.stop()

    @deferred_f_from_coro_f
    async def test_file_expired(self):
        item_url = "http://example.com/file2.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={
                    "checksum": "abc",
                    "last_modified": time.time()
                    - (self.pipeline.expires * 60 * 60 * 24 * 2),
                },
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url)],
            ),
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] != "abc"
        assert result["files"][0]["status"] == "downloaded"

        for p in patchers:
            p.stop()

    @deferred_f_from_coro_f
    async def test_file_cached(self):
        item_url = "http://example.com/file3.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, "inc_stats", return_value=True),
            mock.patch.object(
                FSFilesStore,
                "stat_file",
                return_value={
                    "checksum": "abc",
                    "last_modified": time.time()
                    - (self.pipeline.expires * 60 * 60 * 24 * 2),
                },
            ),
            mock.patch.object(
                FilesPipeline,
                "get_media_requests",
                return_value=[_prepare_request_object(item_url, flags=["cached"])],
            ),
        ]
        for p in patchers:
            p.start()

        result = await self.pipeline.process_item(item)
        assert result["files"][0]["checksum"] != "abc"
        assert result["files"][0]["status"] == "cached"

        for p in patchers:
            p.stop()

    def test_file_path_from_item(self):
        """
        Custom file path based on item data, overriding default implementation
        """

        class CustomFilesPipeline(FilesPipeline):
            def file_path(self, request, response=None, info=None, item=None):
                return f"full/{item.get('path')}"

        file_path = CustomFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": self.tempdir})
        ).file_path
        item = {"path": "path-to-store-file"}
        request = Request("http://example.com")
        assert file_path(request, item=item) == "full/path-to-store-file"

    @pytest.mark.parametrize(
        "bad_type",
        [
            "http://example.com/file.pdf",
            ("http://example.com/file.pdf",),
            {"url": "http://example.com/file.pdf"},
            123,
            None,
        ],
    )
    def test_rejects_non_list_file_urls(self, tmp_path, bad_type):
        pipeline = FilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": str(tmp_path)})
        )
        item = ItemWithFiles()
        item["file_urls"] = bad_type

        with pytest.raises(TypeError, match="file_urls must be a list of URLs"):
            list(pipeline.get_media_requests(item, None))


class TestFilesPipelineFieldsMixin(ABC):
    @property
    @abstractmethod
    def item_class(self) -> Any:
        raise NotImplementedError

    def test_item_fields_default(self, tmp_path):
        url = "http://www.example.com/files/1.txt"
        item = self.item_class(name="item1", file_urls=[url])
        pipeline = FilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        files = ItemAdapter(item).get("files")
        assert files == [results[0][1]]
        assert isinstance(item, self.item_class)

    def test_item_fields_override_settings(self, tmp_path):
        url = "http://www.example.com/files/1.txt"
        item = self.item_class(name="item1", custom_file_urls=[url])
        pipeline = FilesPipeline.from_crawler(
            get_crawler(
                None,
                {
                    "FILES_STORE": tmp_path,
                    "FILES_URLS_FIELD": "custom_file_urls",
                    "FILES_RESULT_FIELD": "custom_files",
                },
            )
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        custom_files = ItemAdapter(item).get("custom_files")
        assert custom_files == [results[0][1]]
        assert isinstance(item, self.item_class)


class TestFilesPipelineFieldsDict(TestFilesPipelineFieldsMixin):
    item_class = dict


class FilesPipelineTestItem(Item):
    name = Field()
    # default fields
    file_urls = Field()
    files = Field()
    # overridden fields
    custom_file_urls = Field()
    custom_files = Field()


class TestFilesPipelineFieldsItem(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestItem


@dataclasses.dataclass
class FilesPipelineTestDataClass:
    name: str
    # default fields
    file_urls: list = dataclasses.field(default_factory=list)
    files: list = dataclasses.field(default_factory=list)
    # overridden fields
    custom_file_urls: list = dataclasses.field(default_factory=list)
    custom_files: list = dataclasses.field(default_factory=list)


class TestFilesPipelineFieldsDataClass(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestDataClass


@attr.s
class FilesPipelineTestAttrsItem:
    name = attr.ib(default="")
    # default fields
    file_urls: list[str] = attr.ib(default=list)
    files: list[dict[str, str]] = attr.ib(default=list)
    # overridden fields
    custom_file_urls: list[str] = attr.ib(default=list)
    custom_files: list[dict[str, str]] = attr.ib(default=list)


class TestFilesPipelineFieldsAttrsItem(TestFilesPipelineFieldsMixin):
    item_class = FilesPipelineTestAttrsItem


class TestFilesPipelineCustomSettings:
    default_cls_settings = {
        "EXPIRES": 90,
        "FILES_URLS_FIELD": "file_urls",
        "FILES_RESULT_FIELD": "files",
    }
    file_cls_attr_settings_map = {
        ("EXPIRES", "FILES_EXPIRES", "expires"),
        ("FILES_URLS_FIELD", "FILES_URLS_FIELD", "files_urls_field"),
        ("FILES_RESULT_FIELD", "FILES_RESULT_FIELD", "files_result_field"),
    }

    def _generate_fake_settings(self, tmp_path, prefix=None):
        def random_string():
            return "".join([chr(random.randint(97, 123)) for _ in range(10)])

        settings = {
            "FILES_EXPIRES": random.randint(100, 1000),
            "FILES_URLS_FIELD": random_string(),
            "FILES_RESULT_FIELD": random_string(),
            "FILES_STORE": tmp_path,
        }
        if not prefix:
            return settings

        return {
            prefix.upper() + "_" + k if k != "FILES_STORE" else k: v
            for k, v in settings.items()
        }

    def _generate_fake_pipeline(self):
        class UserDefinedFilePipeline(FilesPipeline):
            EXPIRES = 1001
            FILES_URLS_FIELD = "alfa"
            FILES_RESULT_FIELD = "beta"

        return UserDefinedFilePipeline

    def test_different_settings_for_different_instances(self, tmp_path):
        """
        If there are different instances with different settings they should keep
        different settings.
        """
        custom_settings = self._generate_fake_settings(tmp_path)
        another_pipeline = FilesPipeline.from_crawler(
            get_crawler(None, custom_settings)
        )
        one_pipeline = FilesPipeline(tmp_path, crawler=get_crawler(None))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            default_value = self.default_cls_settings[pipe_attr]
            assert getattr(one_pipeline, pipe_attr) == default_value
            custom_value = custom_settings[settings_attr]
            assert default_value != custom_value
            assert getattr(another_pipeline, pipe_ins_attr) == custom_value

    def test_subclass_attributes_preserved_if_no_settings(self, tmp_path):
        """
        If subclasses override class attributes and there are no special settings those values should be kept.
        """
        pipe_cls = self._generate_fake_pipeline()
        pipe = pipe_cls.from_crawler(get_crawler(None, {"FILES_STORE": tmp_path}))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            custom_value = getattr(pipe, pipe_ins_attr)
            assert custom_value != self.default_cls_settings[pipe_attr]
            assert getattr(pipe, pipe_ins_attr) == getattr(pipe, pipe_attr)

    def test_subclass_attrs_preserved_custom_settings(self, tmp_path):
        """
        If file settings are defined but they are not defined for subclass
        settings should be preserved.
        """
        pipeline_cls = self._generate_fake_pipeline()
        settings = self._generate_fake_settings(tmp_path)
        pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            value = getattr(pipeline, pipe_ins_attr)
            setting_value = settings.get(settings_attr)
            assert value != self.default_cls_settings[pipe_attr]
            assert value == setting_value

    def test_no_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are no settings for subclass and no subclass attributes, pipeline should use
        attributes of base class.
        """

        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        user_pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        for pipe_attr, settings_attr, pipe_ins_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = self.default_cls_settings.get(pipe_attr.upper())
            assert getattr(user_pipeline, pipe_ins_attr) == custom_value

    def test_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass and NO class attributes, pipeline should use custom
        settings.
        """

        class UserDefinedFilesPipeline(FilesPipeline):
            pass

        prefix = UserDefinedFilesPipeline.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, settings)
        )
        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_cls_settings[pipe_attr]
            assert getattr(user_pipeline, pipe_inst_attr) == custom_value

    def test_custom_settings_and_class_attrs_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass AND class attributes
        setting keys are preferred and override attributes.
        """
        pipeline_cls = self._generate_fake_pipeline()
        prefix = pipeline_cls.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for (
            pipe_cls_attr,
            settings_attr,
            pipe_inst_attr,
        ) in self.file_cls_attr_settings_map:
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_cls_settings[pipe_cls_attr]
            assert getattr(user_pipeline, pipe_inst_attr) == custom_value

    def test_cls_attrs_with_DEFAULT_prefix(self, tmp_path):
        class UserDefinedFilesPipeline(FilesPipeline):
            DEFAULT_FILES_RESULT_FIELD = "this"
            DEFAULT_FILES_URLS_FIELD = "that"

        pipeline = UserDefinedFilesPipeline.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        assert (
            pipeline.files_result_field
            == UserDefinedFilesPipeline.DEFAULT_FILES_RESULT_FIELD
        )
        assert (
            pipeline.files_urls_field
            == UserDefinedFilesPipeline.DEFAULT_FILES_URLS_FIELD
        )

    def test_user_defined_subclass_default_key_names(self, tmp_path):
        """Test situation when user defines subclass of FilesPipeline,
        but uses attribute names for default pipeline (without prefixing
        them with pipeline class name).
        """
        settings = self._generate_fake_settings(tmp_path)

        class UserPipe(FilesPipeline):
            pass

        pipeline_cls = UserPipe.from_crawler(get_crawler(None, settings))

        for pipe_attr, settings_attr, pipe_inst_attr in self.file_cls_attr_settings_map:
            expected_value = settings.get(settings_attr)
            assert getattr(pipeline_cls, pipe_inst_attr) == expected_value

    def test_file_pipeline_using_pathlike_objects(self, tmp_path):
        class CustomFilesPipelineWithPathLikeDir(FilesPipeline):
            def file_path(self, request, response=None, info=None, *, item=None):
                return Path("subdir") / Path(request.url).name

        pipeline = CustomFilesPipelineWithPathLikeDir.from_crawler(
            get_crawler(None, {"FILES_STORE": tmp_path})
        )
        request = Request("http://example.com/image01.jpg")
        assert pipeline.file_path(request) == Path("subdir/image01.jpg")

    def test_files_store_constructor_with_pathlike_object(self, tmp_path):
        fs_store = FSFilesStore(tmp_path)
        assert fs_store.basedir == str(tmp_path)


@pytest.mark.requires_botocore
class TestS3FilesStore:
    @inlineCallbacks
    def test_persist(self):
        bucket = "mybucket"
        key = "export.csv"
        uri = f"s3://{bucket}/{key}"
        buffer = mock.MagicMock()
        meta = {"foo": "bar"}
        path = ""
        content_type = "image/png"

        store = S3FilesStore(uri)
        from botocore.stub import Stubber  # noqa: PLC0415

        with Stubber(store.s3_client) as stub:
            stub.add_response(
                "put_object",
                expected_params={
                    "ACL": S3FilesStore.POLICY,
                    "Body": buffer,
                    "Bucket": bucket,
                    "CacheControl": S3FilesStore.HEADERS["Cache-Control"],
                    "ContentType": content_type,
                    "Key": key,
                    "Metadata": meta,
                },
                service_response={},
            )

            yield store.persist_file(
                path,
                buffer,
                info=None,
                meta=meta,
                headers={"Content-Type": content_type},
            )

            stub.assert_no_pending_responses()
            # The call to read does not happen with Stubber
            assert buffer.method_calls == [mock.call.seek(0)]

    @inlineCallbacks
    def test_stat(self):
        bucket = "mybucket"
        key = "export.csv"
        uri = f"s3://{bucket}/{key}"
        checksum = "3187896a9657a28163abb31667df64c8"
        last_modified = datetime(2019, 12, 1)

        store = S3FilesStore(uri)
        from botocore.stub import Stubber  # noqa: PLC0415

        with Stubber(store.s3_client) as stub:
            stub.add_response(
                "head_object",
                expected_params={
                    "Bucket": bucket,
                    "Key": key,
                },
                service_response={
                    "ETag": f'"{checksum}"',
                    "LastModified": last_modified,
                },
            )

            file_stats = yield store.stat_file("", info=None)
            assert file_stats == {
                "checksum": checksum,
                "last_modified": last_modified.timestamp(),
            }

            stub.assert_no_pending_responses()


@pytest.mark.skipif(
    "GCS_PROJECT_ID" not in os.environ, reason="GCS_PROJECT_ID not found"
)
class TestGCSFilesStore:
    @inlineCallbacks
    def test_persist(self):
        uri = os.environ.get("GCS_TEST_FILE_URI")
        if not uri:
            pytest.skip("No GCS URI available for testing")
        data = b"TestGCSFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {"foo": "bar"}
        path = "full/filename"
        store = GCSFilesStore(uri)
        store.POLICY = "authenticatedRead"
        expected_policy = {"role": "READER", "entity": "allAuthenticatedUsers"}
        yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
        s = yield store.stat_file(path, info=None)
        assert "last_modified" in s
        assert "checksum" in s
        assert s["checksum"] == "cdcda85605e46d0af6110752770dce3c"
        u = urlparse(uri)
        content, acl, blob = get_gcs_content_and_delete(u.hostname, u.path[1:] + path)
        assert content == data
        assert blob.metadata == {"foo": "bar"}
        assert blob.cache_control == GCSFilesStore.CACHE_CONTROL
        assert blob.content_type == "application/octet-stream"
        assert expected_policy in acl

    @inlineCallbacks
    def test_blob_path_consistency(self):
        """Test to make sure that paths used to store files is the same as the one used to get
        already uploaded files.
        """
        try:
            import google.cloud.storage  # noqa: F401,PLC0415
        except ModuleNotFoundError:
            pytest.skip("google-cloud-storage is not installed")
        with (
            mock.patch("google.cloud.storage"),
            mock.patch("scrapy.pipelines.files.time"),
        ):
            uri = "gs://my_bucket/my_prefix/"
            store = GCSFilesStore(uri)
            store.bucket = mock.Mock()
            path = "full/my_data.txt"
            yield store.persist_file(
                path, mock.Mock(), info=None, meta=None, headers=None
            )
            yield store.stat_file(path, info=None)
            expected_blob_path = store.prefix + path
            store.bucket.blob.assert_called_with(expected_blob_path)
            store.bucket.get_blob.assert_called_with(expected_blob_path)


@pytest.mark.requires_reactor  # needs a reactor for FTPFilesStore
class TestFTPFileStore:
    @inlineCallbacks
    def test_persist(self):
        data = b"TestFTPFilesStore: \xe2\x98\x83"
        buf = BytesIO(data)
        meta = {"foo": "bar"}
        path = "full/filename"
        with MockFTPServer() as ftp_server:
            store = FTPFilesStore(ftp_server.url("/"))
            empty_dict = yield store.stat_file(path, info=None)
            assert empty_dict == {}
            yield store.persist_file(path, buf, info=None, meta=meta, headers=None)
            stat = yield store.stat_file(path, info=None)
            assert "last_modified" in stat
            assert "checksum" in stat
            assert stat["checksum"] == "d113d66b2ec7258724a268bd88eef6b6"
            path = f"{store.basedir}/{path}"
            content = get_ftp_content_and_delete(
                path,
                store.host,
                store.port,
                store.username,
                store.password,
                store.USE_ACTIVE_MODE,
            )
        assert data == content


class ItemWithFiles(Item):
    file_urls = Field()
    files = Field()


def _create_item_with_files(*files):
    item = ItemWithFiles()
    item["file_urls"] = files
    return item


def _prepare_request_object(item_url, flags=None):
    return Request(
        item_url,
        meta={"response": Response(item_url, status=200, body=b"data", flags=flags)},
    )


# this is separate from the one in test_pipeline_media.py to specifically test FilesPipeline subclasses
class TestBuildFromCrawler:
    def setup_method(self):
        self.tempdir = mkdtemp()
        self.crawler = get_crawler(None, {"FILES_STORE": self.tempdir})

    def teardown_method(self):
        rmtree(self.tempdir)

    def test_simple(self):
        class Pipeline(FilesPipeline):
            pass

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe.store

    def test_has_from_crawler_and_init(self):
        class Pipeline(FilesPipeline):
            _from_crawler_called = False

            @classmethod
            def from_crawler(cls, crawler):
                settings = crawler.settings
                store_uri = settings["FILES_STORE"]
                o = cls(store_uri, crawler=crawler)
                o._from_crawler_called = True
                return o

        with warnings.catch_warnings(record=True) as w:
            pipe = Pipeline.from_crawler(self.crawler)
            assert pipe.crawler == self.crawler
            assert pipe._fingerprinter
            assert len(w) == 0
            assert pipe.store
            assert pipe._from_crawler_called


@pytest.mark.parametrize("store", [None, ""])
def test_files_pipeline_raises_notconfigured_when_files_store_invalid(store):
    settings = Settings()
    settings.clear()
    settings.set("FILES_STORE", store, priority="cmdline")
    crawler = get_crawler(settings_dict=settings)

    with pytest.raises(NotConfigured):
        FilesPipeline.from_crawler(crawler)

```

```python
"""
Files Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import mimetypes
import time
import warnings
from collections import defaultdict
from contextlib import suppress
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, NoReturn, Protocol, TypedDict, cast
from urllib.parse import urlparse

from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.threads import deferToThread

from scrapy.exceptions import IgnoreRequest, NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.media import FileInfo, FileInfoOrError, MediaPipeline
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.datatypes import CaseInsensitiveDict
from scrapy.utils.defer import deferred_from_coro, ensure_awaitable
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import to_bytes
from scrapy.utils.request import referer_str

if TYPE_CHECKING:
    from os import PathLike

    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


def _to_string(path: str | PathLike[str]) -> str:
    return str(path)  # convert a Path object to string


def _md5sum(file: IO[bytes]) -> str:
    """Calculate the md5 checksum of a file-like object without reading its
    whole content in memory.

    >>> from io import BytesIO
    >>> _md5sum(BytesIO(b'file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'
    """
    m = hashlib.md5()  # noqa: S324
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


class FileException(Exception):
    """General media error exception"""


class StatInfo(TypedDict, total=False):
    checksum: str
    last_modified: float


class FilesStoreProtocol(Protocol):
    def __init__(self, basedir: str): ...

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any] | None: ...

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> StatInfo | Deferred[StatInfo]: ...


class FSFilesStore:
    def __init__(self, basedir: str | PathLike[str]):
        basedir = _to_string(basedir)
        if "://" in basedir:
            basedir = basedir.split("://", 1)[1]
        self.basedir: str = basedir
        self._mkdir(Path(self.basedir))
        self.created_directories: defaultdict[MediaPipeline.SpiderInfo, set[str]] = (
            defaultdict(set)
        )

    def persist_file(
        self,
        path: str | PathLike[str],
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        absolute_path = self._get_filesystem_path(path)
        self._mkdir(absolute_path.parent, info)
        absolute_path.write_bytes(buf.getvalue())

    def stat_file(
        self, path: str | PathLike[str], info: MediaPipeline.SpiderInfo
    ) -> StatInfo:
        absolute_path = self._get_filesystem_path(path)
        try:
            last_modified = absolute_path.stat().st_mtime
        except OSError:
            return {}

        with absolute_path.open("rb") as f:
            checksum = _md5sum(f)

        return {"last_modified": last_modified, "checksum": checksum}

    def _get_filesystem_path(self, path: str | PathLike[str]) -> Path:
        path_comps = _to_string(path).split("/")
        return Path(self.basedir, *path_comps)

    def _mkdir(
        self, dirname: Path, domain: MediaPipeline.SpiderInfo | None = None
    ) -> None:
        seen: set[str] = self.created_directories[domain] if domain else set()
        if str(dirname) not in seen:
            if not dirname.exists():
                dirname.mkdir(parents=True)
            seen.add(str(dirname))


class S3FilesStore:
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_SESSION_TOKEN = None
    AWS_ENDPOINT_URL = None
    AWS_REGION_NAME = None
    AWS_USE_SSL = None
    AWS_VERIFY = None

    POLICY = "private"  # Overridden from settings.FILES_STORE_S3_ACL in FilesPipeline.from_crawler()
    HEADERS = {
        "Cache-Control": "max-age=172800",
    }

    def __init__(self, uri: str):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")
        import botocore.session  # noqa: PLC0415

        session = botocore.session.get_session()
        self.s3_client = session.create_client(
            "s3",
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            aws_session_token=self.AWS_SESSION_TOKEN,
            endpoint_url=self.AWS_ENDPOINT_URL,
            region_name=self.AWS_REGION_NAME,
            use_ssl=self.AWS_USE_SSL,
            verify=self.AWS_VERIFY,
        )
        if not uri.startswith("s3://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 's3'")
        self.bucket, self.prefix = uri[5:].split("/", 1)

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(boto_key: dict[str, Any]) -> StatInfo:
            checksum = boto_key["ETag"].strip('"')
            last_modified = boto_key["LastModified"]
            modified_stamp = time.mktime(last_modified.timetuple())
            return {"checksum": checksum, "last_modified": modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_key(self, path: str) -> Deferred[dict[str, Any]]:
        key_name = f"{self.prefix}{path}"
        return cast(
            "Deferred[dict[str, Any]]",
            deferToThread(
                self.s3_client.head_object,  # type: ignore[attr-defined]
                Bucket=self.bucket,
                Key=key_name,
            ),
        )

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        """Upload file to S3 storage"""
        key_name = f"{self.prefix}{path}"
        buf.seek(0)
        extra = self._headers_to_botocore_kwargs(self.HEADERS)
        if headers:
            extra.update(self._headers_to_botocore_kwargs(headers))
        return deferToThread(
            self.s3_client.put_object,  # type: ignore[attr-defined]
            Bucket=self.bucket,
            Key=key_name,
            Body=buf,
            Metadata={k: str(v) for k, v in (meta or {}).items()},
            ACL=self.POLICY,
            **extra,
        )

    def _headers_to_botocore_kwargs(self, headers: dict[str, Any]) -> dict[str, Any]:
        """Convert headers to botocore keyword arguments."""
        # This is required while we need to support both boto and botocore.
        mapping = CaseInsensitiveDict(
            {
                "Content-Type": "ContentType",
                "Cache-Control": "CacheControl",
                "Content-Disposition": "ContentDisposition",
                "Content-Encoding": "ContentEncoding",
                "Content-Language": "ContentLanguage",
                "Content-Length": "ContentLength",
                "Content-MD5": "ContentMD5",
                "Expires": "Expires",
                "X-Amz-Grant-Full-Control": "GrantFullControl",
                "X-Amz-Grant-Read": "GrantRead",
                "X-Amz-Grant-Read-ACP": "GrantReadACP",
                "X-Amz-Grant-Write-ACP": "GrantWriteACP",
                "X-Amz-Object-Lock-Legal-Hold": "ObjectLockLegalHoldStatus",
                "X-Amz-Object-Lock-Mode": "ObjectLockMode",
                "X-Amz-Object-Lock-Retain-Until-Date": "ObjectLockRetainUntilDate",
                "X-Amz-Request-Payer": "RequestPayer",
                "X-Amz-Server-Side-Encryption": "ServerSideEncryption",
                "X-Amz-Server-Side-Encryption-Aws-Kms-Key-Id": "SSEKMSKeyId",
                "X-Amz-Server-Side-Encryption-Context": "SSEKMSEncryptionContext",
                "X-Amz-Server-Side-Encryption-Customer-Algorithm": "SSECustomerAlgorithm",
                "X-Amz-Server-Side-Encryption-Customer-Key": "SSECustomerKey",
                "X-Amz-Server-Side-Encryption-Customer-Key-Md5": "SSECustomerKeyMD5",
                "X-Amz-Storage-Class": "StorageClass",
                "X-Amz-Tagging": "Tagging",
                "X-Amz-Website-Redirect-Location": "WebsiteRedirectLocation",
            }
        )
        extra: dict[str, Any] = {}
        for key, value in headers.items():
            try:
                kwarg = mapping[key]
            except KeyError:
                raise TypeError(f'Header "{key}" is not supported by botocore')
            extra[kwarg] = value
        return extra


class GCSFilesStore:
    GCS_PROJECT_ID = None

    CACHE_CONTROL = "max-age=172800"

    # The bucket's default object ACL will be applied to the object.
    # Overridden from settings.FILES_STORE_GCS_ACL in FilesPipeline.from_crawler().
    POLICY = None

    def __init__(self, uri: str):
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client(project=self.GCS_PROJECT_ID)
        bucket, prefix = uri[5:].split("/", 1)
        self.bucket = client.bucket(bucket)
        self.prefix: str = prefix
        permissions = self.bucket.test_iam_permissions(
            ["storage.objects.get", "storage.objects.create"]
        )
        if "storage.objects.get" not in permissions:
            logger.warning(
                "No 'storage.objects.get' permission for GSC bucket %(bucket)s. "
                "Checking if files are up to date will be impossible. Files will be downloaded every time.",
                {"bucket": bucket},
            )
        if "storage.objects.create" not in permissions:
            logger.error(
                "No 'storage.objects.create' permission for GSC bucket %(bucket)s. Saving files will be impossible!",
                {"bucket": bucket},
            )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _onsuccess(blob) -> StatInfo:
            if blob:
                checksum = base64.b64decode(blob.md5_hash).hex()
                last_modified = time.mktime(blob.updated.timetuple())
                return {"checksum": checksum, "last_modified": last_modified}
            return {}

        blob_path = self._get_blob_path(path)
        return cast(
            "Deferred[StatInfo]",
            deferToThread(self.bucket.get_blob, blob_path).addCallback(_onsuccess),
        )

    def _get_content_type(self, headers: dict[str, str] | None) -> str:
        if headers and "Content-Type" in headers:
            return headers["Content-Type"]
        return "application/octet-stream"

    def _get_blob_path(self, path: str) -> str:
        return self.prefix + path

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        blob_path = self._get_blob_path(path)
        blob = self.bucket.blob(blob_path)
        blob.cache_control = self.CACHE_CONTROL
        blob.metadata = {k: str(v) for k, v in (meta or {}).items()}
        return deferToThread(
            blob.upload_from_string,
            data=buf.getvalue(),
            content_type=self._get_content_type(headers),
            predefined_acl=self.POLICY,
        )


class FTPFilesStore:
    FTP_USERNAME: str | None = None
    FTP_PASSWORD: str | None = None
    USE_ACTIVE_MODE: bool | None = None

    def __init__(self, uri: str):
        if not uri.startswith("ftp://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 'ftp'")
        u = urlparse(uri)
        assert u.port
        assert u.hostname
        self.port: int = u.port
        self.host: str = u.hostname
        self.port = int(u.port or 21)
        assert self.FTP_USERNAME
        assert self.FTP_PASSWORD
        self.username: str = u.username or self.FTP_USERNAME
        self.password: str = u.password or self.FTP_PASSWORD
        self.basedir: str = u.path.rstrip("/")

    def persist_file(
        self,
        path: str,
        buf: BytesIO,
        info: MediaPipeline.SpiderInfo,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Deferred[Any]:
        path = f"{self.basedir}/{path}"
        return deferToThread(
            ftp_store_file,
            path=path,
            file=buf,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_active_mode=self.USE_ACTIVE_MODE,
        )

    def stat_file(
        self, path: str, info: MediaPipeline.SpiderInfo
    ) -> Deferred[StatInfo]:
        def _stat_file(path: str) -> StatInfo:
            try:
                ftp = FTP()
                ftp.connect(self.host, self.port)
                ftp.login(self.username, self.password)
                if self.USE_ACTIVE_MODE:
                    ftp.set_pasv(False)
                file_path = f"{self.basedir}/{path}"
                last_modified = float(ftp.voidcmd(f"MDTM {file_path}")[4:].strip())
                m = hashlib.md5()  # noqa: S324
                ftp.retrbinary(f"RETR {file_path}", m.update)
                return {"last_modified": last_modified, "checksum": m.hexdigest()}
            # The file doesn't exist
            except Exception:
                return {}

        return cast("Deferred[StatInfo]", deferToThread(_stat_file, path))


class FilesPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading

    This pipeline tries to minimize network transfers and file processing,
    doing stat of the files and determining if file is new, up-to-date or
    expired.

    ``new`` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    ``uptodate`` files are the ones that the pipeline processed and are still
        valid files.

    ``expired`` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME: str = "file"
    EXPIRES: int = 90
    STORE_SCHEMES: dict[str, type[FilesStoreProtocol]] = {
        "": FSFilesStore,
        "file": FSFilesStore,
        "s3": S3FilesStore,
        "gs": GCSFilesStore,
        "ftp": FTPFilesStore,
    }
    DEFAULT_FILES_URLS_FIELD: str = "file_urls"
    DEFAULT_FILES_RESULT_FIELD: str = "files"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of FilesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        if not (store_uri and (store_uri := _to_string(store_uri))):
            from scrapy.pipelines.images import ImagesPipeline  # noqa: PLC0415

            setting_name = (
                "IMAGES_STORE" if isinstance(self, ImagesPipeline) else "FILES_STORE"
            )
            raise NotConfigured(
                f"{setting_name} setting must be set to a valid path (not empty) "
                f"to enable {self.__class__.__name__}."
            )

        settings = crawler.settings
        cls_name = "FilesPipeline"
        self.store: FilesStoreProtocol = self._get_store(store_uri)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name=cls_name, settings=settings
        )
        self.expires: int = settings.getint(resolve("FILES_EXPIRES"), self.EXPIRES)
        if not hasattr(self, "FILES_URLS_FIELD"):
            self.FILES_URLS_FIELD = self.DEFAULT_FILES_URLS_FIELD
        if not hasattr(self, "FILES_RESULT_FIELD"):
            self.FILES_RESULT_FIELD = self.DEFAULT_FILES_RESULT_FIELD
        self.files_urls_field: str = settings.get(
            resolve("FILES_URLS_FIELD"), self.FILES_URLS_FIELD
        )
        self.files_result_field: str = settings.get(
            resolve("FILES_RESULT_FIELD"), self.FILES_RESULT_FIELD
        )

        super().__init__(crawler=crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["FILES_STORE"]
        return cls(store_uri, crawler=crawler)

    @classmethod
    def _update_stores(cls, settings: BaseSettings) -> None:
        s3store: type[S3FilesStore] = cast(
            "type[S3FilesStore]", cls.STORE_SCHEMES["s3"]
        )
        s3store.AWS_ACCESS_KEY_ID = settings["AWS_ACCESS_KEY_ID"]
        s3store.AWS_SECRET_ACCESS_KEY = settings["AWS_SECRET_ACCESS_KEY"]
        s3store.AWS_SESSION_TOKEN = settings["AWS_SESSION_TOKEN"]
        s3store.AWS_ENDPOINT_URL = settings["AWS_ENDPOINT_URL"]
        s3store.AWS_REGION_NAME = settings["AWS_REGION_NAME"]
        s3store.AWS_USE_SSL = settings["AWS_USE_SSL"]
        s3store.AWS_VERIFY = settings["AWS_VERIFY"]
        s3store.POLICY = settings["FILES_STORE_S3_ACL"]

        gcs_store: type[GCSFilesStore] = cast(
            "type[GCSFilesStore]", cls.STORE_SCHEMES["gs"]
        )
        gcs_store.GCS_PROJECT_ID = settings["GCS_PROJECT_ID"]
        gcs_store.POLICY = settings["FILES_STORE_GCS_ACL"] or None

        ftp_store: type[FTPFilesStore] = cast(
            "type[FTPFilesStore]", cls.STORE_SCHEMES["ftp"]
        )
        ftp_store.FTP_USERNAME = settings["FTP_USER"]
        ftp_store.FTP_PASSWORD = settings["FTP_PASSWORD"]
        ftp_store.USE_ACTIVE_MODE = settings.getbool("FEED_STORAGE_FTP_ACTIVE")

    def _get_store(self, uri: str) -> FilesStoreProtocol:
        # to support win32 paths like: C:\\some\dir
        scheme = "file" if Path(uri).is_absolute() else urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_to_download(
        self, request: Request, info: MediaPipeline.SpiderInfo, *, item: Any = None
    ) -> Deferred[FileInfo | None] | None:
        def _onsuccess(result: StatInfo) -> FileInfo | None:
            if not result:
                return None  # returning None force download

            last_modified = result.get("last_modified", None)
            if not last_modified:
                return None  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.expires:
                return None  # returning None force download

            referer = referer_str(request)
            logger.debug(
                "File (uptodate): Downloaded %(medianame)s from %(request)s "
                "referred in <%(referer)s>",
                {"medianame": self.MEDIA_NAME, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            self.inc_stats("uptodate")

            checksum = result.get("checksum", None)
            return {
                "url": request.url,
                "path": path,
                "checksum": checksum,
                "status": "uptodate",
            }

        path = self.file_path(request, info=info, item=item)
        # maybeDeferred() overloads don't seem to support a Union[_T, Deferred[_T]] return type
        dfd: Deferred[StatInfo] = maybeDeferred(self.store.stat_file, path, info)  # type: ignore[call-overload]
        dfd2: Deferred[FileInfo | None] = dfd.addCallback(_onsuccess)
        dfd2.addErrback(lambda _: None)
        dfd2.addErrback(
            lambda f: logger.error(
                self.__class__.__name__ + ".store.stat_file",
                exc_info=failure_to_exc_info(f),
                extra={"spider": info.spider},
            )
        )
        return dfd2

    def media_failed(
        self, failure: Failure, request: Request, info: MediaPipeline.SpiderInfo
    ) -> NoReturn:
        if not isinstance(failure.value, IgnoreRequest):
            referer = referer_str(request)
            logger.warning(
                "File (unknown-error): Error downloading %(medianame)s from "
                "%(request)s referred in <%(referer)s>: %(exception)s",
                {
                    "medianame": self.MEDIA_NAME,
                    "request": request,
                    "referer": referer,
                    "exception": failure.value,
                },
                extra={"spider": info.spider},
            )

        raise FileException

    async def media_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> FileInfo:
        referer = referer_str(request)

        if response.status != 200:
            logger.warning(
                "File (code: %(status)s): Error downloading file from "
                "%(request)s referred in <%(referer)s>",
                {"status": response.status, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("download-error")

        if not response.body:
            logger.warning(
                "File (empty-content): Empty file from %(request)s referred "
                "in <%(referer)s>: no-content",
                {"request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("empty-content")

        status = "cached" if "cached" in response.flags else "downloaded"
        logger.debug(
            "File (%(status)s): Downloaded file from %(request)s referred in "
            "<%(referer)s>",
            {"status": status, "request": request, "referer": referer},
            extra={"spider": info.spider},
        )
        self.inc_stats(status)

        try:
            path = self.file_path(request, response=response, info=info, item=item)
            checksum = await ensure_awaitable(
                self.file_downloaded(response, request, info, item=item)
            )
        except FileException as exc:
            logger.warning(
                "File (error): Error processing file from %(request)s "
                "referred in <%(referer)s>: %(errormsg)s",
                {"request": request, "referer": referer, "errormsg": str(exc)},
                extra={"spider": info.spider},
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "File (unknown-error): Error processing file from %(request)s "
                "referred in <%(referer)s>",
                {"request": request, "referer": referer},
                exc_info=True,
                extra={"spider": info.spider},
            )
            raise FileException(str(exc))

        return {
            "url": request.url,
            "path": path,
            "checksum": checksum,
            "status": status,
        }

    def inc_stats(self, status: str) -> None:
        assert self.crawler.stats
        self.crawler.stats.inc_value("file_count")
        self.crawler.stats.inc_value(f"file_status_count/{status}")

    # Overridable Interface
    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.files_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.files_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = _md5sum(buf)
        buf.seek(0)
        dfd = deferred_from_coro(self.store.persist_file(path, buf, info))
        if isinstance(dfd, Deferred):
            dfd.addCallback(lambda _: checksum)
            return dfd
        return checksum

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.files_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        media_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        media_ext = Path(request.url).suffix
        # Handles empty and wild extensions by trying to guess the
        # mime type then extension or default to empty string otherwise
        if media_ext not in mimetypes.types_map:
            media_ext = ""
            media_type = mimetypes.guess_type(request.url)[0]
            if media_type:
                media_ext = cast("str", mimetypes.guess_extension(media_type))
        return f"full/{media_guid}{media_ext}"

```

```python
"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import functools
import hashlib
import warnings
from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter
from twisted.internet.defer import DeferredList

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline, _md5sum
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from PIL import Image

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.pipelines.media import FileInfoOrError, MediaPipeline


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic"""

    MEDIA_NAME: str = "image"

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH: int = 0
    MIN_HEIGHT: int = 0
    EXPIRES: int = 90
    THUMBS: dict[str, tuple[int, int]] = {}
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of ImagesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        try:
            from PIL import Image, ImageOps  # noqa: PLC0415

            self._Image = Image
            self._ImageOps = ImageOps
        except ImportError:
            raise NotConfigured(
                "ImagesPipeline requires installing Pillow 8.3.2 or later"
            )

        super().__init__(store_uri, crawler=crawler)

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe,
            base_class_name="ImagesPipeline",
            settings=settings,
        )
        self.expires: int = settings.getint(resolve("IMAGES_EXPIRES"), self.EXPIRES)

        if not hasattr(self, "IMAGES_RESULT_FIELD"):
            self.IMAGES_RESULT_FIELD: str = self.DEFAULT_IMAGES_RESULT_FIELD
        if not hasattr(self, "IMAGES_URLS_FIELD"):
            self.IMAGES_URLS_FIELD: str = self.DEFAULT_IMAGES_URLS_FIELD

        self.images_urls_field: str = settings.get(
            resolve("IMAGES_URLS_FIELD"), self.IMAGES_URLS_FIELD
        )
        self.images_result_field: str = settings.get(
            resolve("IMAGES_RESULT_FIELD"), self.IMAGES_RESULT_FIELD
        )
        self.min_width: int = settings.getint(
            resolve("IMAGES_MIN_WIDTH"), self.MIN_WIDTH
        )
        self.min_height: int = settings.getint(
            resolve("IMAGES_MIN_HEIGHT"), self.MIN_HEIGHT
        )
        self.thumbs: dict[str, tuple[int, int]] = settings.get(
            resolve("IMAGES_THUMBS"), self.THUMBS
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, crawler=crawler)

    async def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        return await ensure_awaitable(
            self.image_downloaded(response, request, info, item=item)
        )

    async def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            dfd = maybeDeferred(
                self.store.persist_file,
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
            await maybe_deferred_to_future(dfd)
        assert checksum is not None
        return checksum

    def get_images(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> Iterable[tuple[str, Image.Image, BytesIO]]:
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = self._Image.open(BytesIO(response.body))
        transposed_image = self._ImageOps.exif_transpose(orig_image)

        width, height = transposed_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            transposed_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, response_body=buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(
        self,
        image: Image.Image,
        size: tuple[int, int] | None = None,
        *,
        response_body: BytesIO,
    ) -> tuple[Image.Image, BytesIO]:
        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS  # type: ignore[attr-defined]
            image.thumbnail(size, resampling_filter)
        elif image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.images_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"full/{image_guid}.jpg"

    def thumb_path(
        self,
        request: Request,
        thumb_id: str,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        thumb_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"

```

```python
"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import functools
import hashlib
import warnings
from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter
from twisted.internet.defer import Deferred, DeferredList

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline, _md5sum
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from PIL import Image

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.pipelines.media import FileInfoOrError, MediaPipeline


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic"""

    MEDIA_NAME: str = "image"

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH: int = 0
    MIN_HEIGHT: int = 0
    EXPIRES: int = 90
    THUMBS: dict[str, tuple[int, int]] = {}
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of ImagesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        try:
            from PIL import Image, ImageOps  # noqa: PLC0415

            self._Image = Image
            self._ImageOps = ImageOps
        except ImportError:
            raise NotConfigured(
                "ImagesPipeline requires installing Pillow 8.3.2 or later"
            )

        super().__init__(store_uri, crawler=crawler)

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe,
            base_class_name="ImagesPipeline",
            settings=settings,
        )
        self.expires: int = settings.getint(resolve("IMAGES_EXPIRES"), self.EXPIRES)

        if not hasattr(self, "IMAGES_RESULT_FIELD"):
            self.IMAGES_RESULT_FIELD: str = self.DEFAULT_IMAGES_RESULT_FIELD
        if not hasattr(self, "IMAGES_URLS_FIELD"):
            self.IMAGES_URLS_FIELD: str = self.DEFAULT_IMAGES_URLS_FIELD

        self.images_urls_field: str = settings.get(
            resolve("IMAGES_URLS_FIELD"), self.IMAGES_URLS_FIELD
        )
        self.images_result_field: str = settings.get(
            resolve("IMAGES_RESULT_FIELD"), self.IMAGES_RESULT_FIELD
        )
        self.min_width: int = settings.getint(
            resolve("IMAGES_MIN_WIDTH"), self.MIN_WIDTH
        )
        self.min_height: int = settings.getint(
            resolve("IMAGES_MIN_HEIGHT"), self.MIN_HEIGHT
        )
        self.thumbs: dict[str, tuple[int, int]] = settings.get(
            resolve("IMAGES_THUMBS"), self.THUMBS
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, crawler=crawler)

    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        return self.image_downloaded(response, request, info, item=item)

    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        deferreds: list[Deferred[Any]] = []
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            dfd = deferred_from_coro(
                self.store.persist_file(
                    path,
                    buf,
                    info,
                    meta={"width": width, "height": height},
                    headers={"Content-Type": "image/jpeg"},
                )
            )
            if isinstance(dfd, Deferred):
                deferreds.append(dfd)
        assert checksum is not None
        if deferreds:
            return DeferredList(
                deferreds,
                fireOnOneErrback=True,
                consumeErrors=True,
            ).addCallback(lambda _: checksum)
        return checksum

    def get_images(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> Iterable[tuple[str, Image.Image, BytesIO]]:
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = self._Image.open(BytesIO(response.body))
        transposed_image = self._ImageOps.exif_transpose(orig_image)

        width, height = transposed_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            transposed_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, response_body=buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(
        self,
        image: Image.Image,
        size: tuple[int, int] | None = None,
        *,
        response_body: BytesIO,
    ) -> tuple[Image.Image, BytesIO]:
        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS  # type: ignore[attr-defined]
            image.thumbnail(size, resampling_filter)
        elif image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.images_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"full/{image_guid}.jpg"

    def thumb_path(
        self,
        request: Request,
        thumb_id: str,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        thumb_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"

```

Implemented awaited persistence in the media pipelines so async stores finish before items complete, and added a regression test to lock the behavior. The core change is that `MediaPipeline` now awaits `media_downloaded`, and the default files/images pipelines return awaitables when `persist_file()` is async, preventing premature completion.

- `MediaPipeline._check_media_to_download()` now awaits `media_downloaded()` so coroutine/Deferred results are honored.  
```205:214:scrapy/scrapy/pipelines/media.py
async def _check_media_to_download(
    self, request: Request, info: SpiderInfo, item: Any
) -> FileInfo:
    try:
        self._modify_media_request(request)
        assert self.crawler.engine
        response = await self.crawler.engine.download_async(request)
        return await ensure_awaitable(
            self.media_downloaded(response, request, info, item=item)
        )
```
- `FilesPipeline.media_downloaded()` awaits `file_downloaded()`, and `file_downloaded()` now returns a Deferred when `persist_file()` is async, otherwise a checksum.  
```632:695:scrapy/scrapy/pipelines/files.py
try:
    path = self.file_path(request, response=response, info=info, item=item)
    checksum = await ensure_awaitable(
        self.file_downloaded(response, request, info, item=item)
    )
...
dfd = deferred_from_coro(self.store.persist_file(path, buf, info))
if isinstance(dfd, Deferred):
    dfd.addCallback(lambda _: checksum)
    return dfd
return checksum
```
- `ImagesPipeline.image_downloaded()` now collects async persistence work and waits for it when needed.  
```130:163:scrapy/scrapy/pipelines/images.py
dfd = deferred_from_coro(
    self.store.persist_file(
        path,
        buf,
        info,
        meta={"width": width, "height": height},
        headers={"Content-Type": "image/jpeg"},
    )
)
if isinstance(dfd, Deferred):
    deferreds.append(dfd)
...
if deferreds:
    return DeferredList(
        deferreds,
        fireOnOneErrback=True,
        consumeErrors=True,
    ).addCallback(lambda _: checksum)
```
- Added a test to ensure `process_item()` doesn’t complete before `persist_file()` fires.  
```166:195:scrapy/tests/test_pipeline_files.py
async def test_persist_file_is_awaited(self):
    ...
    item_dfd = deferred_from_coro(self.pipeline.process_item(item))
    ...
    assert not item_dfd.called
    persist_dfd.callback(None)
    result = await maybe_deferred_to_future(item_dfd)
```

Tests not run (not requested). Suggested: `python -m pytest scrapy/tests/test_pipeline_files.py::TestFilesPipeline::test_persist_file_is_awaited`.

```python
async def _check_media_to_download(
    self, request: Request, info: SpiderInfo, item: Any
) -> FileInfo:
    try:
        self._modify_media_request(request)
        assert self.crawler.engine
        response = await self.crawler.engine.download_async(request)
        return await ensure_awaitable(
            self.media_downloaded(response, request, info, item=item)
        )
```

```python
try:
    path = self.file_path(request, response=response, info=info, item=item)
    checksum = await ensure_awaitable(
        self.file_downloaded(response, request, info, item=item)
    )
...
dfd = deferred_from_coro(self.store.persist_file(path, buf, info))
if isinstance(dfd, Deferred):
    dfd.addCallback(lambda _: checksum)
    return dfd
return checksum
```

```python
dfd = deferred_from_coro(
    self.store.persist_file(
        path,
        buf,
        info,
        meta={"width": width, "height": height},
        headers={"Content-Type": "image/jpeg"},
    )
)
if isinstance(dfd, Deferred):
    deferreds.append(dfd)
...
if deferreds:
    return DeferredList(
        deferreds,
        fireOnOneErrback=True,
        consumeErrors=True,
    ).addCallback(lambda _: checksum)
```

```python
async def test_persist_file_is_awaited(self):
    ...
    item_dfd = deferred_from_coro(self.pipeline.process_item(item))
    ...
    assert not item_dfd.called
    persist_dfd.callback(None)
    result = await maybe_deferred_to_future(item_dfd)
```

