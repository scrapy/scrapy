from __future__ import print_function

import functools
import logging
from collections import defaultdict
from twisted.internet.defer import Deferred, DeferredList, _DefGen_Return
from twisted.python.failure import Failure

from scrapy.settings import Settings
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.defer import mustbe_deferred, defer_result
from scrapy.utils.request import request_fingerprint
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.log import failure_to_exc_info

logger = logging.getLogger(__name__)


class MediaPipeline(object):

    LOG_FAILED_RESULTS = True

    class SpiderInfo(object):
        def __init__(self, spider):
            self.spider = spider
            self.downloading = set()
            self.downloaded = {}
            self.waiting = defaultdict(list)

    def __init__(self, download_func=None, settings=None):
        self.download_func = download_func

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        resolve = functools.partial(self._key_for_pipe,
                                    base_class_name="MediaPipeline",
                                    settings=settings)
        self.allow_redirects = settings.getbool(
            resolve('MEDIA_ALLOW_REDIRECTS'), False
        )
        self._handle_statuses(self.allow_redirects)

    def _handle_statuses(self, allow_redirects):
        self.handle_httpstatus_list = None
        if allow_redirects:
            self.handle_httpstatus_list = SequenceExclude(range(300, 400))

    def _key_for_pipe(self, key, base_class_name=None,
                      settings=None):
        """
        >>> MediaPipeline()._key_for_pipe("IMAGES")
        'IMAGES'
        >>> class MyPipe(MediaPipeline):
        ...     pass
        >>> MyPipe()._key_for_pipe("IMAGES", base_class_name="MediaPipeline")
        'MYPIPE_IMAGES'
        """
        class_name = self.__class__.__name__
        formatted_key = "{}_{}".format(class_name.upper(), key)
        if class_name == base_class_name or not base_class_name \
            or (settings and not settings.get(formatted_key)):
            return key
        return formatted_key

    @classmethod
    def from_crawler(cls, crawler):
        try:
            pipe = cls.from_settings(crawler.settings)
        except AttributeError:
            pipe = cls()
        pipe.crawler = crawler
        return pipe

    def open_spider(self, spider):
        self.spiderinfo = self.SpiderInfo(spider)

    def process_item(self, item, spider):
        info = self.spiderinfo
        requests = arg_to_iter(self.get_media_requests(item, info))
        dlist = [self._process_request(r, info) for r in requests]
        dfd = DeferredList(dlist, consumeErrors=1)
        return dfd.addCallback(self.item_completed, item, info)

    def _process_request(self, request, info):
        fp = request_fingerprint(request)
        cb = request.callback or (lambda _: _)
        eb = request.errback
        request.callback = None
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
        dfd = mustbe_deferred(self.media_to_download, request, info)
        dfd.addCallback(self._check_media_to_download, request, info)
        dfd.addBoth(self._cache_result_and_execute_waiters, fp, info)
        dfd.addErrback(lambda f: logger.error(
            f.value, exc_info=failure_to_exc_info(f), extra={'spider': info.spider})
        )
        return dfd.addBoth(lambda _: wad)  # it must return wad at last

    def _modify_media_request(self, request):
        if self.handle_httpstatus_list:
            request.meta['handle_httpstatus_list'] = self.handle_httpstatus_list
        else:
            request.meta['handle_httpstatus_all'] = True

    def _check_media_to_download(self, result, request, info):
        if result is not None:
            return result
        if self.download_func:
            # this ugly code was left only to support tests. TODO: remove
            dfd = mustbe_deferred(self.download_func, request, info.spider)
            dfd.addCallbacks(
                callback=self.media_downloaded, callbackArgs=(request, info),
                errback=self.media_failed, errbackArgs=(request, info))
        else:
            self._modify_media_request(request)
            dfd = self.crawler.engine.download(request, info.spider)
            dfd.addCallbacks(
                callback=self.media_downloaded, callbackArgs=(request, info),
                errback=self.media_failed, errbackArgs=(request, info))
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
            # Twisted inline callbacks pass return values using the function
            # twisted.internet.defer.returnValue, which encapsulates the return
            # value inside a _DefGen_Return base exception.
            #
            # What happens when the media_downloaded callback raises another
            # exception, for example a FileException('download-error') when
            # the Response status code is not 200 OK, is that it stores the
            # _DefGen_Return exception on the FileException context.
            #
            # To avoid keeping references to the Response and therefore Request
            # objects on the Media Pipeline cache, we should wipe the context of
            # the exception encapsulated by the Twisted Failure when its a
            # _DefGen_Return instance.
            #
            # This problem does not occur in Python 2.7 since we don't have
            # Exception Chaining (https://www.python.org/dev/peps/pep-3134/).
            context = getattr(result.value, '__context__', None)
            if isinstance(context, _DefGen_Return):
                setattr(result.value, '__context__', None)

        info.downloading.remove(fp)
        info.downloaded[fp] = result  # cache result
        for wad in info.waiting.pop(fp):
            defer_result(result).chainDeferred(wad)

    ### Overridable Interface
    def media_to_download(self, request, info):
        """Check request before starting download"""
        pass

    def get_media_requests(self, item, info):
        """Returns the media requests to download"""
        pass

    def media_downloaded(self, response, request, info):
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
                        '%(class)s found errors processing %(item)s',
                        {'class': self.__class__.__name__, 'item': item},
                        exc_info=failure_to_exc_info(value),
                        extra={'spider': info.spider}
                    )
        return item
