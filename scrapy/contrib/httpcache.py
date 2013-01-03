import os
from time import time
import cPickle as pickle
from w3lib.http import headers_raw_to_dict, headers_dict_to_raw
from scrapy.http import Headers
from scrapy.responsetypes import responsetypes
from scrapy.utils.request import request_fingerprint
from scrapy.utils.project import data_path


class DbmCacheStorage(object):

    def __init__(self, settings):
        self.cachedir = data_path(settings['HTTPCACHE_DIR'], createdir=True)
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self.dbmodule = __import__(settings['HTTPCACHE_DBM_MODULE'])
        self.db = None

    def open_spider(self, spider):
        dbpath = os.path.join(self.cachedir, '%s.db' % spider.name)
        self.db = self.dbmodule.open(dbpath, 'c')

    def close_spider(self, spider):
        self.db.close()

    def retrieve_response(self, spider, request):
        data = self._read_data(spider, request)
        if data is None:
            return  # not cached
        url = data['url']
        status = data['status']
        headers = Headers(data['headers'])
        body = data['body']
        respcls = responsetypes.from_args(headers=headers, url=url)
        response = respcls(url=url, headers=headers, status=status, body=body)
        return response

    def store_response(self, spider, request, response):
        key = self._request_key(request)
        data = {
            'status': response.status,
            'url': response.url,
            'headers': dict(response.headers),
            'body': response.body,
        }
        self.db['%s_data' % key] = pickle.dumps(data, protocol=2)
        self.db['%s_time' % key] = str(time())

    def _read_data(self, spider, request):
        key = self._request_key(request)
        db = self.db
        tkey = '%s_time' % key
        if not db.has_key(tkey):
            return # not found
        ts = db[tkey]
        if 0 < self.expiration_secs < time() - float(ts):
            return # expired
        return pickle.loads(db['%s_data' % key])

    def _request_key(self, request):
        return request_fingerprint(request)


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
            return  # not cached
        rpath = self._get_request_path(spider, request)
        with open(os.path.join(rpath, 'response_body'), 'rb') as f:
            body = f.read()
        with open(os.path.join(rpath, 'response_headers'), 'rb') as f:
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
        if not os.path.exists(rpath):
            os.makedirs(rpath)
        metadata = {
            'url': request.url,
            'method': request.method,
            'status': response.status,
            'response_url': response.url,
            'timestamp': time(),
        }
        with open(os.path.join(rpath, 'meta'), 'wb') as f:
            f.write(repr(metadata))
        with open(os.path.join(rpath, 'pickled_meta'), 'wb') as f:
            pickle.dump(metadata, f, protocol=2)
        with open(os.path.join(rpath, 'response_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(response.headers))
        with open(os.path.join(rpath, 'response_body'), 'wb') as f:
            f.write(response.body)
        with open(os.path.join(rpath, 'request_headers'), 'wb') as f:
            f.write(headers_dict_to_raw(request.headers))
        with open(os.path.join(rpath, 'request_body'), 'wb') as f:
            f.write(request.body)

    def _get_request_path(self, spider, request):
        key = request_fingerprint(request)
        return os.path.join(self.cachedir, spider.name, key[0:2], key)

    def _read_meta(self, spider, request):
        rpath = self._get_request_path(spider, request)
        metapath = os.path.join(rpath, 'pickled_meta')
        if not os.path.exists(metapath):
            return  # not found
        mtime = os.stat(rpath).st_mtime
        if 0 < self.expiration_secs < time() - mtime:
            return  # expired
        with open(metapath, 'rb') as f:
            return pickle.load(f)
