import os
import calendar
import email.utils
from time import time
import cPickle as pickle

from scrapy import log
from scrapy.http import Headers
from scrapy.exceptions import IgnoreRequest
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
            return # not cached
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


class BaseRealCacheStorage(object):
    """
    Most of the code was taken from the httplib2 (MIT License)
    https://code.google.com/p/httplib2/source/browse/python2/httplib2/__init__.py
    """
    
    def parse_cache_control(self, headers):
        retval = {}
        if headers.has_key('cache-control'):
            parts =  headers['cache-control'].split(',')
            parts_with_args = [tuple([x.strip().lower() for x in part.split("=", 1)]) for part in parts if -1 != part.find("=")]
            parts_wo_args = [(name.strip().lower(), 1) for name in parts if -1 == name.find("=")]
            retval = dict(parts_with_args + parts_wo_args)
        return retval
    
    
    def get(self, response_headers, request_headers):
        """Determine freshness from the Date, Expires and Cache-Control headers.

        We don't handle the following:

        1. Cache-Control: max-stale
        2. Age: headers are not used in the calculations.

        Not that this algorithm is simpler than you might think
        because we are operating as a private (non-shared) cache.
        This lets us ignore 's-maxage'. We can also ignore
        'proxy-invalidate' since we aren't a proxy.
        We will never return a stale document as
        fresh as a design decision, and thus the non-implementation
        of 'max-stale'. This also lets us safely ignore 'must-revalidate'
        since we operate as if every server has sent 'must-revalidate'.
        Since we are private we get to ignore both 'public' and
        'private' parameters. We also ignore 'no-transform' since
        we don't do any transformations.
        The 'no-store' parameter is handled at a higher level.
        So the only Cache-Control parameters we look at are:

        no-cache
        only-if-cached
        max-age
        min-fresh
        """

        retval = "STALE"
        cc = self.parse_cache_control(request_headers)
        cc_response = self.parse_cache_control(response_headers)
        
        if request_headers.has_key('pragma') and request_headers['pragma'].lower().find('no-cache') != -1:
            retval = "TRANSPARENT"
            if 'cache-control' not in request_headers:
                request_headers['cache-control'] = 'no-cache'
        elif cc.has_key('no-cache'):
            retval = "TRANSPARENT"
        elif cc_response.has_key('no-cache'):
            retval = "STALE"
        elif cc.has_key('only-if-cached'):
            retval = "FRESH"
        elif response_headers.has_key('date'):
            date = calendar.timegm(email.utils.parsedate_tz(response_headers['date']))
            now = time()
            current_age = max(0, now - date)
            if cc_response.has_key('max-age'):
                try:
                    freshness_lifetime = int(cc_response['max-age'])
                except ValueError:
                    freshness_lifetime = 0
            elif response_headers.has_key('expires'):
                expires = email.utils.parsedate_tz(response_headers['expires'])
                if None == expires:
                    freshness_lifetime = 0
                else:
                    freshness_lifetime = max(0, calendar.timegm(expires) - date)
            else:
                freshness_lifetime = 0
            if cc.has_key('max-age'):
                try:
                    freshness_lifetime = int(cc['max-age'])
                except ValueError:
                    freshness_lifetime = 0
            if cc.has_key('min-fresh'):
                try:
                    min_fresh = int(cc['min-fresh'])
                except ValueError:
                    min_fresh = 0
                current_age += min_fresh
            if freshness_lifetime > current_age:
                retval = "FRESH"
        return retval

    def retrieve_cache(self, spider, request, response_headers, response_status, response_url='', response_body=''):
        # Determine our course of action:
        #   Is the cached entry fresh or stale?
        #
        # There seems to be three possible answers:
        # 1. [FRESH] Return the Response object
        # 2. [STALE] Update the Request object with cache validators if available
        # 3. [TRANSPARENT] Don't update the Request with cache validators (Cache-Control: no-cache)
        entry_disposition = self.get(Headers(response_headers), Headers(request.headers))
        
        # Per the RFC, requests should not be repeated in these situations
        if response_status in [400, 401, 403, 410]:
            raise IgnoreRequest("Ignored request because cached response status is %d." % response_status)
        
        if entry_disposition == "FRESH":
            log.msg("Cache is FRESH", level=log.DEBUG, spider=spider)
            
            headers = Headers(response_headers)
            respcls = responsetypes.from_args(headers=headers, url=response_url)
            response = respcls(url=response_url, headers=headers, status=response_status, body=response_body)
            
            return response

        new_request = request.copy()
        if entry_disposition == "STALE":
            log.msg("Cache is STALE, updating Request object with cache validators", level=log.DEBUG, spider=spider)
            if response_headers.has_key('ETag') and not 'If-None-Match' in request.headers:
                new_request.headers['If-None-Match'] = response_headers['ETag']
            if response_headers.has_key('Last-Modified') and not 'Last-Modified' in request.headers:
                new_request.headers['If-Modified-Since'] = response_headers['Last-Modified']
        elif entry_disposition == "TRANSPARENT":
            log.msg("Cache is TRANSPARENT, not adding cache validators to Request object", level=log.DEBUG, spider=spider)
        
        return new_request


class DbmRealCacheStorage(DbmCacheStorage, BaseRealCacheStorage):
    def __init__(self, settings):
        super(DbmRealCacheStorage, self).__init__(settings)
    
    def retrieve_response(self, spider, request):
        data = self._read_data(spider, request)
        if data is None:
            return # not cached
        else:
            return self.retrieve_cache(spider, request, data['headers'], data['status'], data['url'], data['body'])
