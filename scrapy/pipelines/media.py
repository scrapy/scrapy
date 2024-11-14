from __future__ import annotations

import functools
import logging
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NoReturn,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

from twisted import version as twisted_version
from twisted.internet.defer import Deferred, DeferredList
from twisted.python.failure import Failure
from twisted.python.versions import Version

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.request import NO_CALLBACK, Request
from scrapy.settings import Settings
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.defer import defer_result, mustbe_deferred
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args, global_object_name

if TYPE_CHECKING:
    from collections.abc import Callable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.utils.request import RequestFingerprinter

_T = TypeVar("_T")


class FileInfo(TypedDict):
    url: str
    path: str
    checksum: str | None
    status: str


FileInfoOrError = Union[tuple[Literal[True], FileInfo], tuple[Literal[False], Failure]]

logger = logging.getLogger(__name__)


class MediaPipeline(ABC):
    crawler: Crawler
    _fingerprinter: RequestFingerprinter
    _modern_init = False

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
        download_func: Callable[[Request, Spider], Response] | None = None,
        settings: Settings | dict[str, Any] | None = None,
        *,
        crawler: Crawler | None = None,
    ):
        self.download_func = download_func

        if crawler is not None:
            if settings is not None:
                warnings.warn(
                    f"MediaPipeline.__init__() was called with a crawler instance and a settings instance"
                    f" when creating {global_object_name(self.__class__)}. The settings instance will be ignored"
                    f" and crawler.settings will be used. The settings argument will be removed in a future Scrapy version.",
                    category=ScrapyDeprecationWarning,
                    stacklevel=2,
                )
            settings = crawler.settings
        elif isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name="MediaPipeline", settings=settings
        )
        self.allow_redirects: bool = settings.getbool(
            resolve("MEDIA_ALLOW_REDIRECTS"), False
        )
        self._handle_statuses(self.allow_redirects)

        if crawler:
            self._finish_init(crawler)
            self._modern_init = True
        else:
            warnings.warn(
                f"MediaPipeline.__init__() was called without the crawler argument"
                f" when creating {global_object_name(self.__class__)}."
                f" This is deprecated and the argument will be required in future Scrapy versions.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

    def _finish_init(self, crawler: Crawler) -> None:
        # This was done in from_crawler() before 2.12, now it's done in __init__()
        # if the crawler was passed to it and may be needed to be called in other
        # deprecated code paths explicitly too. After the crawler argument of __init__()
        # becomes mandatory this should be inlined there.
        self.crawler = crawler
        assert crawler.request_fingerprinter
        self._fingerprinter = crawler.request_fingerprinter

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
            or settings
            and not settings.get(formatted_key)
        ):
            return key
        return formatted_key

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        pipe: Self
        if hasattr(cls, "from_settings"):
            pipe = cls.from_settings(crawler.settings)  # type: ignore[attr-defined]
        elif "crawler" in get_func_args(cls.__init__):
            pipe = cls(crawler=crawler)
        else:
            pipe = cls()
            warnings.warn(
                f"{global_object_name(cls)}.__init__() doesn't take a crawler argument."
                " This is deprecated and the argument will be required in future Scrapy versions.",
                category=ScrapyDeprecationWarning,
            )
        if not pipe._modern_init:
            pipe._finish_init(crawler)
        return pipe

    def open_spider(self, spider: Spider) -> None:
        self.spiderinfo = self.SpiderInfo(spider)

    def process_item(
        self, item: Any, spider: Spider
    ) -> Deferred[list[FileInfoOrError]]:
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = [self._process_request(r, info, item) for r in requests]
        dfd = cast(
            "Deferred[list[FileInfoOrError]]", DeferredList(dlist, consumeErrors=True)
        )
        return dfd.addCallback(self.item_completed, item, info)

    def _process_request(
        self, request: Request, info: SpiderInfo, item: Any
    ) -> Deferred[FileInfo]:
        fp = self._fingerprinter.fingerprint(request)
        eb = request.errback
        request.callback = NO_CALLBACK
        request.errback = None

        # Return cached result if request was already seen
        if fp in info.downloaded:
            d = defer_result(info.downloaded[fp])
            if eb:
                d.addErrback(eb)
            return d

        # Otherwise, wait for result
        wad: Deferred[FileInfo] = Deferred()
        if eb:
            wad.addErrback(eb)
        info.waiting[fp].append(wad)

        # Check if request is downloading right now to avoid doing it twice
        if fp in info.downloading:
            return wad

        # Download request checking media_to_download hook output first
        info.downloading.add(fp)
        dfd: Deferred[FileInfo | None] = mustbe_deferred(
            self.media_to_download, request, info, item=item
        )
        dfd2: Deferred[FileInfo] = dfd.addCallback(
            self._check_media_to_download, request, info, item=item
        )
        dfd2.addErrback(self._log_exception)
        dfd2.addBoth(self._cache_result_and_execute_waiters, fp, info)
        return dfd2.addBoth(lambda _: wad)  # it must return wad at last

    def _log_exception(self, result: Failure) -> Failure:
        logger.exception(result)
        return result

    def _modify_media_request(self, request: Request) -> None:
        if self.handle_httpstatus_list:
            request.meta["handle_httpstatus_list"] = self.handle_httpstatus_list
        else:
            request.meta["handle_httpstatus_all"] = True

    def _check_media_to_download(
        self, result: FileInfo | None, request: Request, info: SpiderInfo, item: Any
    ) -> FileInfo | Deferred[FileInfo]:
        if result is not None:
            return result
        dfd: Deferred[Response]
        if self.download_func:
            # this ugly code was left only to support tests. TODO: remove
            dfd = mustbe_deferred(self.download_func, request, info.spider)
        else:
            self._modify_media_request(request)
            assert self.crawler.engine
            dfd = self.crawler.engine.download(request)
        dfd2: Deferred[FileInfo] = dfd.addCallback(
            self.media_downloaded, request, info, item=item
        )
        dfd2.addErrback(self.media_failed, request, info)
        return dfd2

    def _cache_result_and_execute_waiters(
        self, result: FileInfo | Failure, fp: bytes, info: SpiderInfo
    ) -> None:
        if isinstance(result, Failure):
            # minimize cached information for failure
            result.cleanFailure()
            result.frames = []
            if twisted_version <= Version("twisted", 24, 10, 0):
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
            #
            # This problem does not occur in Python 2.7 since we don't have
            # Exception Chaining (https://www.python.org/dev/peps/pep-3134/).
            context = getattr(result.value, "__context__", None)
            if isinstance(context, StopIteration):
                result.value.__context__ = None

        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            defer_result(result).chainDeferred(wad)

    # Overridable Interface
    @abstractmethod
    def media_to_download(
        self, request: Request, info: SpiderInfo, *, item: Any = None
    ) -> Deferred[FileInfo | None]:
        """Check request before starting download"""
        raise NotImplementedError()

    @abstractmethod
    def get_media_requests(self, item: Any, info: SpiderInfo) -> list[Request]:
        """Returns the media requests to download"""
        raise NotImplementedError()

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
        raise NotImplementedError()

    @abstractmethod
    def media_failed(
        self, failure: Failure, request: Request, info: SpiderInfo
    ) -> NoReturn:
        """Handler for failed downloads"""
        raise NotImplementedError()

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
        raise NotImplementedError()
