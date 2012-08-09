"""
Images Pipeline

See documentation in topics/images.rst
"""

import os
import time
import hashlib
import urlparse
import rfc822
from cStringIO import StringIO
from collections import defaultdict

from twisted.internet import defer, threads
from PIL import Image

from scrapy import log
from scrapy.utils.misc import md5sum
from scrapy.http import Request
from scrapy.exceptions import DropItem, NotConfigured, IgnoreRequest
from scrapy.contrib.pipeline.media import MediaPipeline


class NoimagesDrop(DropItem):
    """Product with no images exception"""

class ImageException(Exception):
    """General image error exception"""


class FSImagesStore(object):

    def __init__(self, basedir):
        if '://' in basedir:
            basedir = basedir.split('://', 1)[1]
        self.basedir = basedir
        self._mkdir(self.basedir)
        self.created_directories = defaultdict(set)

    def persist_image(self, key, image, buf, info):
        absolute_path = self._get_filesystem_path(key)
        self._mkdir(os.path.dirname(absolute_path), info)
        image.save(absolute_path)

    def stat_image(self, key, info):
        absolute_path = self._get_filesystem_path(key)
        try:
            last_modified = os.path.getmtime(absolute_path)
        except: # FIXME: catching everything!
            return {}

        with open(absolute_path, 'rb') as imagefile:
            checksum = md5sum(imagefile)

        return {'last_modified': last_modified, 'checksum': checksum}

    def _get_filesystem_path(self, key):
        path_comps = key.split('/')
        return os.path.join(self.basedir, *path_comps)

    def _mkdir(self, dirname, domain=None):
        seen = self.created_directories[domain] if domain else set()
        if dirname not in seen:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            seen.add(dirname)


class S3ImagesStore(object):

    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None

    POLICY = 'public-read'
    HEADERS = {
            'Cache-Control': 'max-age=172800',
            'Content-Type': 'image/jpeg',
            }

    def __init__(self, uri):
        assert uri.startswith('s3://')
        self.bucket, self.prefix = uri[5:].split('/', 1)

    def stat_image(self, key, info):
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

    def persist_image(self, key, image, buf, info):
        """Upload image to S3 storage"""
        width, height = image.size
        b = self._get_boto_bucket()
        key_name = '%s%s' % (self.prefix, key)
        k = b.new_key(key_name)
        k.set_metadata('width', str(width))
        k.set_metadata('height', str(height))
        buf.seek(0)
        return threads.deferToThread(k.set_contents_from_file, buf, \
                headers=self.HEADERS, policy=self.POLICY)


