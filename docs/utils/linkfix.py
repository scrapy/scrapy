"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""
from hashlib import sha1
from io import BytesIO
import warnings

from PIL import Image
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem, NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline
from scrapy.settings import Settings
from scrapy.utils.misc import md5sum
from scrapy.utils.python import to_bytes


class NoImagesDrop(DropItem):
    """Raise this exception if the product doesn't have images"""

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "The NoImagesDrop class is deprecated",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


class ImagesPipeline(FilesPipeline):
    """
    Abstract pipeline that implements the image thumbnail generation logic
    """

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH = 0
    MIN_HEIGHT = 0
    EXPIRES = 90
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"
    THUMBS = {}

    MEDIA_NAME = "image"

    def __init__(self, store_uri, download_func=None, settings=None):
        super().__init__(store_uri, settings=settings, download_func=download_func)

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)

        self.expires = settings.getint("IMAGES_EXPIRES", self.EXPIRES)
        self.images_urls_field = settings.get("IMAGES_URLS_FIELD",
            self.DEFAULT_IMAGES_URLS_FIELD)
        self.images_result_field = settings.get("IMAGES_RESULT_FIELD",
            self.DEFAULT_IMAGES_RESULT_FIELD)
        self.min_width = settings.getint("IMAGES_MIN_WIDTH",
            self.MIN_WIDTH)
        self.min_height = settings.getint("IMAGES_MIN_HEIGHT",
            self.MIN_HEIGHT)
        self.thumbs = settings.get("IMAGES_THUMBS", self.THUMBS)

        self._deprecated_convert_image = None

    @classmethod
    def from_settings(cls, settings):
        s3store = cls.STORE_SCHEMES["s3"]
        s3store.AWS_ACCESS_KEY_ID = settings["AWS_ACCESS_KEY_ID"]
        s3store.AWS_SECRET_ACCESS_KEY = settings["AWS_SECRET_ACCESS_KEY"]
        s3store.AWS_SESSION_TOKEN = settings["AWS_SESSION_TOKEN"]
        s3store.AWS_ENDPOINT_URL = settings["AWS_ENDPOINT_URL"]
        s3store.AWS_REGION_NAME = settings["AWS_REGION_NAME"]
        s3store.AWS_USE_SSL = settings["AWS_USE_SSL"]
        s3store.AWS_VERIFY = settings["AWS_VERIFY"]
        s3store.POLICY = settings["IMAGES_STORE_S3_ACL"]

        gcs_store = cls.STORE_SCHEMES["gs"]
        gcs_store.GCS_PROJECT_ID = settings["GCS_PROJECT_ID"]
        gcs_store.POLICY = settings.get("IMAGES_STORE_GCS_ACL", None)

        ftp_store = cls.STORE_SCHEMES["ftp"]
        ftp_store.FTP_USERNAME = settings["FTP_USER"]
        ftp_store.FTP_PASSWORD = settings["FTP_PASSWORD"]
        ftp_store.USE_ACTIVE_MODE = settings.getbool("FEED_STORAGE_FTP_ACTIVE")

        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, settings=settings)

    def file_downloaded(self, response, request, info, *, item=None):
        return self.image_downloaded(response, request, info, item=item)

    def image_downloaded(self, response, request, info, *, item=None):
        checksum = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        return checksum

    def get_images(self, response, request, info, *, item=None):
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = Image.open(BytesIO(response.body))

        width, height = orig_image.size
        if width < self.min_width or height < self.min_height:
            raise FileException(
                f"Image too small ({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        if self._deprecated_convert_image is None:
            self._deprecated_convert_image = "response_body" not in get_func_args(
                self.convert_image
            )
            if self._deprecated_convert_image:
                warnings.warn(
                    f"{self.__class__.__name__}.convert_image() method overridden in a deprecated way, "
                    "overridden method does not accept response_body argument.",
                    category=ScrapyDeprecationWarning,
                )

        if self._deprecated_convert_image:
            image, buf = self.convert_image(orig_image)
        else:
            image, buf = self.convert_image(
                orig_image, response_body=BytesIO(response.body)
            )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            if self._deprecated_convert_image:
                thumb_image, thumb_buf = self.convert_image(image, size)
            else:
                thumb_image, thumb_buf = self.convert_image(image, size, buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(self, image, size=None, response_body=None):
        if response_body is None:
            warnings.warn(
                f"{self.__class__.__name__}.convert_image() method called in a deprecated way, "
                "method called without response_body argument.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                resampling_filter = Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = Image.ANTIALIAS
            image.thumbnail(size, resampling_filter)
        elif response_body is not None and image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(self, results, item, info):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(self, request, response=None, info=None, *, item=None):
        image_guid = sha1(to_bytes(request.url)).hexdigest()
        return f"full/{image_guid}.jpg"

    def thumb_path(self, request, thumb_id, response=None, info=None, *, item=None):
        thumb_guid = sha1(to_bytes(request.url)).hexdigest()
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"