import os
from os.path import join, exists
from time import time
import cPickle as pickle

from w3lib.http import headers_dict_to_raw, headers_raw_to_dict

from scrapy import signals
from scrapy.http import Headers
from scrapy.http.request import Request
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.responsetypes import responsetypes
from scrapy.utils.request import request_fingerprint
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.project import data_path


class HttpCachePolicy(object):
    def __init__(self, settings):
        self.ignore_schemes = settings.getlist('HTTPCACHE_IGNORE_SCHEMES')
        self.ignore_http_codes = map(int, settings.getlist('HTTPCACHE_IGNORE_HTTP_CODES'))
        self.policy = settings.get('HTTPCACHE_POLICY')

        if self.policy == 'dummy':
            self.use_dummy_cache = True
        else:
            self.use_dummy_cache = False

    def should_cache_response(self, response):
        retval = response.status not in self.ignore_http_codes
        if not self.use_dummy_cache and response.headers.has_key('cache-control'):
            retval = retval and (response.headers['cache-control'].lower().find('no-store') == -1)
        #retval = retval and self.policy_response(response)
        return retval

    def should_cache_request(self, request):
        retval = urlparse_cached(request).scheme not in self.ignore_schemes
        if not self.use_dummy_cache and request.headers.has_key('cache-control'):
            retval = retval and (request.headers['cache-control'].lower().find('no-store') == -1)
        #retval = retval and self.policy_request(request)
        return retval

class HttpCacheMiddleware(HttpCachePolicy):

    def __init__(self, settings, stats):
        if not settings.getbool('HTTPCACHE_ENABLED'):
            raise NotConfigured
        self.storage = load_object(settings['HTTPCACHE_STORAGE'])(settings)
        self.ignore_missing = settings.getbool('HTTPCACHE_IGNORE_MISSING')
        self.stats = stats
        super(HttpCacheMiddleware, self).__init__(settings)

    @classmethod
    def from_crawler(cls, crawler):
        o = cls.from_settings(crawler.settings, crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider):
        self.storage.open_spider(spider)

    def spider_closed(self, spider):
        self.storage.close_spider(spider)

    def process_request(self, request, spider):
        if not self.should_cache_request(request):
            return
        response = self.storage.retrieve_response(spider, request)

        # Response cached, but stale
        if response and type(response) is Request:
            # Return None so that Scrapy continues processing
            self.stats.inc_value('httpcache/revalidation', spider=spider)
            return

        if response and self.should_cache_response(response):
            self.stats.inc_value('httpcache/hit', spider=spider)
            if self.use_dummy_cache:
                response.flags.append('cached')
                return response
            else:
                # Response cached and fresh
                raise IgnoreRequest("Ignored request already in cache: %s" % request)

        # Response not cached
        self.stats.inc_value('httpcache/miss', spider=spider)
        if self.ignore_missing:
            raise IgnoreRequest("Ignored request not in cache: %s" % request)

    def process_response(self, request, response, spider):
        if (self.should_cache_request(request)
            and self.should_cache_response(response)):
            if self.use_dummy_cache:
                if 'cached' not in response.flags:
                    self.storage.store_response(spider, request, response)
                    self.stats.inc_value('httpcache/store', spider=spider)
            else:
                if response.status != 304:
                    self.storage.store_response(spider, request, response)
                    self.stats.inc_value('httpcache/store', spider=spider)
                else:
                    response.flags.append('cached')
                    self.stats.inc_value('httpcache/hit', spider=spider)
        return response


class FilesystemCacheStorage(object):

    def __init__(self, settings):
        self.cachedir = data_path(settings['HTTPCACHE_DIR'])
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def retrieve_response(self, spider, request):
        """Return response if present in cache, or None otherwise."""
        metadata = self._read_meta(spider, request)
        if metadata is None:
            return # not cached
        rpath = self._get_request_path(spider, request)
        with open(join(rpath, 'response_body'), 'rb') as f:
            body = f.read()
        with open(join(rpath, 'response_headers'), 'rb') as f:
            rawheaders = f.read()
        url = metadata.get('response_url')
        status = metadata['status']
        headers = Headers(headers_raw_to_dict(rawheaders))
        respcls = responsetypes.from_args(headers=headers, url=url)
        response = respcls(url=url, headers=headers, status=status, body=body)
        return response

    def store_response(self, spider, request, response):
        """Store the given response in the cache."""
        rpath = self._get_request_path(spider, request)
        if not exists(rpath):
            os.makedirs(rpath)
        metadata = {
            'url': request.url,
            'method': request.method,
            'status': response.status,
            'response_url': response.url,
            'timestamp': time(),
        }
        with open(join(rpath, 'meta'), 'wb') as f:
            f.write(repr(metadata))
        with open(join(rpath, 'pickled_meta'), 'wb') as f:
            pickle.dump(metadata, f, protocol=2)
        with open(join(rpath, 'response_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(response.headers))
        with open(join(rpath, 'response_body'), 'wb') as f:
            f.write(response.body)
        with open(join(rpath, 'request_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(request.headers))
        with open(join(rpath, 'request_body'), 'wb') as f:
            f.write(request.body)

    def _get_request_path(self, spider, request):
        key = request_fingerprint(request)
        return join(self.cachedir, spider.name, key[0:2], key)

    def _read_meta(self, spider, request):
        rpath = self._get_request_path(spider, request)
        metapath = join(rpath, 'pickled_meta')
        if not exists(metapath):
            return # not found
        mtime = os.stat(rpath).st_mtime
        if 0 < self.expiration_secs < time() - mtime:
            return # expired
        with open(metapath, 'rb') as f:
            return pickle.load(f)