class ImagesPipeline(MediaPipeline):
    """Abstract pipeline that implement the image downloading and thumbnail generation logic

    This pipeline tries to minimize network transfers and image processing,
    doing stat of the images and determining if image is new, uptodate or
    expired.

    `new` images are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    `uptodate` images are the ones that the pipeline processed and are still
        valid images.

    `expired` images are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME = 'image'
    MIN_WIDTH = 0
    MIN_HEIGHT = 0
    EXPIRES = 90
    THUMBS = {}
    STORE_SCHEMES = {
            '': FSImagesStore,
            'file': FSImagesStore,
            's3': S3ImagesStore,
            }

    def __init__(self, store_uri, download_func=None):
        if not store_uri:
            raise NotConfigured
        self.store = self._get_store(store_uri)
        super(ImagesPipeline, self).__init__(download_func=download_func)

    @classmethod
    def from_settings(cls, settings):
        cls.MIN_WIDTH = settings.getint('IMAGES_MIN_WIDTH', 0)
        cls.MIN_HEIGHT = settings.getint('IMAGES_MIN_HEIGHT', 0)
        cls.EXPIRES = settings.getint('IMAGES_EXPIRES', 90)
        cls.THUMBS = settings.get('IMAGES_THUMBS', {})
        s3store = cls.STORE_SCHEMES['s3']
        s3store.AWS_ACCESS_KEY_ID = settings['AWS_ACCESS_KEY_ID']
        s3store.AWS_SECRET_ACCESS_KEY = settings['AWS_SECRET_ACCESS_KEY']
        store_uri = settings['IMAGES_STORE']
        return cls(store_uri)

    def _get_store(self, uri):
        if os.path.isabs(uri): # to support win32 paths like: C:\\some\dir
            scheme = 'file'
        else:
            scheme = urlparse.urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_downloaded(self, response, request, info):
        referer = request.headers.get('Referer')

        if response.status != 200:
            log.msg(format='Image (code: %(status)s): Error downloading image from %(request)s referred in <%(referer)s>',
                    level=log.WARNING, spider=info.spider,
                    status=response.status, request=request, referer=referer)
            raise ImageException

        if not response.body:
            log.msg(format='Image (empty-content): Empty image from %(request)s referred in <%(referer)s>: no-content',
                    level=log.WARNING, spider=info.spider,
                    request=request, referer=referer)
            raise ImageException

        status = 'cached' if 'cached' in response.flags else 'downloaded'
        log.msg(format='Image (%(status)s): Downloaded image from %(request)s referred in <%(referer)s>',
                level=log.DEBUG, spider=info.spider,
                status=status, request=request, referer=referer)
        self.inc_stats(info.spider, status)

        try:
            key = self.image_key(request.url)
            checksum = self.image_downloaded(response, request, info)
        except ImageException, ex:
            log.err('image_downloaded hook failed',
                    level=log.WARNING, spider=info.spider)
            raise
        except Exception:
            log.err(spider=info.spider)
            raise ImageException

        return {'url': request.url, 'path': key, 'checksum': checksum}

    def media_failed(self, failure, request, info):
        if not isinstance(failure.value, IgnoreRequest):
            referer = request.headers.get('Referer')
            log.msg(format='Image (unknown-error): Error downloading '
                           '%(medianame)s from %(request)s referred in '
                           '<%(referer)s>: %(exception)s',
                    level=log.WARNING, spider=info.spider, exception=failure.value,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)

        raise ImageException

    def media_to_download(self, request, info):
        def _onsuccess(result):
            if not result:
                return # returning None force download

            last_modified = result.get('last_modified', None)
            if not last_modified:
                return # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.EXPIRES:
                return # returning None force download

            referer = request.headers.get('Referer')
            log.msg(format='Image (uptodate): Downloaded %(medianame)s from %(request)s referred in <%(referer)s>',
                    level=log.DEBUG, spider=info.spider,
                    medianame=self.MEDIA_NAME, request=request, referer=referer)
            self.inc_stats(info.spider, 'uptodate')

            checksum = result.get('checksum', None)
            return {'url': request.url, 'path': key, 'checksum': checksum}

        key = self.image_key(request.url)
        dfd = defer.maybeDeferred(self.store.stat_image, key, info)
        dfd.addCallbacks(_onsuccess, lambda _:None)
        dfd.addErrback(log.err, self.__class__.__name__ + '.store.stat_image')
        return dfd

    def image_downloaded(self, response, request, info):
        checksum = None
        for key, image, buf in self.get_images(response, request, info):
            if checksum is None:
                buf.seek(0)
                checksum = md5sum(buf)
            self.store.persist_image(key, image, buf, info)
        return checksum

    def get_images(self, response, request, info):
        key = self.image_key(request.url)
        orig_image = Image.open(StringIO(response.body))

        width, height = orig_image.size
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            raise ImageException("Image too small (%dx%d < %dx%d): %s" % \
                    (width, height, self.MIN_WIDTH, self.MIN_HEIGHT, response.url))

        image, buf = self.convert_image(orig_image)
        yield key, image, buf

        for thumb_id, size in self.THUMBS.iteritems():
            thumb_key = self.thumb_key(request.url, thumb_id)
            thumb_image, thumb_buf = self.convert_image(image, size)
            yield thumb_key, thumb_image, thumb_buf

    def inc_stats(self, spider, status):
        spider.crawler.stats.inc_value('image_count', spider=spider)
        spider.crawler.stats.inc_value('image_status_count/%s' % status, spider=spider)

    def convert_image(self, image, size=None):
        if image.format == 'PNG' and image.mode == 'RGBA':
            background = Image.new('RGBA', image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert('RGB')
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        if size:
            image = image.copy()
            image.thumbnail(size, Image.ANTIALIAS)

        buf = StringIO()
        try:
            image.save(buf, 'JPEG')
        except Exception, ex:
            raise ImageException("Cannot process image. Error: %s" % ex)

        return image, buf

    def image_key(self, url):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'full/%s.jpg' % (image_guid)

    def thumb_key(self, url, thumb_id):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'thumbs/%s/%s.jpg' % (thumb_id, image_guid)

    def get_media_requests(self, item, info):
        return [Request(x) for x in item.get('image_urls', [])]

    def item_completed(self, results, item, info):
        if 'images' in item.fields:
            item['images'] = [x for ok, x in results if ok]
        return item
