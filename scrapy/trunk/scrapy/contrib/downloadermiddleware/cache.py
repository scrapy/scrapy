from __future__ import with_statement

import os
import sha
import datetime
import urlparse
from pydispatch import dispatcher
from twisted.internet import defer

from scrapy.core import signals, log
from scrapy.core.engine import scrapyengine
from scrapy.http import Response, Headers
from scrapy.http.headers import headers_dict_to_raw
from scrapy.core.exceptions import UsageError, NotConfigured, HttpException, IgnoreRequest
from scrapy.conf import settings


class CacheMiddleware(object):
    def __init__(self):
        if not settings['CACHE2_DIR']:
            raise NotConfigured
        self.cache = Cache(settings['CACHE2_DIR'], sectorize=settings.getbool('CACHE2_SECTORIZE'))
        self.ignore_missing = settings.getbool('CACHE2_IGNORE_MISSING')
        dispatcher.connect(self.open_domain, signal=signals.domain_open)

    def open_domain(self, domain):
        self.cache.open_domain(domain)

    def process_request(self, request, spider):
        if not is_cacheable(request):
            return

        key = request.fingerprint()
        domain = spider.domain_name
        response = self.cache.retrieve_response(domain, key)
        if response:
            response.cached = True
            if not 200 <= int(response.status) < 300:
                raise HttpException(response.status, None, response)
            return response
        elif self.ignore_missing:
            raise IgnoreRequest("Ignored request not in cache: %s" % request)

    def process_response(self, request, response, spider):
        if not is_cacheable(request):
            return response

        if isinstance(response, Response) and not response.cached:
            key = request.fingerprint()
            domain = spider.domain_name
            self.cache.store(domain, key, request, response)

        return response

    def process_exception(self, request, exception, spider):
        if not is_cacheable(request):
            return

        if isinstance(exception, HttpException) and isinstance(exception.response, Response):
            key = request.fingerprint()
            domain = spider.domain_name
            self.cache.store(domain,key, request, exception.response)

def is_cacheable(request):
    scheme, _, _, _, _ = urlparse.urlsplit(request.url)
    return scheme in ['http', 'https']


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
        sector = sha.sha(domain).hexdigest()[0]
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

    def is_cached(self, domain, key):
        requestpath = self.requestpath(domain, key)
        return os.path.exists(requestpath)

    def retrieve_response(self, domain, key):
        """
        Return response dictionary if request has correspondent cache record;
        return None if not.
        """
        requestpath = self.requestpath(domain, key)
        if not os.path.exists(requestpath):
            return None # not cached

        metadata = responsebody = responseheaders = None
        with open(os.path.join(requestpath, 'meta_data')) as f:
            metadata = f.read()
        with open(os.path.join(requestpath, 'response_body')) as f:
            responsebody = f.read()
        with open(os.path.join(requestpath, 'response_headers')) as f:
            responseheaders = f.read()

        metadata = eval(metadata)
        url = metadata['url']
        original_url = metadata.get('original_url', url)
        headers = Headers(responseheaders)
        parent = metadata.get('parent')
        status = metadata['status']

        response = Response(domain=domain, url=url, original_url=original_url, headers=headers, status=status, body=responsebody, parent=parent)
        response.cached = True
        return response

    def store(self, domain, key, request, response):
        requestpath = self.requestpath(domain, key)
        if not os.path.exists(requestpath):
            os.makedirs(requestpath)

        metadata = {
                'url':request.url,
                'method': request.method,
                'parent': response.parent,
                'status': response.status,
                'domain': response.domain,
                'original_url': response.original_url,
                'timestamp': datetime.datetime.now(),
            }

        # metadata
        with open(os.path.join(requestpath, 'meta_data'), 'w') as f:
            f.write(repr(metadata))
        # response
        with open(os.path.join(requestpath, 'response_headers'), 'w') as f:
            f.write(headers_dict_to_raw(response.headers))
        with open(os.path.join(requestpath, 'response_body'), 'w') as f:
            f.write(response.body.get_content())
        # request
        with open(os.path.join(requestpath, 'request_headers'), 'w') as f:
            f.write(headers_dict_to_raw(request.headers))
        if request.body:
            with open(os.path.join(requestpath, 'request_body'), 'w') as f:
                f.write(request.body)

