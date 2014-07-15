"""
Files Pipeline
"""

import hashlib
import os
import os.path
import rfc822
import time
from six.moves.urllib.parse import urlparse
from collections import defaultdict
import six

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

from twisted.internet import defer, threads

from scrapy import log
from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import Request
from scrapy.utils.misc import md5sum


class FileException(Exception):
    """General media error exception"""


class FSFilesStore(object):

    def __init__(self, basedir):
        if '://' in basedir:
            basedir = basedir.split('://', 1)[1]
        self.basedir = basedir
        self._mkdir(self.basedir)
        self.created_directories = defaultdict(set)

    def persist_file(self, path, buf, info, meta=None, headers=None):
        absolute_path = self._get_filesystem_path(path)
        self._mkdir(os.path.dirname(absolute_path), info)
        with open(absolute_path, 'wb') as f:
            f.write(buf.getvalue())

    def stat_file(self, path, info):
        absolute_path = self._get_filesystem_path(path)
        try:
            last_modified = os.path.getmtime(absolute_path)
        except:  # FIXME: catching everything!
            return {}

        with open(absolute_path, 'rb') as f:
            checksum = md5sum(f)

        return {'last_modified': last_modified, 'checksum': checksum}

    def _get_filesystem_path(self, path):
        path_comps = path.split('/')
        return os.path.join(self.basedir, *path_comps)

    def _mkdir(self, dirname, domain=None):
        seen = self.created_directories[domain] if domain else set()
        if dirname not in seen:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            seen.add(dirname)


