import time
import hashlib
import rfc822
from cStringIO import StringIO

import Image
import boto

from scrapy import log
from scrapy.stats import stats
from scrapy.core.exceptions import DropItem, NotConfigured
from scrapy.core.exceptions import HttpException
from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.conf import settings

class NoimagesDrop(DropItem):
    """Product with no images exception"""

class ImageException(Exception):
    """General image error exception"""

class S3ImagesPipeline(MediaPipeline):
    MEDIA_TYPE = 'image'
    THUMBS = (
        ("50", (50, 50)),
        ("110", (110, 110)),
        ("270", (270, 270))
    )

    def __init__(self):
        if not settings['S3_IMAGES']:
            raise NotConfigured

        # days to wait before redownloading images
        self.image_refresh_days = settings.getint('IMAGES_REFRESH_DAYS', 90)
        
        self.bucket_name = settings['S3_BUCKET']
        self.prefix = settings['S3_PREFIX']
        access_key = settings['AWS_ACCESS_KEY_ID']
        secret_key = settings['AWS_SECRET_ACCESS_KEY']
        conn = boto.connect_s3(access_key, secret_key)
        self.bucket = conn.get_bucket(self.bucket_name)

        MediaPipeline.__init__(self)

    def media_to_download(self, request, info):
        key = self.s3_image_key(request.url)
        if not self.s3_should_download(request.url):
            self.inc_stats(info.domain, 'uptodate')
            referer = request.headers.get('Referer')
            log.msg('Image (uptodate) type=%s at <%s> referred from <%s>' % \
                    (self.MEDIA_TYPE, request.url, referer), level=log.DEBUG, domain=info.domain)
            return key

    def media_downloaded(self, response, request, info):
        mtype = self.MEDIA_TYPE
        referer = request.headers.get('Referer')

        if not response or not response.body.to_string():
            msg = 'Image (empty): Empty %s (no content) in %s referred in <%s>: Empty image (no-content)' % (mtype, request, referer)
            log.msg(msg, level=log.WARNING, domain=info.domain)
            raise ImageException(msg)

        result = self.save_image(response, request, info) # save and thumbs response

        status = 'cached' if getattr(response, 'cached', False) else 'downloaded'
        msg = 'Image (%s): Downloaded %s from %s referred in <%s>' % (status, mtype, request, referer)
        log.msg(msg, level=log.DEBUG, domain=info.domain)
        self.inc_stats(info.domain, status)
        return result

    def media_failed(self, failure, request, info):
        referer = request.headers.get('Referer')
        errmsg = str(failure.value) if isinstance(failure.value, HttpException) else str(failure)
        msg = 'Image (http-error): Error downloading %s from %s referred in <%s>: %s' % (self.MEDIA_TYPE, request, referer, errmsg)
        log.msg(msg, level=log.WARNING, domain=info.domain)
        raise ImageException(msg)

    def save_image(self, response, request, info):
        try:
            key = self.s3_image_key(request.url)
            self.s3_store_image(response, request.url)
        except ImageException, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex
        except Exception, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex

        return key # success value sent as input result for item_media_downloaded

    def inc_stats(self, domain, status):
        stats.incpath('%s/image_count' % domain)
        stats.incpath('%s/image_status_count/%s' % (domain, status))

    def s3_image_key(self, url):
        """Return the relative path on the target filesystem for an image to be
        downloaded to.
        """
        image_guid = hashlib.sha1(url).hexdigest()
        return '%s/full/%s.jpg' % (self.prefix, image_guid)

    def s3_thumb_key(self, url, thumb_id):
        """Return the relative path on the target filesystem for an image to be
        downloaded to.
        """
        image_guid = hashlib.sha1(url).hexdigest()
        return '%s/thumbs/%s/%s.jpg' % (self.prefix, thumb_id, image_guid)

    def s3_should_download(self, url):
        """Return if the image should be downloaded by checking if it's already in
        the S3 storage and not too old"""
        key = self.s3_image_key(url)
        k = self.bucket.get_key(key)
        if k is None:
            return True
        modified_tuple = rfc822.parsedate_tz(k.last_modified)
        modified_stamp = int(rfc822.mktime_tz(modified_tuple))
        age_seconds = time.time() - modified_stamp
        age_days = age_seconds / 60 / 60 / 24
        return age_days > self.image_refresh_days

    def s3_store_image(self, response, url):
        """Upload image to S3 storage"""
        buf = StringIO(response.body.to_string())
        image = Image.open(buf)
        key = self.s3_image_key(url)
        self._s3_put_image(image, key)
        self.s3_store_thumbnails(image, url)

    def s3_store_thumbnails(self, image, url):
        """Upload image thumbnails to S3 storage"""
        for thumb_id, size in self.THUMBS or []:
            thumb = image.copy() if image.mode == 'RGB' else image.convert('RGB')
            thumb.thumbnail(size, Image.ANTIALIAS)
            key = self.s3_thumb_key(url, thumb_id)
            self._s3_put_image(thumb, key)

    def s3_public_url(self, key):
        return "http://%s.s3.amazonaws.com/%s" % (self.bucket_name, key)

    def _s3_put_image(self, image, key):
        buf = StringIO()
        try:
            image.save(buf, 'JPEG')
        except Exception, ex:
            raise ImageException("Cannot process image. Error: %s" % ex)

        buf.seek(0)
        k = self.bucket.new_key(key)
        k.content_type = 'image/jpeg'
        k.set_contents_from_file(buf, policy='public-read')
        log.msg("Uploaded to S3: %s" % self.s3_public_url(key), level=log.DEBUG)

