import time
import hmac
import base64
import hashlib
import rfc822
from cStringIO import StringIO

import Image

from scrapy import log
from scrapy.http import Request
from scrapy.stats import stats
from scrapy.core.exceptions import DropItem, NotConfigured, HttpException
from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.contrib.aws import canonical_string, sign_request
from scrapy.conf import settings

from .images import BaseImagesPipeline, NoimagesDrop, ImageException


class S3ImagesPipeline(BaseImagesPipeline):
    MEDIA_TYPE = 'image'
    THUMBS = (
        ("50", (50, 50)),
        ("110", (110, 110)),
        ("270", (270, 270))
    )

    def __init__(self):
        if not settings['S3_IMAGES']:
            raise NotConfigured

        self.bucket_name = settings['S3_BUCKET']
        self.prefix = settings['S3_PREFIX']
        self.access_key = settings['AWS_ACCESS_KEY_ID']
        self.secret_key = settings['AWS_SECRET_ACCESS_KEY']
        self.image_refresh_days = settings.getint('IMAGES_REFRESH_DAYS', 90)
        MediaPipeline.__init__(self)

    def s3request(self, key, method, body=None, headers=None):
        url = 'http://%s.s3.amazonaws.com/%s' % (self.bucket_name, key)
        req = Request(url, method=method, body=body, headers=headers)
        sign_request(req, self.access_key, self.secret_keself.secret_keyy)
        return req

    def image_downloaded(self, response, request, info):
        try:
            key = self.s3_image_key(request.url)
            self.s3_store_image(response, request.url, info)
        except ImageException, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex
        except Exception, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex

        return key # success value sent as input result for item_media_downloaded

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

    def media_to_download(self, request, info):
        """Return if the image should be downloaded by checking if it's already in
        the S3 storage and not too old"""

        def _on200(response):
            if 'Last-Modified' not in response.headers:
                return True

            last_modified = response.headers['Last-Modified'][0]
            modified_tuple = rfc822.parsedate_tz(last_modified)
            modified_stamp = int(rfc822.mktime_tz(modified_tuple))
            age_seconds = time.time() - modified_stamp
            age_days = age_seconds / 60 / 60 / 24
            return age_days > self.image_refresh_days

        def _non200(_failure):
            return True

        def _evaluate(should):
            if not should:
                self.inc_stats(info.domain, 'uptodate')
                referer = request.headers.get('Referer')
                log.msg('Image (uptodate) type=%s at <%s> referred from <%s>' % \
                        (self.MEDIA_TYPE, request.url, referer), level=log.DEBUG, domain=info.domain)
                return key

        key = self.s3_image_key(request.url)
        req = self.s3request(key, method='HEAD')
        dfd = self.download(req, info)
        dfd.addCallbacks(_on200, _non200)
        dfd.addCallback(_evaluate)
        dfd.addErrback(log.err, 'S3ImagesPipeline.media_to_download')
        return dfd

    def s3_store_image(self, response, url, info):
        """Upload image to S3 storage"""
        buf = StringIO(response.body.to_string())
        image = Image.open(buf)
        key = self.s3_image_key(url)
        self._s3_put_image(image, key, info)
        self.s3_store_thumbnails(image, url, info)

    def s3_store_thumbnails(self, image, url, info):
        """Upload image thumbnails to S3 storage"""
        for thumb_id, size in self.THUMBS or []:
            thumb = image.copy() if image.mode == 'RGB' else image.convert('RGB')
            thumb.thumbnail(size, Image.ANTIALIAS)
            key = self.s3_thumb_key(url, thumb_id)
            self._s3_put_image(thumb, key, info)

    def _s3_put_image(self, image, key, info):
        buf = StringIO()
        try:
            image.save(buf, 'JPEG')
        except Exception, ex:
            raise ImageException("Cannot process image. Error: %s" % ex)
        buf.seek(0)

        headers = {
                'Content-Type': 'image/jpeg',
                'X-Amz-Acl': 'public-read',
                }

        req = self.s3request(key, method='PUT', body=buf.read(), headers=headers)
        return self.download(req, info)


