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
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import DropItem, NotConfigured, HttpException
from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.contrib.aws import sign_request
from scrapy.conf import settings

from .images import BaseImagesPipeline, NoimagesDrop, ImageException


def md5sum(buffer):
    m = hashlib.md5()
    buffer.seek(0)
    while 1:
        d = buffer.read(8096)
        if not d: break
        m.update(d)
    return m.hexdigest()


class S3ImagesPipeline(BaseImagesPipeline):
    MEDIA_TYPE = 'image'
    THUMBS = (
#             ('50', (50, 50)),
#             ('110', (110, 110)),
#             ('270', (270, 270))
    )

    # Automatically sign requests with AWS authorization header,
    # alternative we can do this using scrapy.contrib.aws.AWSMiddleware
    sign_requests = True

    s3_custom_spider = None

    def __init__(self):
        if not settings['S3_IMAGES']:
            raise NotConfigured

        self.bucket_name = settings['S3_BUCKET']
        self.prefix = settings['S3_PREFIX']
        self.access_key = settings['AWS_ACCESS_KEY_ID']
        self.secret_key = settings['AWS_SECRET_ACCESS_KEY']
        self.image_refresh_days = settings.getint('IMAGES_EXPIRES', 90)
        MediaPipeline.__init__(self)

    def s3_request(self, key, method, body=None, headers=None):
        url = 'http://%s.s3.amazonaws.com/%s%s' % (self.bucket_name, self.prefix, key)
        req = Request(url, method=method, body=body, headers=headers)
        if self.sign_requests:
            sign_request(req, self.access_key, self.secret_key)
        return req

    def image_downloaded(self, response, request, info):
        try:
            key = self.s3_image_key(request.url)
            etag = self.s3_store_image(response, request.url, info)
        except ImageException, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex
        except Exception, ex:
            log.msg(str(ex), level=log.WARNING, domain=info.domain)
            raise ex

        return '%s#%s' % (key, etag) # success value sent as input result for item_media_downloaded

    def s3_image_key(self, url):
        """Return the relative path on the target filesystem for an image to be
        downloaded to.
        """
        image_guid = hashlib.sha1(url).hexdigest()
        return 'full/%s.jpg' % (image_guid)

    def s3_thumb_key(self, url, thumb_id):
        """Return the relative path on the target filesystem for an image to be
        downloaded to.
        """
        image_guid = hashlib.sha1(url).hexdigest()
        return 'thumbs/%s/%s.jpg' % (thumb_id, image_guid)

    def media_to_download(self, request, info):
        """Return if the image should be downloaded by checking if it's already in
        the S3 storage and not too old"""

        def _onsuccess(response):
            if 'Last-Modified' not in response.headers:
                return # returning None force download

            # check if last modified date did not expires
            last_modified = response.headers['Last-Modified'][0]
            modified_tuple = rfc822.parsedate_tz(last_modified)
            modified_stamp = int(rfc822.mktime_tz(modified_tuple))
            age_seconds = time.time() - modified_stamp
            age_days = age_seconds / 60 / 60 / 24

            if age_days > self.image_refresh_days:
                return # returning None force download

            etag = response.headers['Etag'][0].strip('"')
            referer = request.headers.get('Referer')
            log.msg('Image (uptodate) type=%s at <%s> referred from <%s>' % \
                    (self.MEDIA_TYPE, request.url, referer), level=log.DEBUG, domain=info.domain)

            self.inc_stats(info.domain, 'uptodate')
            return '%s#%s' % (key, etag)

        key = self.s3_image_key(request.url)
        req = self.s3_request(key, method='HEAD')
        dfd = self.s3_download(req, info)
        dfd.addCallbacks(_onsuccess, lambda _:None)
        dfd.addErrback(log.err, 'S3ImagesPipeline.media_to_download')
        return dfd

    def s3_store_image(self, response, url, info):
        """Upload image to S3 storage"""
        buf = StringIO(response.body.to_string())
        image = Image.open(buf)
        key = self.s3_image_key(url)
        _, jpegbuf = self._s3_put_image(image, key, info)
        self.s3_store_thumbnails(image, url, info)
        return md5sum(jpegbuf) # Etag

    def s3_store_thumbnails(self, image, url, info):
        """Upload image thumbnails to S3 storage"""
        for thumb_id, size in self.THUMBS or []:
            thumb = image.copy() if image.mode == 'RGB' else image.convert('RGB')
            thumb.thumbnail(size, Image.ANTIALIAS)
            key = self.s3_thumb_key(url, thumb_id)
            self._s3_put_image(thumb, key, info)

    def _s3_put_image(self, image, key, info):
        if image.mode != 'RGB':
            image = image.convert('RGB')

        buf = StringIO()
        try:
            image.save(buf, 'JPEG')
        except Exception, ex:
            raise ImageException("Cannot process image. Error: %s" % ex)

        width, height = image.size
        headers = {
                'Content-Type': 'image/jpeg',
                'X-Amz-Acl': 'public-read',
                'X-Amz-Meta-Width': str(width),
                'X-Amz-Meta-Height': str(height),
                'Cache-Control': 'max-age=172800',
                }

        buf.seek(0)
        req = self.s3_request(key, method='PUT', body=buf.read(), headers=headers)
        return self.s3_download(req, info), buf

    def s3_download(self, request, info):
        """This method is used for HEAD and PUT requests sent to amazon S3

        It tries to use a specific spider domain for uploads, or defaults
        to current domain spider.

        """
        if self.s3_custom_spider:
            return scrapyengine.schedule(request, self.s3_custom_spider)
        return self.download(request, info)


