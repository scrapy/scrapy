"""
Images Pipeline

See documentation in topics/media-pipeline.rst
"""

from __future__ import annotations

import functools
import hashlib
import warnings
from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING, Any

from itemadapter import ItemAdapter

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FileException, FilesPipeline, _md5sum
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable
    from os import PathLike

    from PIL import Image

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.pipelines.media import FileInfoOrError, MediaPipeline


class ImageException(FileException):
    """General image error exception"""


class ImagesPipeline(FilesPipeline):
    """Abstract pipeline that implement the image thumbnail generation logic"""

    MEDIA_NAME: str = "image"

    # Uppercase attributes kept for backward compatibility with code that subclasses
    # ImagesPipeline. They may be overridden by settings.
    MIN_WIDTH: int = 0
    MIN_HEIGHT: int = 0
    EXPIRES: int = 90
    THUMBS: dict[str, tuple[int, int]] = {}
    DEFAULT_IMAGES_URLS_FIELD = "image_urls"
    DEFAULT_IMAGES_RESULT_FIELD = "images"

    def __init__(
        self,
        store_uri: str | PathLike[str],
        download_func: None = None,
        *,
        crawler: Crawler,
    ):
        if download_func is not None:  # pragma: no cover
            warnings.warn(
                "The download_func argument of ImagesPipeline.__init__() is ignored"
                " and will be removed in a future Scrapy version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        try:
            from PIL import Image, ImageOps  # noqa: PLC0415

            self._Image = Image
            self._ImageOps = ImageOps
        except ImportError:
            raise NotConfigured(
                "ImagesPipeline requires installing Pillow 8.3.2 or later"
            )

        super().__init__(store_uri, crawler=crawler)

        settings = crawler.settings
        resolve = functools.partial(
            self._key_for_pipe,
            base_class_name="ImagesPipeline",
            settings=settings,
        )
        self.expires: int = settings.getint(resolve("IMAGES_EXPIRES"), self.EXPIRES)

        if not hasattr(self, "IMAGES_RESULT_FIELD"):
            self.IMAGES_RESULT_FIELD: str = self.DEFAULT_IMAGES_RESULT_FIELD
        if not hasattr(self, "IMAGES_URLS_FIELD"):
            self.IMAGES_URLS_FIELD: str = self.DEFAULT_IMAGES_URLS_FIELD

        self.images_urls_field: str = settings.get(
            resolve("IMAGES_URLS_FIELD"), self.IMAGES_URLS_FIELD
        )
        self.images_result_field: str = settings.get(
            resolve("IMAGES_RESULT_FIELD"), self.IMAGES_RESULT_FIELD
        )
        self.min_width: int = settings.getint(
            resolve("IMAGES_MIN_WIDTH"), self.MIN_WIDTH
        )
        self.min_height: int = settings.getint(
            resolve("IMAGES_MIN_HEIGHT"), self.MIN_HEIGHT
        )
        self.thumbs: dict[str, tuple[int, int]] = settings.get(
            resolve("IMAGES_THUMBS"), self.THUMBS
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        cls._update_stores(settings)
        store_uri = settings["IMAGES_STORE"]
        return cls(store_uri, crawler=crawler)

    def file_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        return self.image_downloaded(response, request, info, item=item)

    def image_downloaded(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> str:
        checksum: str | None = None
        for path, image, buf in self.get_images(response, request, info, item=item):
            if checksum is None:
                buf.seek(0)
                checksum = _md5sum(buf)
            width, height = image.size
            self.store.persist_file(
                path,
                buf,
                info,
                meta={"width": width, "height": height},
                headers={"Content-Type": "image/jpeg"},
            )
        assert checksum is not None
        return checksum

    def get_images(
        self,
        response: Response,
        request: Request,
        info: MediaPipeline.SpiderInfo,
        *,
        item: Any = None,
    ) -> Iterable[tuple[str, Image.Image, BytesIO]]:
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = self._Image.open(BytesIO(response.body))
        transposed_image = self._ImageOps.exif_transpose(orig_image)

        width, height = transposed_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            transposed_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, response_body=buf)
            yield thumb_path, thumb_image, thumb_buf

    def convert_image(
        self,
        image: Image.Image,
        size: tuple[int, int] | None = None,
        *,
        response_body: BytesIO,
    ) -> tuple[Image.Image, BytesIO]:
        if image.format in ("PNG", "WEBP") and image.mode == "RGBA":
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA")
            background = self._Image.new("RGBA", image.size, (255, 255, 255))
            background.paste(image, image)
            image = background.convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS  # type: ignore[attr-defined]
            image.thumbnail(size, resampling_filter)
        elif image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.save(buf, "JPEG")
        return image, buf

    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        if not isinstance(urls, list):
            raise TypeError(
                f"{self.images_urls_field} must be a list of URLs, got {type(urls).__name__}. "
            )
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def item_completed(
        self, results: list[FileInfoOrError], item: Any, info: MediaPipeline.SpiderInfo
    ) -> Any:
        with suppress(KeyError):
            ItemAdapter(item)[self.images_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(
        self,
        request: Request,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"full/{image_guid}.jpg"

    def thumb_path(
        self,
        request: Request,
        thumb_id: str,
        response: Response | None = None,
        info: MediaPipeline.SpiderInfo | None = None,
        *,
        item: Any = None,
    ) -> str:
        thumb_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()  # noqa: S324
        return f"thumbs/{thumb_id}/{thumb_guid}.jpg"
