"""
Images Pipeline

See documentation in topics/images.rst
"""

import hashlib
from cStringIO import StringIO

from PIL import Image

from scrapy.utils.misc import md5sum
from scrapy.http import Request
from scrapy.exceptions import DropItem
#TODO: from scrapy.contrib.pipeline.media import MediaPipeline
from scrapy.contrib.pipeline.files import FileException, FilesPipeline


class NoimagesDrop(DropItem):
    """Product with no images exception"""


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic

    """

    MEDIA_NAME = 'image'
    MIN_WIDTH = 0
    MIN_HEIGHT = 0
    THUMBS = {}
    DEFAULT_IMAGES_URLS_FIELD = 'image_urls'
    DEFAULT_IMAGES_RESULT_FIELD = 'images'

    @classmethod
    def from_settings(cls, settings):
        cls.MIN_WIDTH = settings.getint('IMAGES_MIN_WIDTH', 0)
        cls.MIN_HEIGHT = settings.getint('IMAGES_MIN_HEIGHT', 0)
        cls.EXPIRES = settings.getint('IMAGES_EXPIRES', 90)
        cls.THUMBS = settings.get('IMAGES_THUMBS', {})
        s3store = cls.STORE_SCHEMES['s3']
        s3store.AWS_ACCESS_KEY_ID = settings['AWS_ACCESS_KEY_ID']
        s3store.AWS_SECRET_ACCESS_KEY = settings['AWS_SECRET_ACCESS_KEY']

        cls.IMAGES_URLS_FIELD = settings.get('IMAGES_URLS_FIELD', cls.DEFAULT_IMAGES_URLS_FIELD)
        cls.IMAGES_RESULT_FIELD = settings.get('IMAGES_RESULT_FIELD', cls.DEFAULT_IMAGES_RESULT_FIELD)
        store_uri = settings['IMAGES_STORE']
        return cls(store_uri)

    def file_downloaded(self, response, request, info):
        return self.image_downloaded(response, request, info)

    def image_downloaded(self, response, request, info):
        checksum = None
        for path, image, buf in self.get_images(response, request, info):
            if checksum is None:
                buf.seek(0)
                checksum = md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path, buf, info,
                meta={'width': width, 'height': height},
                headers={'Content-Type': 'image/jpeg'})
        return checksum

    def get_images(self, response, request, info):
        path = self.file_path(request, response=response, info=info)
        orig_image = Image.open(StringIO(response.body))

        width, height = orig_image.size
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            raise ImageException("Image too small (%dx%d < %dx%d)" %
                                 (width, height, self.MIN_WIDTH, self.MIN_HEIGHT))

        image, buf = self.convert_image(orig_image)
        yield path, image, buf

        for thumb_id, size in self.THUMBS.iteritems():
            thumb_path = self.thumb_path(request, thumb_id, response=response, info=info)
            thumb_image, thumb_buf = self.convert_image(image, size)
            yield thumb_path, thumb_image, thumb_buf

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

    def get_media_requests(self, item, info):
        return [Request(x) for x in item.get(self.IMAGES_URLS_FIELD, [])]

    def item_completed(self, results, item, info):
        if self.IMAGES_RESULT_FIELD in item.fields:
            item[self.IMAGES_RESULT_FIELD] = [x for ok, x in results if ok]
        return item

    def file_path(self, request, response=None, info=None):
        return self.file_key(request.url)

    def thumb_path(self, request, thumb_id, response=None, info=None):
        return self.thumb_key(request.url)

    # deprecated
    def file_key(self, url):
        return self.image_key(url)

    # deprecated
    def image_key(self, url):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'full/%s.jpg' % (image_guid)

    # deprecated
    def thumb_key(self, url, thumb_id):
        thumb_guid = hashlib.sha1(url).hexdigest()
        return 'thumbs/%s/%s.jpg' % (thumb_id, thumb_guid)
