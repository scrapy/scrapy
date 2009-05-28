from __future__ import with_statement
import os
import time
import hashlib
import Image
from cStringIO import StringIO

from twisted.internet import defer

from scrapy import log
from scrapy.stats import stats
from scrapy.utils.misc import md5sum
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.conf import settings
from scrapy.contrib.pipeline.media import MediaPipeline


class NoimagesDrop(DropItem):
    """Product with no images exception"""

class ImageException(Exception):
    """General image error exception"""


class BaseImagesPipeline(MediaPipeline):
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

    IMAGES_EXPIRES setting controls the maximun days since an image was modified
    to consider it uptodate.

    THUMBS is a tuple of tuples, each sub-tuple is a pair of thumb_id string
    and a compatible python image library size (a tuple).
    See thumbnail method at http://www.pythonware.com/library/pil/handbook/image.htm

    Downloaded images are skipped if sizes aren't greater than MIN_WIDTH and
    MIN_HEIGHT limit. A proper log messages will be printed.

    """

    MIN_WIDTH = settings.getint('IMAGES_MIN_WIDTH', 0)
    MIN_HEIGHT = settings.getint('IMAGES_MIN_HEIGHT', 0)
    IMAGES_EXPIRES = settings.getint('IMAGES_EXPIRES', 90)
    MEDIA_NAME = 'image'
    THUMBS = (
#             ('50', (50, 50)),
#             ('110', (110, 110)),
#             ('270', (270, 270))
     )

    def media_downloaded(self, response, request, info):
        mtype = self.MEDIA_NAME
        referer = request.headers.get('Referer')

        if response.status != 200:
            msg = 'Image (http-error): Error downloading %s from %s referred in <%s>: %s' \
                    % (mtype, request, referer, errmsg)
            log.msg(msg, level=log.WARNING, domain=info.domain)
            raise ImageException(msg)

        if not response.body:
            msg = 'Image (empty-content): Empty %s from %s referred in <%s>: no-content' \
                    % (mtype, request, referer)
            log.msg(msg, level=log.WARNING, domain=info.domain)
            raise ImageException(msg)

        status = 'cached' if 'cached' in response.flags else 'downloaded'
        msg = 'Image (%s): Downloaded %s from %s referred in <%s>' % \
                (status, mtype, request, referer)
        log.msg(msg, level=log.DEBUG, domain=info.domain)
        self.inc_stats(info.domain, status)

        try:
            key = self.image_key(request.url)
            checksum = self.image_downloaded(response, request, info)
        except ImageException, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex
        except Exception, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex

        return '%s#%s' % (key, checksum) if checksum else key

    def media_failed(self, failure, request, info):
        referer = request.headers.get('Referer')
        msg = 'Image (unknow-error): Error downloading %s from %s referred in <%s>: %s' \
                % (self.MEDIA_NAME, request, referer, str(failure))
        log.msg(msg, level=log.WARNING, domain=info.domain)
        raise ImageException(msg)

    def media_to_download(self, request, info):
        def _onsuccess(result):
            if not result:
                return # returning None force download

            last_modified = result.get('last_modified', None)
            if not last_modified:
                return # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.IMAGES_EXPIRES:
                return # returning None force download

            referer = request.headers.get('Referer')
            log.msg('Image (uptodate): Downloaded %s from <%s> referred in <%s>' % \
                    (self.MEDIA_NAME, request.url, referer), level=log.DEBUG, domain=info.domain)
            self.inc_stats(info.domain, 'uptodate')

            checksum = result.get('checksum', None)
            return '%s#%s' % (key, checksum) if checksum else key

        key = self.image_key(request.url)
        dfd = defer.maybeDeferred(self.stat_key, key, info)
        dfd.addCallbacks(_onsuccess, lambda _:None)
        dfd.addErrback(log.err, self.__class__.__name__ + '.stat_key')
        return dfd

    def image_downloaded(self, response, request, info):
        first_buf = None
        for key, image, buf in self.get_images(response, request, info):
            self.store_image(key, image, buf, info)
            if first_buf is None:
                first_buf = buf
        return md5sum(first_buf)

    def get_images(self, response, request, info):
        key = self.image_key(request.url)
        orig_image = Image.open(StringIO(response.body))

        width, height = orig_image.size
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            raise ImageException("Image too small (%dx%d < %dx%d): %s" % \
                    (width, height, self.MIN_WIDTH, self.MIN_HEIGHT, response.url))

        image, buf = self.convert_image(orig_image)
        yield key, image, buf

        for thumb_id, size in self.THUMBS or []:
            thumb_key = self.thumb_key(request.url, thumb_id)
            thumb_image, thumb_buf = self.convert_image(image, size)
            yield thumb_key, thumb_image, thumb_buf

    def inc_stats(self, domain, status):
        stats.incpath('%s/image_count' % domain)
        stats.incpath('%s/image_status_count/%s' % (domain, status))

    def convert_image(self, image, size=None):
        if image.mode != 'RGB':
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

    # Required overradiable interface
    def store_image(self, key, image, buf, info):
        """Override this method with specific code to persist an image

        This method is used to persist the full image and any defined
        thumbnail, one a time.

        Return value is ignored.

        """
        raise NotImplementedError

    def stat_key(self, key, info):
        """Override this method with specific code to stat an image

        this method should return and dictionary with two parameters:
         * last_modified: the last modification time in seconds since the epoch
         * checksum: the md5sum of the content of the stored image if found

         If an exception is raised or last_modified is None, then the image
         will be re-downloaded.

         If the difference in days between last_modified and now is greater than
         IMAGES_EXPIRES settings, then the image will be re-downloaded

         The checksum value is appended to returned image path after a hash
         sign (#), if checksum is None, then nothing is appended including the
         hash sign.

        """
        raise NotImplementedError


class ImagesPipeline(BaseImagesPipeline):
    """Images pipeline with filesystem support as image's store backend

    If IMAGES_DIR setting has a valid value, this pipeline is enabled and use
    path defined at setting as dirname for storing images.

    """

    class DomainInfo(BaseImagesPipeline.DomainInfo):
        def __init__(self, domain):
            self.created_directories = set()
            super(ImagesPipeline.DomainInfo, self).__init__(domain)

    def __init__(self):
        if not settings['IMAGES_DIR']:
            raise NotConfigured

        self.BASEDIRNAME = settings['IMAGES_DIR']
        self.mkdir(self.BASEDIRNAME)
        super(ImagesPipeline, self).__init__()

    def store_image(self, key, image, buf, info):
        absolute_path = self.get_filesystem_path(key)
        self.mkdir(os.path.dirname(absolute_path), info)
        image.save(absolute_path)

    def stat_key(self, key, info):
        absolute_path = self.get_filesystem_path(key)
        try:
            last_modified = os.path.getmtime(absolute_path)
        except:
            return {}

        with open(absolute_path, 'rb') as imagefile:
            checksum = md5sum(imagefile)

        return {'last_modified': last_modified, 'checksum': checksum}

    def get_filesystem_path(self, key):
        return os.path.join(self.BASEDIRNAME, key)

    def mkdir(self, dirname, info=None):
        already_created = info.created_directories if info else set()
        if dirname not in already_created:
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            already_created.add(dirname)
