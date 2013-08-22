"""
FileMedia Pipeline

See documentation in topics/filemedia.rst
"""
import os
import time
import hashlib
import urlparse
import rfc822
from cStringIO import StringIO
from collections import defaultdict

from twisted.internet import defer, threads

from scrapy import log
from scrapy.utils.misc import md5sum
from scrapy.http import Request
from scrapy.exceptions import DropItem, NotConfigured, IgnoreRequest
from scrapy.contrib.pipeline.media import MediaPipeline


class FileException(Exception):
    """General file error exception"""


def file_key(url, params=None):
    return hashlib.sha1(url).hexdigest()


class FileMediaStore(object):
    """
    `key` identifies the media file in the store
    it should therefore be a unique ID,
    e.g. generated from a URL hash (SHA1, MD5...)

    You could use file_key() as a starting point
    but you may need to add an extension to make it more usable
    """
    def persist_file(self, key, buf, info):
        raise NotImplementedError

    def stat_file(self, key, info):
        """
        This should return a dict with useful keys such as:
         - 'last_modified': to skip download if file is not so old
         - 'checksum'
        """
        raise NotImplementedError


class FSFilesStore(FileMediaStore):
    """
    Filesystem store to persiste files locally
    """
    def __init__(self, basedir, checksum=False):
        if '://' in basedir:
            basedir = basedir.split('://', 1)[1]
        self.basedir = basedir
        self._mkdir(self.basedir)
        self.created_directories = defaultdict(set)
        self.checksum = checksum

    def persist_file(self, key, buf, meta, info):
        absolute_path = self._get_filesystem_path(key)
        self._mkdir(os.path.dirname(absolute_path), info)
        fp = open(absolute_path, 'wb')
        fp.write(buf)
        fp.close()
        retvals = [('path', key),
                   ('full_path', absolute_path),
                   ('size', len(buf))]
        if self.checksum:
            retvals.append(('checksum', md5sum(StringIO(buf))))
        return dict(retvals)

    def stat_file(self, key, info):
        absolute_path = self._get_filesystem_path(key)
        try:
            # we can use os.sstat() for size and modified
            retvals = [('path', key),
                       ('full_path', absolute_path),
                       ('size', os.path.getsize(absolute_path)),
                       ('last_modified', os.path.getmtime(absolute_path))]
        except:  # FIXME: catching everything!
            return {}
        if self.checksum:
            with open(absolute_path, 'rb') as fp:
                retvals.append(('checksum', md5sum(fp)))
        return dict(retvals)

    def _get_filesystem_path(self, key):
        path_comps = key.split('/')
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

    def stat_file(self, key, info):
        def _onsuccess(boto_key):
            checksum = boto_key.etag.strip('"')
            last_modified = boto_key.last_modified
            modified_tuple = rfc822.parsedate_tz(last_modified)
            modified_stamp = int(rfc822.mktime_tz(modified_tuple))
            return {'checksum': checksum, 'last_modified': modified_stamp}

        return self._get_boto_key(key).addCallback(_onsuccess)

    def _get_boto_bucket(self):
        from boto.s3.connection import S3Connection
        # disable ssl (is_secure=False) because of this python bug:
        # http://bugs.python.org/issue5103
        c = S3Connection(self.AWS_ACCESS_KEY_ID, self.AWS_SECRET_ACCESS_KEY, is_secure=False)
        return c.get_bucket(self.bucket, validate=False)

    def _get_boto_key(self, key):
        b = self._get_boto_bucket()
        key_name = '%s%s' % (self.prefix, key)
        return threads.deferToThread(b.get_key, key_name)

    def persist_file(self, key, buf, meta, info):
        """Upload file to S3 storage"""
        b = self._get_boto_bucket()
        if meta:
            key_name = '%s%s' % (self.prefix, key)
            k = b.new_key(key_name)
            for k, v in meta.iteritems():
                k.set_metadata(k, v)
        buf.seek(0)
        return threads.deferToThread(k.set_contents_from_file, buf,
                                     headers=self.HEADERS, policy=self.POLICY)


class FileMediaPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading logic

    This pipeline tries to minimize network transfers,
    doing stat on the files and determining if file is new, up-to-date or
    expired.

    `new` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    `uptodate` files are the ones that the pipeline processed and are still
        valid files.

    `expired` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME = 'file'
    ITEM_MEDIA_URLS_KEY = 'file_urls'
    ITEM_MEDIA_RESULT_KEY = 'files'
    EXPIRES = 90 # expiration in days
    STORE_SCHEMES = {
        '': FSFilesStore,
        'file': FSFilesStore,
        's3': S3FilesStore,
    }

    def __init__(self, store_uri, download_func=None, key_func=None):
        if not store_uri:
            raise NotConfigured
        self.store = self._get_store(store_uri)
        self.key_func = key_func
        super(FileMediaPipeline, self).__init__(download_func=download_func)

    @classmethod
    def from_settings(cls, settings):
        cls.EXPIRES = settings.getint('FILE_EXPIRES', 90)
        store_uri = settings['FILE_STORE']
        return cls(store_uri)

    def _file_key(self, url, params=None):
        """Generate a key identifying the file in the file store, using it's URL"""
        if not self.key_func:
            root, ext = os.path.splitext(urlparse.urlparse(url).path)
            return "%s%s" % (file_key(url), ext)
        else:
            self.key_func(url, params)

    def _get_store(self, uri):
        if os.path.isabs(uri):  # to support win32 paths like: C:\\some\dir
            scheme = 'file'
        else:
            scheme = urlparse.urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_downloaded(self, response, request, info):
        referer = request.headers.get('Referer')

        if response.status != 200:
            log.msg(format='Media (code: %(status)s): Error downloading '
                           '%(medianame)s from %(request)s referred in <%(referer)s>',
                    level=log.WARNING, spider=info.spider,
                    medianame=self.MEDIA_NAME,
                    status=response.status, request=request, referer=referer)
            raise FileException('download-error')

        if not response.body:
            log.msg(format='Media (empty-content): Empty '
                           '%(medianame)s from %(request)s referred in <%(referer)s>: no-content',
                    level=log.WARNING, spider=info.spider,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)
            raise FileException('empty-content')

        status = 'cached' if 'cached' in response.flags else 'downloaded'
        log.msg(format='Media (%(status)s): Downloaded '
                       '%(medianame)s from %(request)s referred in <%(referer)s>',
                level=log.DEBUG, spider=info.spider,
                status=status,
                medianame=self.MEDIA_NAME, request=request, referer=referer)
        self.inc_stats(info.spider, status)

        try:
            processing_result = list(self.file_downloaded(response, request, info))
        except FileException as exc:
            whyfmt = 'Media (error): Error processing %(medianame)s from %(request)s referred in <%(referer)s>: %(errormsg)s'
            log.msg(format=whyfmt, level=log.WARNING, spider=info.spider,
                    medianame=self.MEDIA_NAME,
                    request=request, referer=referer, errormsg=str(exc))
            raise
        except Exception as exc:
            whyfmt = 'Media (unknown-error): Error processing %(medianame)s from %(request)s referred in <%(referer)s>'
            log.err(None, whyfmt % {'request': request, 'referer': referer,
                                    'medianame': self.MEDIA_NAME},
                        spider=info.spider)
            raise FileException(str(exc))

        return processing_result

    def media_failed(self, failure, request, info):
        if not isinstance(failure.value, IgnoreRequest):
            referer = request.headers.get('Referer')
            log.msg(format='Media (unknown-error): Error downloading '
                           '%(medianame)s from %(request)s referred in '
                           '<%(referer)s>: %(exception)s',
                    level=log.WARNING, spider=info.spider, exception=failure.value,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)

        raise FileException

    def media_to_download(self, request, info):
        def _onsuccess(stat_result):
            if not stat_result:
                return  # returning None force download

            last_modified = stat_result.get('last_modified', None)
            if not last_modified:
                return  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.EXPIRES:
                return  # returning None force download

            referer = request.headers.get('Referer')
            log.msg(format='Media (uptodate): Downloaded '
                           '%(medianame)s from %(request)s referred in <%(referer)s>',
                    level=log.DEBUG, spider=info.spider,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)
            self.inc_stats(info.spider, 'uptodate')

            result = {'url': request.url}
            result.update(stat_result)
            return result

        key = self._file_key(request.url)
        dfd = defer.maybeDeferred(self.store.stat_file, key, info)
        dfd.addCallbacks(_onsuccess, lambda _: None)
        dfd.addErrback(log.err, self.__class__.__name__ + '.store.stat_file')
        return dfd

    def file_downloaded(self, response, request, info):
        return self.process_file_buffer(request.url, response.body, info)

    def process_file_buffer(self, url, buf, info):
        key = self._file_key(url)
        store_result = self.store.persist_file(key, buf, None, info)
        store_result.update({'url': url})
        yield store_result

    def inc_stats(self, spider, status):
        spider.crawler.stats.inc_value('media_count', spider=spider)
        spider.crawler.stats.inc_value('media_status_count/%s' % status, spider=spider)

    def get_media_requests(self, item, info):
        return [Request(x) for x in item.get(self.ITEM_MEDIA_URLS_KEY, [])]

    def item_completed(self, results, item, info):
        if self.ITEM_MEDIA_RESULT_KEY in item.fields:
            item[self.ITEM_MEDIA_RESULT_KEY] = [x for ok, x in results if ok]
        return item
