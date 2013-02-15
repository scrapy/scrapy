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
from scrapy.contrib.pipeline.files import FileMediaPipeline


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
        except:  # FIXME: catching everything!
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
        return threads.deferToThread(k.set_contents_from_file, buf,
                                     headers=self.HEADERS, policy=self.POLICY)


class ImagesPipeline(FileMediaPipeline):
    MEDIA_NAME = 'image'
    ITEM_MEDIA_URLS_KEY = 'image_urls'
    ITEM_MEDIA_RESULT_KEY = 'images'

    @classmethod
    def from_settings(cls, settings):
        cls.MIN_WIDTH = settings.getint('IMAGES_MIN_WIDTH', 0)
        cls.MIN_HEIGHT = settings.getint('IMAGES_MIN_HEIGHT', 0)
        cls.EXPIRES = settings.getint('IMAGES_EXPIRES', 90)
        cls.THUMBS = settings.get('IMAGES_THUMBS', {})
        cls.ORIGINAL_SAVE = settings.getbool('IMAGES_ORIGINAL_SAVE', False)
        cls.ORIGINAL_CONVERT = settings.getbool('IMAGES_ORIGINAL_CONVERT', True)
        cls.REPORT_DIMENSIONS = settings.getbool('IMAGES_REPORT_DIMENSIONS', False)
        s3store = cls.STORE_SCHEMES['s3']
        s3store.AWS_ACCESS_KEY_ID = settings['AWS_ACCESS_KEY_ID']
        s3store.AWS_SECRET_ACCESS_KEY = settings['AWS_SECRET_ACCESS_KEY']
        store_uri = settings['IMAGES_STORE']
        return cls(store_uri)

    def process_file_buffer(self, url, buf, info):
        image = Image.open(StringIO(buf))
        key = self._file_key(url)
        width, height = image.size
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            raise ImageException("Image too small (%dx%d < %dx%d)" %
                                 (width, height, self.MIN_WIDTH, self.MIN_HEIGHT))
        if self.ORIGINAL_SAVE:
            result = self.persist_image(self.origimage_key(url), image, buf, info)
            result.update({'url': url, 'tag': 'original'})
            yield result

        if self.ORIGINAL_CONVERT:
            convimage, convbuf = self.convert_image(image)
            result = self.persist_image(
                self.convimage_key(url),
                convimage, convbuf.getvalue(), info)
            result.update({'url': url, 'tag': 'converted'})
            yield result

        for thumb_id, size in self.THUMBS.iteritems():
            thumb_image, thumb_buf = self.convert_image(image, size)
            result = self.persist_image(
                self.thumb_key(url, thumb_id),
                thumb_image, thumb_buf.getvalue(), info)
            result.update({'url': url, 'tag': 'thumbnail'})
            yield result

    def persist_image(self, key, image, buf, info):
        width, height = image.size
        result = self.store.persist_file(
            key, buf, {'width' :  width, 'height': height}, info)
        if self.REPORT_DIMENSIONS:
            result.update({'width': width, 'height': height})
        result.update({'format': image.format})
        return result

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
        image.save(buf, 'JPEG')
        return image, buf

    def _file_key(self, url):
        if self.ORIGINAL_SAVE:
            return self.origimage_key(url)
        elif self.ORIGINAL_CONVERT:
            return self.convimage_key(url)
        # FIXME: if we only generate thumbnails,
        # the key should be the first thumbnail key
        else:
            return super(ImagesPipeline, self)._file_key(url)

    def origimage_key(self, url):
        return 'full/%s' % super(ImagesPipeline, self)._file_key(url)

    def image_key(self, url):
        return self.convimage_key(url)

    def convimage_key(self, url):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'full/%s.jpg' % image_guid

    def thumb_key(self, url, thumb_id):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'thumbs/%s/%s.jpg' % (thumb_id, image_guid)
