from __future__ import with_statement

import errno
import os
import hashlib
import datetime
import cPickle as pickle
from pydispatch import dispatcher

from scrapy.core import signals
from scrapy import log
from scrapy.http import Response, Headers
from scrapy.core.exceptions import NotConfigured, IgnoreRequest
from scrapy.core.downloader.responsetypes import responsetypes
from scrapy.utils.request import request_fingerprint
from scrapy.utils.http import headers_dict_to_raw, headers_raw_to_dict
from scrapy.conf import settings


class HttpCacheMiddleware(object):
    def __init__(self):
        if not settings['HTTPCACHE_DIR']:
            raise NotConfigured
        self.cache = Cache(settings['HTTPCACHE_DIR'], sectorize=settings.getbool('HTTPCACHE_SECTORIZE'))
        self.ignore_missing = settings.getbool('HTTPCACHE_IGNORE_MISSING')
        dispatcher.connect(self.open_domain, signal=signals.domain_open)

    def open_domain(self, domain):
        self.cache.open_domain(domain)

    def process_request(self, request, spider):
        if not is_cacheable(request):
            return

        key = request_fingerprint(request)
        domain = spider.domain_name

        try:
            response = self.cache.retrieve_response(domain, key)
        except:
            log.msg("Corrupt cache for %s" % request.url, log.WARNING)
            response = False

        if response:
            return response
        elif self.ignore_missing:
            raise IgnoreRequest("Ignored request not in cache: %s" % request)

    def process_response(self, request, response, spider):
        if is_cacheable(request):
            key = request_fingerprint(request)
            self.cache.store(spider.domain_name, key, request, response)

        return response


def is_cacheable(request):
    return request.url.scheme in ['http', 'https']


class Cache(object):
    DOMAIN_SECTORDIR = 'data'
    DOMAIN_LINKDIR = 'domains'

    def __init__(self, cachedir, sectorize=False):
        self.cachedir = cachedir
        self.sectorize = sectorize

        self.baselinkpath = os.path.join(self.cachedir, self.DOMAIN_LINKDIR)
        if not os.path.exists(self.baselinkpath):
            os.makedirs(self.baselinkpath)

        self.basesectorpath = os.path.join(self.cachedir, self.DOMAIN_SECTORDIR)
        if not os.path.exists(self.basesectorpath):
            os.makedirs(self.basesectorpath)

    def domainsectorpath(self, domain):
        sector = hashlib.sha1(domain).hexdigest()[0]
        return os.path.join(self.basesectorpath, sector, domain)

    def domainlinkpath(self, domain):
        return os.path.join(self.baselinkpath, domain)

    def requestpath(self, domain, key):
        linkpath = self.domainlinkpath(domain)
        return os.path.join(linkpath, key[0:2], key)

    def open_domain(self, domain):
        if domain:
            linkpath = self.domainlinkpath(domain)
            if self.sectorize:
                sectorpath = self.domainsectorpath(domain)
                if not os.path.exists(sectorpath):
                    os.makedirs(sectorpath)
                if not os.path.exists(linkpath):
                    try:
                        os.symlink(sectorpath, linkpath)
                    except:
                        os.makedirs(linkpath) # windows filesystem
            else:
                if not os.path.exists(linkpath):
                    os.makedirs(linkpath)

    def read_meta(self, domain, key):
        """Return the metadata dictionary (possibly empty) if the entry is
        cached, None otherwise.
        """
        requestpath = self.requestpath(domain, key)
        try:
            with open(os.path.join(requestpath, 'pickled_meta'), 'r') as f:
                metadata = pickle.load(f)
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            return None
        expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        if expiration_secs >= 0:
            expiration_date = metadata['timestamp'] + datetime.timedelta(seconds=expiration_secs)
            if datetime.datetime.utcnow() > expiration_date:
                log.msg('dropping old cached response from %s' % metadata['timestamp'], level=log.DEBUG)
                return None
        return metadata

    def retrieve_response(self, domain, key):
        """
        Return response dictionary if request has correspondent cache record;
        return None if not.
        """
        metadata = self.read_meta(domain, key)
        if metadata is None:
            return None # not cached

        requestpath = self.requestpath(domain, key)
        responsebody = responseheaders = None
        with open(os.path.join(requestpath, 'response_body')) as f:
            responsebody = f.read()
        with open(os.path.join(requestpath, 'response_headers')) as f:
            responseheaders = f.read()

        url = metadata['url']
        headers = Headers(headers_raw_to_dict(responseheaders))
        status = metadata['status']

        respcls = responsetypes.from_args(headers=headers, url=url)
        response = respcls(url=url, headers=headers, status=status, body=responsebody)
        response.meta['cached'] = True
        response.flags.append('cached')
        return response

    def store(self, domain, key, request, response):
        requestpath = self.requestpath(domain, key)
        if not os.path.exists(requestpath):
            os.makedirs(requestpath)

        metadata = {
                'url':request.url,
                'method': request.method,
                'status': response.status,
                'domain': domain,
                'timestamp': datetime.datetime.utcnow(),
            }

        # metadata
        with open(os.path.join(requestpath, 'meta_data'), 'w') as f:
            f.write(repr(metadata))
        # pickled metadata (to recover without using eval)
        with open(os.path.join(requestpath, 'pickled_meta'), 'w') as f:
            pickle.dump(metadata, f)
        # response
        with open(os.path.join(requestpath, 'response_headers'), 'w') as f:
            f.write(headers_dict_to_raw(response.headers))
        with open(os.path.join(requestpath, 'response_body'), 'w') as f:
            f.write(response.body)
        # request
        with open(os.path.join(requestpath, 'request_headers'), 'w') as f:
            f.write(headers_dict_to_raw(request.headers))
        if request.body:
            with open(os.path.join(requestpath, 'request_body'), 'w') as f:
                f.write(request.body)
