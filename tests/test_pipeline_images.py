from __future__ import annotations

import dataclasses
import io
import random
from shutil import rmtree
from tempfile import mkdtemp

import attr
import pytest
from itemadapter import ItemAdapter

from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.pipelines.images import ImageException, ImagesPipeline
from scrapy.utils.test import get_crawler

try:
    from PIL import Image
except ImportError:
    pytest.skip(
        "Missing Python Imaging Library, install https://pypi.org/pypi/Pillow",
        allow_module_level=True,
    )
else:
    encoders = {"jpeg_encoder", "jpeg_decoder"}
    if not encoders.issubset(set(Image.core.__dict__)):  # type: ignore[attr-defined]
        pytest.skip("Missing JPEG encoders", allow_module_level=True)


class TestImagesPipeline:
    def setup_method(self):
        self.tempdir = mkdtemp()
        crawler = get_crawler()
        self.pipeline = ImagesPipeline(self.tempdir, crawler=crawler)

    def teardown_method(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        assert (
            file_path(Request("https://dev.mydeco.com/mydeco.gif"))
            == "full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg"
        )
        assert (
            file_path(
                Request(
                    "http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.jpg"
                )
            )
            == "full/0ffcd85d563bca45e2f90becd0ca737bc58a00b2.jpg"
        )
        assert (
            file_path(
                Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.gif")
            )
            == "full/b250e3a74fff2e4703e310048a5b13eba79379d2.jpg"
        )
        assert (
            file_path(
                Request(
                    "http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg"
                )
            )
            == "full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532/"))
            == "full/97ee6f8a46cbbb418ea91502fd24176865cf39b2.jpg"
        )
        assert (
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532"))
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg"
        )
        assert (
            file_path(
                Request("http://www.dorma.co.uk/images/product_details/2532"),
                response=Response("http://www.dorma.co.uk/images/product_details/2532"),
                info=object(),
            )
            == "full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg"
        )

    def test_thumbnail_name(self):
        thumb_path = self.pipeline.thumb_path
        name = "50"
        assert (
            thumb_path(Request("file:///tmp/foo.jpg"), name)
            == "thumbs/50/38a86208c36e59d4404db9e37ce04be863ef0335.jpg"
        )
        assert (
            thumb_path(Request("file://foo.png"), name)
            == "thumbs/50/e55b765eba0ec7348e50a1df496040449071b96a.jpg"
        )
        assert (
            thumb_path(Request("file:///tmp/foo"), name)
            == "thumbs/50/0329ad83ebb8e93ea7c7906d46e9ed55f7349a50.jpg"
        )
        assert (
            thumb_path(Request("file:///tmp/some.name/foo"), name)
            == "thumbs/50/850233df65a5b83361798f532f1fc549cd13cbe9.jpg"
        )
        assert (
            thumb_path(
                Request("file:///tmp/some.name/foo"),
                name,
                response=Response("file:///tmp/some.name/foo"),
                info=object(),
            )
            == "thumbs/50/850233df65a5b83361798f532f1fc549cd13cbe9.jpg"
        )

    def test_thumbnail_name_from_item(self):
        """
        Custom thumbnail name based on item data, overriding default implementation
        """

        class CustomImagesPipeline(ImagesPipeline):
            def thumb_path(
                self, request, thumb_id, response=None, info=None, item=None
            ):
                return f"thumb/{thumb_id}/{item.get('path')}"

        thumb_path = CustomImagesPipeline.from_crawler(
            get_crawler(None, {"IMAGES_STORE": self.tempdir})
        ).thumb_path
        item = {"path": "path-to-store-file"}
        request = Request("http://example.com")
        assert (
            thumb_path(request, "small", item=item) == "thumb/small/path-to-store-file"
        )

    def test_get_images_exception(self):
        self.pipeline.min_width = 100
        self.pipeline.min_height = 100

        _, buf1 = _create_image("JPEG", "RGB", (50, 50), (0, 0, 0))
        _, buf2 = _create_image("JPEG", "RGB", (150, 50), (0, 0, 0))
        _, buf3 = _create_image("JPEG", "RGB", (50, 150), (0, 0, 0))

        resp1 = Response(url="https://dev.mydeco.com/mydeco.gif", body=buf1.getvalue())
        resp2 = Response(url="https://dev.mydeco.com/mydeco.gif", body=buf2.getvalue())
        resp3 = Response(url="https://dev.mydeco.com/mydeco.gif", body=buf3.getvalue())
        req = Request(url="https://dev.mydeco.com/mydeco.gif")

        with pytest.raises(ImageException):
            next(self.pipeline.get_images(response=resp1, request=req, info=object()))
        with pytest.raises(ImageException):
            next(self.pipeline.get_images(response=resp2, request=req, info=object()))
        with pytest.raises(ImageException):
            next(self.pipeline.get_images(response=resp3, request=req, info=object()))

    def test_get_images(self):
        self.pipeline.min_width = 0
        self.pipeline.min_height = 0
        self.pipeline.thumbs = {"small": (20, 20)}

        orig_im, buf = _create_image("JPEG", "RGB", (50, 50), (0, 0, 0))
        orig_thumb, orig_thumb_buf = _create_image("JPEG", "RGB", (20, 20), (0, 0, 0))
        resp = Response(url="https://dev.mydeco.com/mydeco.gif", body=buf.getvalue())
        req = Request(url="https://dev.mydeco.com/mydeco.gif")

        get_images_gen = self.pipeline.get_images(
            response=resp, request=req, info=object()
        )

        path, new_im, new_buf = next(get_images_gen)
        assert path == "full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg"
        assert orig_im == new_im
        assert buf.getvalue() == new_buf.getvalue()

        thumb_path, thumb_img, thumb_buf = next(get_images_gen)
        assert thumb_path == "thumbs/small/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg"
        assert orig_thumb_buf.getvalue() == thumb_buf.getvalue()

    def test_convert_image(self):
        SIZE = (100, 100)
        # straight forward case: RGB and JPEG
        COLOUR = (0, 127, 255)
        im, buf = _create_image("JPEG", "RGB", SIZE, COLOUR)
        converted, converted_buf = self.pipeline.convert_image(im, response_body=buf)
        assert converted.mode == "RGB"
        assert converted.getcolors() == [(10000, COLOUR)]
        # check that we don't convert JPEGs again
        assert converted_buf == buf

        # check that thumbnail keep image ratio
        thumbnail, _ = self.pipeline.convert_image(
            converted, size=(10, 25), response_body=converted_buf
        )
        assert thumbnail.mode == "RGB"
        assert thumbnail.size == (10, 10)

        # transparency case: RGBA and PNG
        COLOUR = (0, 127, 255, 50)
        im, buf = _create_image("PNG", "RGBA", SIZE, COLOUR)
        converted, _ = self.pipeline.convert_image(im, response_body=buf)
        assert converted.mode == "RGB"
        assert converted.getcolors() == [(10000, (205, 230, 255))]

        # transparency case with palette: P and PNG
        COLOUR = (0, 127, 255, 50)
        im, buf = _create_image("PNG", "RGBA", SIZE, COLOUR)
        im = im.convert("P")
        converted, _ = self.pipeline.convert_image(im, response_body=buf)
        assert converted.mode == "RGB"
        assert converted.getcolors() == [(10000, (205, 230, 255))]