class S3FilesStore(object):

    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None

    POLICY = 'public-read'
    HEADERS = {
        'Cache-Control': 'max-age=172800',
    }

    def __init__(self, uri):
        assert uri.startswith('s3://')
        self.bucket, self.prefix = uri[5:].split('/', 1)

    def stat_file(self, path, info):
        def _onsuccess(boto_key):
            checksum = boto_key.etag.strip('"')
            last_modified = boto_key.last_modified
            modified_tuple = rfc822.parsedate_tz(last_modified)
            modified_stamp = int(rfc822.mktime_tz(modified_tuple))
            return {'checksum': checksum, 'last_modified': modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_bucket(self):
        from boto.s3.connection import S3Connection
        # disable ssl (is_secure=False) because of this python bug:
        # http://bugs.python.org/issue5103
        c = S3Connection(self.AWS_ACCESS_KEY_ID, self.AWS_SECRET_ACCESS_KEY, is_secure=False)
        return c.get_bucket(self.bucket, validate=False)

    def _get_boto_key(self, path):
        b = self._get_boto_bucket()
        key_name = '%s%s' % (self.prefix, path)
        return threads.deferToThread(b.get_key, key_name)

    def persist_file(self, path, buf, info, meta=None, headers=None):
        """Upload file to S3 storage"""
        b = self._get_boto_bucket()
        key_name = '%s%s' % (self.prefix, path)
        k = b.new_key(key_name)
        if meta:
            for metakey, metavalue in six.iteritems(meta):
                k.set_metadata(metakey, str(metavalue))
        h = self.HEADERS.copy()
        if headers:
            h.update(headers)
        buf.seek(0)
        return threads.deferToThread(k.set_contents_from_string, buf.getvalue(),
                                     headers=h, policy=self.POLICY)


class FilesPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading

    This pipeline tries to minimize network transfers and file processing,
    doing stat of the files and determining if file is new, uptodate or
    expired.

    `new` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    `uptodate` files are the ones that the pipeline processed and are still
        valid files.

    `expired` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME = "file"
    EXPIRES = 90
    STORE_SCHEMES = {
        '': FSFilesStore,
        'file': FSFilesStore,
        's3': S3FilesStore,
    }
    DEFAULT_FILES_URLS_FIELD = 'file_urls'
    DEFAULT_FILES_RESULT_FIELD = 'files'

    def __init__(self, store_uri, download_func=None):
        if not store_uri:
            raise NotConfigured
        self.store = self._get_store(store_uri)
        super(FilesPipeline, self).__init__(download_func=download_func)

    @classmethod
    def from_settings(cls, settings):
        s3store = cls.STORE_SCHEMES['s3']
        s3store.AWS_ACCESS_KEY_ID = settings['AWS_ACCESS_KEY_ID']
        s3store.AWS_SECRET_ACCESS_KEY = settings['AWS_SECRET_ACCESS_KEY']

        cls.FILES_URLS_FIELD = settings.get('FILES_URLS_FIELD', cls.DEFAULT_FILES_URLS_FIELD)
        cls.FILES_RESULT_FIELD = settings.get('FILES_RESULT_FIELD', cls.DEFAULT_FILES_RESULT_FIELD)
        cls.EXPIRES = settings.getint('FILES_EXPIRES', 90)
        store_uri = settings['FILES_STORE']
        return cls(store_uri)

    def _get_store(self, uri):
        if os.path.isabs(uri):  # to support win32 paths like: C:\\some\dir
            scheme = 'file'
        else:
            scheme = urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_to_download(self, request, info):
        def _onsuccess(result):
            if not result:
                return  # returning None force download

            last_modified = result.get('last_modified', None)
            if not last_modified:
                return  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.EXPIRES:
                return  # returning None force download

            referer = request.headers.get('Referer')
            log.msg(format='File (uptodate): Downloaded %(medianame)s from %(request)s referred in <%(referer)s>',
                    level=log.DEBUG, spider=info.spider,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)
            self.inc_stats(info.spider, 'uptodate')

            checksum = result.get('checksum', None)
            return {'url': request.url, 'path': path, 'checksum': checksum}

        path = self.file_path(request, info=info)
        dfd = defer.maybeDeferred(self.store.stat_file, path, info)
        dfd.addCallbacks(_onsuccess, lambda _: None)
        dfd.addErrback(log.err, self.__class__.__name__ + '.store.stat_file')
        return dfd

    def media_failed(self, failure, request, info):
        if not isinstance(failure.value, IgnoreRequest):
            referer = request.headers.get('Referer')
            log.msg(format='File (unknown-error): Error downloading '
                           '%(medianame)s from %(request)s referred in '
                           '<%(referer)s>: %(exception)s',
                    level=log.WARNING, spider=info.spider, exception=failure.value,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)

        raise FileException

    def media_downloaded(self, response, request, info):
        referer = request.headers.get('Referer')

        if response.status != 200:
            log.msg(format='File (code: %(status)s): Error downloading file from %(request)s referred in <%(referer)s>',
                    level=log.WARNING, spider=info.spider,
                    status=response.status, request=request, referer=referer)
            raise FileException('download-error')

        if not response.body:
            log.msg(format='File (empty-content): Empty file from %(request)s referred in <%(referer)s>: no-content',
                    level=log.WARNING, spider=info.spider,
                    request=request, referer=referer)
            raise FileException('empty-content')

        status = 'cached' if 'cached' in response.flags else 'downloaded'
        log.msg(format='File (%(status)s): Downloaded file from %(request)s referred in <%(referer)s>',
                level=log.DEBUG, spider=info.spider,
                status=status, request=request, referer=referer)
        self.inc_stats(info.spider, status)

        try:
            path = self.file_path(request, response=response, info=info)
            checksum = self.file_downloaded(response, request, info)
        except FileException as exc:
            whyfmt = 'File (error): Error processing file from %(request)s referred in <%(referer)s>: %(errormsg)s'
            log.msg(format=whyfmt, level=log.WARNING, spider=info.spider,
                    request=request, referer=referer, errormsg=str(exc))
            raise
        except Exception as exc:
            whyfmt = 'File (unknown-error): Error processing file from %(request)s referred in <%(referer)s>'
            log.err(None, whyfmt % {'request': request, 'referer': referer}, spider=info.spider)
            raise FileException(str(exc))

        return {'url': request.url, 'path': path, 'checksum': checksum}

    def inc_stats(self, spider, status):
        spider.crawler.stats.inc_value('file_count', spider=spider)
        spider.crawler.stats.inc_value('file_status_count/%s' % status, spider=spider)

    ### Overridable Interface
    def get_media_requests(self, item, info):
        return [Request(x) for x in item.get(self.FILES_URLS_FIELD, [])]

    def file_downloaded(self, response, request, info):
        path = self.file_path(request, response=response, info=info)
        buf = BytesIO(response.body)
        self.store.persist_file(path, buf, info)
        checksum = md5sum(buf)
        return checksum

    def item_completed(self, results, item, info):
        if self.FILES_RESULT_FIELD in item.fields:
            item[self.FILES_RESULT_FIELD] = [x for ok, x in results if ok]
        return item

    def file_path(self, request, response=None, info=None):
        ## start of deprecation warning block (can be removed in the future)
        def _warn():
            from scrapy.exceptions import ScrapyDeprecationWarning
            import warnings
            warnings.warn('FilesPipeline.file_key(url) method is deprecated, please use '
                          'file_path(request, response=None, info=None) instead',
                          category=ScrapyDeprecationWarning, stacklevel=1)

        # check if called from file_key with url as first argument
        if not isinstance(request, Request):
            _warn()
            url = request
        else:
            url = request.url

        # detect if file_key() method has been overridden
        if not hasattr(self.file_key, '_base'):
            _warn()
            return self.file_key(url)
        ## end of deprecation warning block

        media_guid = hashlib.sha1(url).hexdigest()  # change to request.url after deprecation
        media_ext = os.path.splitext(url)[1]  # change to request.url after deprecation
        return 'full/%s%s' % (media_guid, media_ext)

    # deprecated
    def file_key(self, url):
        return self.file_path(url)
    file_key._base = True
