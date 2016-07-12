"""
Files Pipeline

See documentation in topics/media-pipeline.rst
"""
import functools
import hashlib
import os
import os.path
import time
import logging
from email.utils import parsedate_tz, mktime_tz
from six.moves.urllib.parse import urlparse
from collections import defaultdict
import six

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

from twisted.internet import defer, threads

from scrapy.pipelines.media import MediaPipeline
from scrapy.settings import Settings
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import Request
from scrapy.utils.misc import md5sum
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.python import to_bytes
from scrapy.utils.request import referer_str
from scrapy.utils.boto import is_botocore
from scrapy.utils.datatypes import CaselessDict

logger = logging.getLogger(__name__)


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

    POLICY = 'private'  # Overriden from settings.FILES_STORE_S3_ACL in
                        # FilesPipeline.from_settings.
    HEADERS = {
        'Cache-Control': 'max-age=172800',
    }

    def __init__(self, uri):
        self.is_botocore = is_botocore()
        if self.is_botocore:
            import botocore.session
            session = botocore.session.get_session()
            self.s3_client = session.create_client(
                's3', aws_access_key_id=self.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY)
        else:
            from boto.s3.connection import S3Connection
            self.S3Connection = S3Connection
        assert uri.startswith('s3://')
        self.bucket, self.prefix = uri[5:].split('/', 1)

    def stat_file(self, path, info):
        def _onsuccess(boto_key):
            if self.is_botocore:
                checksum = boto_key['ETag'].strip('"')
                last_modified = boto_key['LastModified']
                modified_stamp = time.mktime(last_modified.timetuple())
            else:
                checksum = boto_key.etag.strip('"')
                last_modified = boto_key.last_modified
                modified_tuple = parsedate_tz(last_modified)
                modified_stamp = int(mktime_tz(modified_tuple))
            return {'checksum': checksum, 'last_modified': modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_bucket(self):
        # disable ssl (is_secure=False) because of this python bug:
        # http://bugs.python.org/issue5103
        c = self.S3Connection(self.AWS_ACCESS_KEY_ID, self.AWS_SECRET_ACCESS_KEY, is_secure=False)
        return c.get_bucket(self.bucket, validate=False)

    def _get_boto_key(self, path):
        key_name = '%s%s' % (self.prefix, path)
        if self.is_botocore:
            return threads.deferToThread(
                self.s3_client.head_object,
                Bucket=self.bucket,
                Key=key_name)
        else:
            b = self._get_boto_bucket()
            return threads.deferToThread(b.get_key, key_name)

    def persist_file(self, path, buf, info, meta=None, headers=None):
        """Upload file to S3 storage"""
        key_name = '%s%s' % (self.prefix, path)
        buf.seek(0)
        if self.is_botocore:
            extra = self._headers_to_botocore_kwargs(self.HEADERS)
            if headers:
                extra.update(self._headers_to_botocore_kwargs(headers))
            return threads.deferToThread(
                self.s3_client.put_object,
                Bucket=self.bucket,
                Key=key_name,
                Body=buf,
                Metadata={k: str(v) for k, v in six.iteritems(meta or {})},
                ACL=self.POLICY,
                **extra)
        else:
            b = self._get_boto_bucket()
            k = b.new_key(key_name)
            if meta:
                for metakey, metavalue in six.iteritems(meta):
                    k.set_metadata(metakey, str(metavalue))
            h = self.HEADERS.copy()
            if headers:
                h.update(headers)
            return threads.deferToThread(
                k.set_contents_from_string, buf.getvalue(),
                headers=h, policy=self.POLICY)

    def _headers_to_botocore_kwargs(self, headers):
        """ Convert headers to botocore keyword agruments.
        """
        # This is required while we need to support both boto and botocore.
        mapping = CaselessDict({
            'Content-Type': 'ContentType',
            'Cache-Control': 'CacheControl',
            'Content-Disposition': 'ContentDisposition',
            'Content-Encoding': 'ContentEncoding',
            'Content-Language': 'ContentLanguage',
            'Content-Length': 'ContentLength',
            'Content-MD5': 'ContentMD5',
            'Expires': 'Expires',
            'X-Amz-Grant-Full-Control': 'GrantFullControl',
            'X-Amz-Grant-Read': 'GrantRead',
            'X-Amz-Grant-Read-ACP': 'GrantReadACP',
            'X-Amz-Grant-Write-ACP': 'GrantWriteACP',
            })
        extra = {}
        for key, value in six.iteritems(headers):
            try:
                kwarg = mapping[key]
            except KeyError:
                raise TypeError(
                    'Header "%s" is not supported by botocore' % key)
            else:
                extra[kwarg] = value
        return extra


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

    def __init__(self, store_uri, download_func=None, settings=None):
        if not store_uri:
            raise NotConfigured
        
        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)

        cls_name = "FilesPipeline"
        self.store = self._get_store(store_uri)
        resolve = functools.partial(self._key_for_pipe,
                                    base_class_name=cls_name)
        self.expires = settings.getint(
            resolve('FILES_EXPIRES'), self.EXPIRES
        )
        if not hasattr(self, "FILES_URLS_FIELD"):
            self.FILES_URLS_FIELD = self.DEFAULT_FILES_URLS_FIELD
        if not hasattr(self, "FILES_RESULT_FIELD"):
            self.FILES_RESULT_FIELD = self.DEFAULT_FILES_RESULT_FIELD
        self.files_urls_field = settings.get(
            resolve('FILES_URLS_FIELD'), self.FILES_URLS_FIELD
        )
        self.files_result_field = settings.get(
            resolve('FILES_RESULT_FIELD'), self.FILES_RESULT_FIELD
        )

        super(FilesPipeline, self).__init__(download_func=download_func)

    @classmethod
    def from_settings(cls, settings):
        s3store = cls.STORE_SCHEMES['s3']
        s3store.AWS_ACCESS_KEY_ID = settings['AWS_ACCESS_KEY_ID']
        s3store.AWS_SECRET_ACCESS_KEY = settings['AWS_SECRET_ACCESS_KEY']
        s3store.POLICY = settings['FILES_STORE_S3_ACL']

        store_uri = settings['FILES_STORE']
        return cls(store_uri, settings=settings)

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
            if age_days > self.expires:
                return  # returning None force download

            referer = referer_str(request)
            logger.debug(
                'File (uptodate): Downloaded %(medianame)s from %(request)s '
                'referred in <%(referer)s>',
                {'medianame': self.MEDIA_NAME, 'request': request,
                 'referer': referer},
                extra={'spider': info.spider}
            )
            self.inc_stats(info.spider, 'uptodate')

            checksum = result.get('checksum', None)
            return {'url': request.url, 'path': path, 'checksum': checksum}

        path = self.file_path(request, info=info)
        dfd = defer.maybeDeferred(self.store.stat_file, path, info)
        dfd.addCallbacks(_onsuccess, lambda _: None)
        dfd.addErrback(
            lambda f:
            logger.error(self.__class__.__name__ + '.store.stat_file',
                         exc_info=failure_to_exc_info(f),
                         extra={'spider': info.spider})
        )
        return dfd

    def media_failed(self, failure, request, info):
        if not isinstance(failure.value, IgnoreRequest):
            referer = referer_str(request)
            logger.warning(
                'File (unknown-error): Error downloading %(medianame)s from '
                '%(request)s referred in <%(referer)s>: %(exception)s',
                {'medianame': self.MEDIA_NAME, 'request': request,
                 'referer': referer, 'exception': failure.value},
                extra={'spider': info.spider}
            )

        raise FileException

    def media_downloaded(self, response, request, info):
        referer = referer_str(request)

        if response.status != 200:
            logger.warning(
                'File (code: %(status)s): Error downloading file from '
                '%(request)s referred in <%(referer)s>',
                {'status': response.status,
                 'request': request, 'referer': referer},
                extra={'spider': info.spider}
            )
            raise FileException('download-error')

        if not response.body:
            logger.warning(
                'File (empty-content): Empty file from %(request)s referred '
                'in <%(referer)s>: no-content',
                {'request': request, 'referer': referer},
                extra={'spider': info.spider}
            )
            raise FileException('empty-content')

        status = 'cached' if 'cached' in response.flags else 'downloaded'
        logger.debug(
            'File (%(status)s): Downloaded file from %(request)s referred in '
            '<%(referer)s>',
            {'status': status, 'request': request, 'referer': referer},
            extra={'spider': info.spider}
        )
        self.inc_stats(info.spider, status)

        try:
            path = self.file_path(request, response=response, info=info)
            checksum = self.file_downloaded(response, request, info)
        except FileException as exc:
            logger.warning(
                'File (error): Error processing file from %(request)s '
                'referred in <%(referer)s>: %(errormsg)s',
                {'request': request, 'referer': referer, 'errormsg': str(exc)},
                extra={'spider': info.spider}, exc_info=True
            )
            raise
        except Exception as exc:
            logger.error(
                'File (unknown-error): Error processing file from %(request)s '
                'referred in <%(referer)s>',
                {'request': request, 'referer': referer},
                exc_info=True, extra={'spider': info.spider}
            )
            raise FileException(str(exc))

        return {'url': request.url, 'path': path, 'checksum': checksum}

    def inc_stats(self, spider, status):
        spider.crawler.stats.inc_value('file_count', spider=spider)
        spider.crawler.stats.inc_value('file_status_count/%s' % status, spider=spider)

    ### Overridable Interface
    def get_media_requests(self, item, info):
        return [Request(x) for x in item.get(self.files_urls_field, [])]

    def file_downloaded(self, response, request, info):
        path = self.file_path(request, response=response, info=info)
        buf = BytesIO(response.body)
        checksum = md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum

    def item_completed(self, results, item, info):
        if isinstance(item, dict) or self.files_result_field in item.fields:
            item[self.files_result_field] = [x for ok, x in results if ok]
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

        media_guid = hashlib.sha1(to_bytes(url)).hexdigest()  # change to request.url after deprecation
        media_ext = os.path.splitext(url)[1]  # change to request.url after deprecation
        return 'full/%s%s' % (media_guid, media_ext)

    # deprecated
    def file_key(self, url):
        return self.file_path(url)
    file_key._base = True