class ImagesPipelineTestCaseFieldsMixin:
    def test_item_fields_default(self):
        url = "http://www.example.com/images/1.jpg"
        item = self.item_class(name="item1", image_urls=[url])
        pipeline = ImagesPipeline.from_crawler(
            get_crawler(None, {"IMAGES_STORE": "s3://example/images/"})
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        images = ItemAdapter(item).get("images")
        assert images == [results[0][1]]
        assert isinstance(item, self.item_class)

    def test_item_fields_override_settings(self):
        url = "http://www.example.com/images/1.jpg"
        item = self.item_class(name="item1", custom_image_urls=[url])
        pipeline = ImagesPipeline.from_crawler(
            get_crawler(
                None,
                {
                    "IMAGES_STORE": "s3://example/images/",
                    "IMAGES_URLS_FIELD": "custom_image_urls",
                    "IMAGES_RESULT_FIELD": "custom_images",
                },
            )
        )
        requests = list(pipeline.get_media_requests(item, None))
        assert requests[0].url == url
        results = [(True, {"url": url})]
        item = pipeline.item_completed(results, item, None)
        custom_images = ItemAdapter(item).get("custom_images")
        assert custom_images == [results[0][1]]
        assert isinstance(item, self.item_class)


class TestImagesPipelineFieldsDict(ImagesPipelineTestCaseFieldsMixin):
    item_class = dict


class ImagesPipelineTestItem(Item):
    name = Field()
    # default fields
    image_urls = Field()
    images = Field()
    # overridden fields
    custom_image_urls = Field()
    custom_images = Field()


class TestImagesPipelineFieldsItem(ImagesPipelineTestCaseFieldsMixin):
    item_class = ImagesPipelineTestItem


@dataclasses.dataclass
class ImagesPipelineTestDataClass:
    name: str
    # default fields
    image_urls: list = dataclasses.field(default_factory=list)
    images: list = dataclasses.field(default_factory=list)
    # overridden fields
    custom_image_urls: list = dataclasses.field(default_factory=list)
    custom_images: list = dataclasses.field(default_factory=list)


class TestImagesPipelineFieldsDataClass(ImagesPipelineTestCaseFieldsMixin):
    item_class = ImagesPipelineTestDataClass


@attr.s
class ImagesPipelineTestAttrsItem:
    name = attr.ib(default="")
    # default fields
    image_urls: list[str] = attr.ib(default=list)
    images: list[dict[str, str]] = attr.ib(default=list)
    # overridden fields
    custom_image_urls: list[str] = attr.ib(default=list)
    custom_images: list[dict[str, str]] = attr.ib(default=list)


class TestImagesPipelineFieldsAttrsItem(ImagesPipelineTestCaseFieldsMixin):
    item_class = ImagesPipelineTestAttrsItem


class TestImagesPipelineCustomSettings:
    img_cls_attribute_names = [
        # Pipeline attribute names with corresponding setting names.
        ("EXPIRES", "IMAGES_EXPIRES"),
        ("MIN_WIDTH", "IMAGES_MIN_WIDTH"),
        ("MIN_HEIGHT", "IMAGES_MIN_HEIGHT"),
        ("IMAGES_URLS_FIELD", "IMAGES_URLS_FIELD"),
        ("IMAGES_RESULT_FIELD", "IMAGES_RESULT_FIELD"),
        ("THUMBS", "IMAGES_THUMBS"),
    ]

    # This should match what is defined in ImagesPipeline.
    default_pipeline_settings = {
        "MIN_WIDTH": 0,
        "MIN_HEIGHT": 0,
        "EXPIRES": 90,
        "THUMBS": {},
        "IMAGES_URLS_FIELD": "image_urls",
        "IMAGES_RESULT_FIELD": "images",
    }

    def _generate_fake_settings(self, tmp_path, prefix=None):
        """
        :param prefix: string for setting keys
        :return: dictionary of image pipeline settings
        """

        def random_string():
            return "".join([chr(random.randint(97, 123)) for _ in range(10)])

        settings = {
            "IMAGES_EXPIRES": random.randint(100, 1000),
            "IMAGES_STORE": tmp_path,
            "IMAGES_RESULT_FIELD": random_string(),
            "IMAGES_URLS_FIELD": random_string(),
            "IMAGES_MIN_WIDTH": random.randint(1, 1000),
            "IMAGES_MIN_HEIGHT": random.randint(1, 1000),
            "IMAGES_THUMBS": {
                "small": (random.randint(1, 1000), random.randint(1, 1000)),
                "big": (random.randint(1, 1000), random.randint(1, 1000)),
            },
        }
        if not prefix:
            return settings

        return {
            prefix.upper() + "_" + k if k != "IMAGES_STORE" else k: v
            for k, v in settings.items()
        }

    def _generate_fake_pipeline_subclass(self):
        """
        :return: ImagePipeline class will all uppercase attributes set.
        """

        class UserDefinedImagePipeline(ImagesPipeline):
            # Values should be in different range than fake_settings.
            MIN_WIDTH = random.randint(1000, 2000)
            MIN_HEIGHT = random.randint(1000, 2000)
            THUMBS = {
                "small": (random.randint(1000, 2000), random.randint(1000, 2000)),
                "big": (random.randint(1000, 2000), random.randint(1000, 2000)),
            }
            EXPIRES = random.randint(1000, 2000)
            IMAGES_URLS_FIELD = "field_one"
            IMAGES_RESULT_FIELD = "field_two"

        return UserDefinedImagePipeline

    def test_different_settings_for_different_instances(self, tmp_path):
        """
        If there are two instances of ImagesPipeline class with different settings, they should
        have different settings.
        """
        custom_settings = self._generate_fake_settings(tmp_path)
        default_sts_pipe = ImagesPipeline(tmp_path, crawler=get_crawler(None))
        user_sts_pipe = ImagesPipeline.from_crawler(get_crawler(None, custom_settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            expected_default_value = self.default_pipeline_settings.get(pipe_attr)
            custom_value = custom_settings.get(settings_attr)
            assert expected_default_value != custom_value
            assert (
                getattr(default_sts_pipe, pipe_attr.lower()) == expected_default_value
            )
            assert getattr(user_sts_pipe, pipe_attr.lower()) == custom_value

    def test_subclass_attrs_preserved_default_settings(self, tmp_path):
        """
        If image settings are not defined at all subclass of ImagePipeline takes values
        from class attributes.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        pipeline = pipeline_cls.from_crawler(
            get_crawler(None, {"IMAGES_STORE": tmp_path})
        )
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Instance attribute (lowercase) must be equal to class attribute (uppercase).
            attr_value = getattr(pipeline, pipe_attr.lower())
            assert attr_value != self.default_pipeline_settings[pipe_attr]
            assert attr_value == getattr(pipeline, pipe_attr)

    def test_subclass_attrs_preserved_custom_settings(self, tmp_path):
        """
        If image settings are defined but they are not defined for subclass default
        values taken from settings should be preserved.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        settings = self._generate_fake_settings(tmp_path)
        pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Instance attribute (lowercase) must be equal to
            # value defined in settings.
            value = getattr(pipeline, pipe_attr.lower())
            assert value != self.default_pipeline_settings[pipe_attr]
            setings_value = settings.get(settings_attr)
            assert value == setings_value

    def test_no_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are no settings for subclass and no subclass attributes, pipeline should use
        attributes of base class.
        """

        class UserDefinedImagePipeline(ImagesPipeline):
            pass

        user_pipeline = UserDefinedImagePipeline.from_crawler(
            get_crawler(None, {"IMAGES_STORE": tmp_path})
        )
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = self.default_pipeline_settings.get(pipe_attr.upper())
            assert getattr(user_pipeline, pipe_attr.lower()) == custom_value

    def test_custom_settings_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass and NO class attributes, pipeline should use custom
        settings.
        """

        class UserDefinedImagePipeline(ImagesPipeline):
            pass

        prefix = UserDefinedImagePipeline.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = UserDefinedImagePipeline.from_crawler(
            get_crawler(None, settings)
        )
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_pipeline_settings[pipe_attr]
            assert getattr(user_pipeline, pipe_attr.lower()) == custom_value

    def test_custom_settings_and_class_attrs_for_subclasses(self, tmp_path):
        """
        If there are custom settings for subclass AND class attributes
        setting keys are preferred and override attributes.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        prefix = pipeline_cls.__name__.upper()
        settings = self._generate_fake_settings(tmp_path, prefix=prefix)
        user_pipeline = pipeline_cls.from_crawler(get_crawler(None, settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            custom_value = settings.get(prefix + "_" + settings_attr)
            assert custom_value != self.default_pipeline_settings[pipe_attr]
            assert getattr(user_pipeline, pipe_attr.lower()) == custom_value

    def test_cls_attrs_with_DEFAULT_prefix(self, tmp_path):
        class UserDefinedImagePipeline(ImagesPipeline):
            DEFAULT_IMAGES_URLS_FIELD = "something"
            DEFAULT_IMAGES_RESULT_FIELD = "something_else"

        pipeline = UserDefinedImagePipeline.from_crawler(
            get_crawler(None, {"IMAGES_STORE": tmp_path})
        )
        assert (
            pipeline.images_result_field
            == UserDefinedImagePipeline.DEFAULT_IMAGES_RESULT_FIELD
        )
        assert (
            pipeline.images_urls_field
            == UserDefinedImagePipeline.DEFAULT_IMAGES_URLS_FIELD
        )

    def test_user_defined_subclass_default_key_names(self, tmp_path):
        """Test situation when user defines subclass of ImagePipeline,
        but uses attribute names for default pipeline (without prefixing
        them with pipeline class name).
        """
        settings = self._generate_fake_settings(tmp_path)

        class UserPipe(ImagesPipeline):
            pass

        pipeline_cls = UserPipe.from_crawler(get_crawler(None, settings))

        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            expected_value = settings.get(settings_attr)
            assert getattr(pipeline_cls, pipe_attr.lower()) == expected_value


def _create_image(format, *a, **kw):
    buf = io.BytesIO()
    Image.new(*a, **kw).save(buf, format)
    buf.seek(0)
    return Image.open(buf), buf
