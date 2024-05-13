import functools
import logging
from collections import defaultdict
from inspect import signature
from warnings import warn

from twisted.internet.defer import Deferred, DeferredList
from twisted.python.failure import Failure

from scrapy.http.request import NO_CALLBACK
from scrapy.settings import Settings
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.defer import defer_result, mustbe_deferred
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import arg_to_iter

logger = logging.getLogger(__name__)


def _DUMMY_CALLBACK(response):
    return response


class MediaPipeline:
    LOG_FAILED_RESULTS = True

    class SpiderInfo:
        def __init__(self, spider):
            self.spider = spider
            self.downloading = set()
            self.downloaded = {}
            self.waiting = defaultdict(list)

    def __init__(self, download_func=None, settings=None):
        self.download_func = download_func
        self._expects_item = {}

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name="MediaPipeline", settings=settings
        )
        self.allow_redirects = settings.getbool(resolve("MEDIA_ALLOW_REDIRECTS"), False)
        self._handle_statuses(self.allow_redirects)

        # Check if deprecated methods are being used and make them compatible
        self._make_compatible()

    def _handle_statuses(self, allow_redirects):
        self.handle_httpstatus_list = None
        if allow_redirects:
            self.handle_httpstatus_list = SequenceExclude(range(300, 400))

    def _key_for_pipe(self, key, base_class_name=None, settings=None):
        """
        >>> MediaPipeline()._key_for_pipe("IMAGES")
        'IMAGES'
        >>> class MyPipe(MediaPipeline):
        ...     pass
        >>> MyPipe()._key_for_pipe("IMAGES", base_class_name="MediaPipeline")
        'MYPIPE_IMAGES'
        """
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
    def from_crawler(cls, crawler):
        try:
            pipe = cls.from_settings(crawler.settings)
        except AttributeError:
            pipe = cls()
        pipe.crawler = crawler
        pipe._fingerprinter = crawler.request_fingerprinter
        return pipe

    def open_spider(self, spider):
        self.spiderinfo = self.SpiderInfo(spider)

    def process_item(self, item, spider):
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = [self._process_request(r, info, item) for r in requests]
        dfd = DeferredList(dlist, consumeErrors=True)
        return dfd.addCallback(self.item_completed, item, info)

    def _process_request(self, request, info, item):
        fp = self._fingerprinter.fingerprint(request)
        if not request.callback or request.callback is NO_CALLBACK:
            cb = _DUMMY_CALLBACK
        else:
            cb = request.callback
        eb = request.errback
        request.callback = NO_CALLBACK
        request.errback = None

        # Return cached result if request was already seen
        if fp in info.downloaded:
            return defer_result(info.downloaded[fp]).addCallbacks(cb, eb)

        # Otherwise, wait for result
        wad = Deferred().addCallbacks(cb, eb)
        info.waiting[fp].append(wad)

        # Check if request is downloading right now to avoid doing it twice
        if fp in info.downloading:
            return wad

        # Download request checking media_to_download hook output first
        info.downloading.add(fp)
        dfd = mustbe_deferred(self.media_to_download, request, info, item=item)
        dfd.addCallback(self._check_media_to_download, request, info, item=item)
        dfd.addErrback(self._log_exception)
        dfd.addBoth(self._cache_result_and_execute_waiters, fp, info)
        return dfd.addBoth(lambda _: wad)  # it must return wad at last

    def _log_exception(self, result):
        logger.exception(result)
        return result

    def _make_compatible(self):
        """Make overridable methods of MediaPipeline and subclasses backwards compatible"""
        methods = [
            "file_path",
            "thumb_path",
            "media_to_download",
            "media_downloaded",
            "file_downloaded",
            "image_downloaded",
            "get_images",
        ]

        for method_name in methods:
            method = getattr(self, method_name, None)
            if callable(method):
                setattr(self, method_name, self._compatible(method))

    def _compatible(self, func):
        """Wrapper for overridable methods to allow backwards compatibility"""
        self._check_signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if self._expects_item[func.__name__]:
                return func(*args, **kwargs)

            kwargs.pop("item", None)
            return func(*args, **kwargs)

        return wrapper

    def _check_signature(self, func):
        sig = signature(func)
        self._expects_item[func.__name__] = True

        if "item" not in sig.parameters:
            old_params = str(sig)[1:-1]
            new_params = old_params + ", *, item=None"
            warn(
                f"{func.__name__}(self, {old_params}) is deprecated, "
                f"please use {func.__name__}(self, {new_params})",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self._expects_item[func.__name__] = False

    def _modify_media_request(self, request):
        if self.handle_httpstatus_list:
            request.meta["handle_httpstatus_list"] = self.handle_httpstatus_list
        else:
            request.meta["handle_httpstatus_all"] = True

    def _check_media_to_download(self, result, request, info, item):
        if result is not None:
            return result
        if self.download_func:
            # this ugly code was left only to support tests. TODO: remove
            dfd = mustbe_deferred(self.download_func, request, info.spider)
            dfd.addCallbacks(
                callback=self.media_downloaded,
                callbackArgs=(request, info),
                callbackKeywords={"item": item},
                errback=self.media_failed,
                errbackArgs=(request, info),
            )
        else:
            self._modify_media_request(request)
            dfd = self.crawler.engine.download(request)
            dfd.addCallbacks(
                callback=self.media_downloaded,
                callbackArgs=(request, info),
                callbackKeywords={"item": item},
                errback=self.media_failed,
                errbackArgs=(request, info),
            )
        return dfd

    def _cache_result_and_execute_waiters(self, result, fp, info):
        if isinstance(result, Failure):
            # minimize cached information for failure
            result.cleanFailure()
            result.frames = []
            result.stack = None

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
                setattr(result.value, "__context__", None)

        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            defer_result(result).chainDeferred(wad)

    # Overridable Interface
    def media_to_download(self, request, info, *, item=None):
        """Check request before starting download"""
        pass

    def get_media_requests(self, item, info):
        """Returns the media requests to download"""
        pass

    def media_downloaded(self, response, request, info, *, item=None):
        """Handler for success downloads"""
        return response

    def media_failed(self, failure, request, info):
        """Handler for failed downloads"""
        return failure

    def item_completed(self, results, item, info):
        """Called per item when all media requests has been processed"""
        if self.LOG_FAILED_RESULTS:
            for ok, value in results:
                if not ok:
                    logger.error(
                        "%(class)s found errors processing %(item)s",
                        {"class": self.__class__.__name__, "item": item},
                        exc_info=failure_to_exc_info(value),
                        extra={"spider": info.spider},
                    )
        return item

    def file_path(self, request, response=None, info=None, *, item=None):
        """Returns the path where downloaded media should be stored"""
        pass
