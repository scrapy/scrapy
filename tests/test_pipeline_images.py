import hashlib
import io
import random
from shutil import rmtree
from tempfile import mkdtemp
from unittest import skipIf

import attr
from itemadapter import ItemAdapter
from twisted.trial import unittest

from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.pipelines.images import ImagesPipeline
from scrapy.settings import Settings
from scrapy.utils.python import to_bytes


try:
    from dataclasses import make_dataclass, field as dataclass_field
except ImportError:
    make_dataclass = None
    dataclass_field = None


try:
    from PIL import Image
except ImportError:
    skip_pillow = 'Missing Python Imaging Library, install https://pypi.python.org/pypi/Pillow'
else:
    encoders = {'jpeg_encoder', 'jpeg_decoder'}
    if not encoders.issubset(set(Image.core.__dict__)):
        skip_pillow = 'Missing JPEG encoders'
    else:
        skip_pillow = None


def _mocked_download_func(request, info):
    response = request.meta.get('response')
    return response() if callable(response) else response


class ImagesPipelineTestCase(unittest.TestCase):

    skip = skip_pillow

    def setUp(self):
        self.tempdir = mkdtemp()
        self.pipeline = ImagesPipeline(self.tempdir, download_func=_mocked_download_func)

    def tearDown(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        self.assertEqual(
            file_path(Request("https://dev.mydeco.com/mydeco.gif")),
            'full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
        self.assertEqual(
            file_path(Request("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.jpg")),
            'full/0ffcd85d563bca45e2f90becd0ca737bc58a00b2.jpg')
        self.assertEqual(
            file_path(Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.gif")),
            'full/b250e3a74fff2e4703e310048a5b13eba79379d2.jpg')
        self.assertEqual(
            file_path(Request("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg")),
            'full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532/")),
            'full/97ee6f8a46cbbb418ea91502fd24176865cf39b2.jpg')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532")),
            'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg')
        self.assertEqual(
            file_path(Request("http://www.dorma.co.uk/images/product_details/2532"),
                      response=Response("http://www.dorma.co.uk/images/product_details/2532"),
                      info=object()),
            'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg')

    def test_thumbnail_name(self):
        thumb_path = self.pipeline.thumb_path
        name = '50'
        self.assertEqual(thumb_path(Request("file:///tmp/foo.jpg"), name),
                         'thumbs/50/38a86208c36e59d4404db9e37ce04be863ef0335.jpg')
        self.assertEqual(thumb_path(Request("file://foo.png"), name),
                         'thumbs/50/e55b765eba0ec7348e50a1df496040449071b96a.jpg')
        self.assertEqual(thumb_path(Request("file:///tmp/foo"), name),
                         'thumbs/50/0329ad83ebb8e93ea7c7906d46e9ed55f7349a50.jpg')
        self.assertEqual(thumb_path(Request("file:///tmp/some.name/foo"), name),
                         'thumbs/50/850233df65a5b83361798f532f1fc549cd13cbe9.jpg')
        self.assertEqual(thumb_path(Request("file:///tmp/some.name/foo"), name,
                                    response=Response("file:///tmp/some.name/foo"),
                                    info=object()),
                         'thumbs/50/850233df65a5b83361798f532f1fc549cd13cbe9.jpg')

    def test_convert_image(self):
        SIZE = (100, 100)
        # straigh forward case: RGB and JPEG
        COLOUR = (0, 127, 255)
        im = _create_image('JPEG', 'RGB', SIZE, COLOUR)
        converted, _ = self.pipeline.convert_image(im)
        self.assertEqual(converted.mode, 'RGB')
        self.assertEqual(converted.getcolors(), [(10000, COLOUR)])

        # check that thumbnail keep image ratio
        thumbnail, _ = self.pipeline.convert_image(converted, size=(10, 25))
        self.assertEqual(thumbnail.mode, 'RGB')
        self.assertEqual(thumbnail.size, (10, 10))

        # transparency case: RGBA and PNG
        COLOUR = (0, 127, 255, 50)
        im = _create_image('PNG', 'RGBA', SIZE, COLOUR)
        converted, _ = self.pipeline.convert_image(im)
        self.assertEqual(converted.mode, 'RGB')
        self.assertEqual(converted.getcolors(), [(10000, (205, 230, 255))])

        # transparency case with palette: P and PNG
        COLOUR = (0, 127, 255, 50)
        im = _create_image('PNG', 'RGBA', SIZE, COLOUR)
        im = im.convert('P')
        converted, _ = self.pipeline.convert_image(im)
        self.assertEqual(converted.mode, 'RGB')
        self.assertEqual(converted.getcolors(), [(10000, (205, 230, 255))])


class DeprecatedImagesPipeline(ImagesPipeline):
    def file_key(self, url):
        return self.image_key(url)

    def image_key(self, url):
        image_guid = hashlib.sha1(to_bytes(url)).hexdigest()
        return f'empty/{image_guid}.jpg'

    def thumb_key(self, url, thumb_id):
        thumb_guid = hashlib.sha1(to_bytes(url)).hexdigest()
        return f'thumbsup/{thumb_id}/{thumb_guid}.jpg'


class ImagesPipelineTestCaseFieldsMixin:

    skip = skip_pillow

    def test_item_fields_default(self):
        url = 'http://www.example.com/images/1.jpg'
        item = self.item_class(name='item1', image_urls=[url])
        pipeline = ImagesPipeline.from_settings(Settings({'IMAGES_STORE': 's3://example/images/'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        item = pipeline.item_completed(results, item, None)
        images = ItemAdapter(item).get("images")
        self.assertEqual(images, [results[0][1]])
        self.assertIsInstance(item, self.item_class)

    def test_item_fields_override_settings(self):
        url = 'http://www.example.com/images/1.jpg'
        item = self.item_class(name='item1', custom_image_urls=[url])
        pipeline = ImagesPipeline.from_settings(Settings({
            'IMAGES_STORE': 's3://example/images/',
            'IMAGES_URLS_FIELD': 'custom_image_urls',
            'IMAGES_RESULT_FIELD': 'custom_images'
        }))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        item = pipeline.item_completed(results, item, None)
        custom_images = ItemAdapter(item).get("custom_images")
        self.assertEqual(custom_images, [results[0][1]])
        self.assertIsInstance(item, self.item_class)


class ImagesPipelineTestCaseFieldsDict(ImagesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = dict


class ImagesPipelineTestItem(Item):
    name = Field()
    # default fields
    image_urls = Field()
    images = Field()
    # overridden fields
    custom_image_urls = Field()
    custom_images = Field()


class ImagesPipelineTestCaseFieldsItem(ImagesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = ImagesPipelineTestItem


@skipIf(not make_dataclass, "dataclasses module is not available")
class ImagesPipelineTestCaseFieldsDataClass(ImagesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if make_dataclass:
            self.item_class = make_dataclass(
                "FilesPipelineTestDataClass",
                [
                    ("name", str),
                    # default fields
                    ("image_urls", list, dataclass_field(default_factory=list)),
                    ("images", list, dataclass_field(default_factory=list)),
                    # overridden fields
                    ("custom_image_urls", list, dataclass_field(default_factory=list)),
                    ("custom_images", list, dataclass_field(default_factory=list)),
                ],
            )


@attr.s
class ImagesPipelineTestAttrsItem:
    name = attr.ib(default="")
    # default fields
    image_urls = attr.ib(default=lambda: [])
    images = attr.ib(default=lambda: [])
    # overridden fields
    custom_image_urls = attr.ib(default=lambda: [])
    custom_images = attr.ib(default=lambda: [])


class ImagesPipelineTestCaseFieldsAttrsItem(ImagesPipelineTestCaseFieldsMixin, unittest.TestCase):
    item_class = ImagesPipelineTestAttrsItem


class ImagesPipelineTestCaseCustomSettings(unittest.TestCase):

    skip = skip_pillow

    img_cls_attribute_names = [
        # Pipeline attribute names with corresponding setting names.
        ("EXPIRES", "IMAGES_EXPIRES"),
        ("MIN_WIDTH", "IMAGES_MIN_WIDTH"),
        ("MIN_HEIGHT", "IMAGES_MIN_HEIGHT"),
        ("IMAGES_URLS_FIELD", "IMAGES_URLS_FIELD"),
        ("IMAGES_RESULT_FIELD", "IMAGES_RESULT_FIELD"),
        ("THUMBS", "IMAGES_THUMBS")
    ]

    # This should match what is defined in ImagesPipeline.
    default_pipeline_settings = dict(
        MIN_WIDTH=0,
        MIN_HEIGHT=0,
        EXPIRES=90,
        THUMBS={},
        IMAGES_URLS_FIELD='image_urls',
        IMAGES_RESULT_FIELD='images'
    )

    def setUp(self):
        self.tempdir = mkdtemp()

    def tearDown(self):
        rmtree(self.tempdir)

    def _generate_fake_settings(self, prefix=None):
        """
        :param prefix: string for setting keys
        :return: dictionary of image pipeline settings
        """

        def random_string():
            return "".join([chr(random.randint(97, 123)) for _ in range(10)])

        settings = {
            "IMAGES_EXPIRES": random.randint(100, 1000),
            "IMAGES_STORE": self.tempdir,
            "IMAGES_RESULT_FIELD": random_string(),
            "IMAGES_URLS_FIELD": random_string(),
            "IMAGES_MIN_WIDTH": random.randint(1, 1000),
            "IMAGES_MIN_HEIGHT": random.randint(1, 1000),
            "IMAGES_THUMBS": {
                'small': (random.randint(1, 1000), random.randint(1, 1000)),
                'big': (random.randint(1, 1000), random.randint(1, 1000))
            }
        }
        if not prefix:
            return settings

        return {prefix.upper() + "_" + k if k != "IMAGES_STORE" else k: v for k, v in settings.items()}

    def _generate_fake_pipeline_subclass(self):
        """
        :return: ImagePipeline class will all uppercase attributes set.
        """
        class UserDefinedImagePipeline(ImagesPipeline):
            # Values should be in different range than fake_settings.
            MIN_WIDTH = random.randint(1000, 2000)
            MIN_HEIGHT = random.randint(1000, 2000)
            THUMBS = {
                'small': (random.randint(1000, 2000), random.randint(1000, 2000)),
                'big': (random.randint(1000, 2000), random.randint(1000, 2000))
            }
            EXPIRES = random.randint(1000, 2000)
            IMAGES_URLS_FIELD = "field_one"
            IMAGES_RESULT_FIELD = "field_two"

        return UserDefinedImagePipeline

    def test_different_settings_for_different_instances(self):
        """
        If there are two instances of ImagesPipeline class with different settings, they should
        have different settings.
        """
        custom_settings = self._generate_fake_settings()
        default_settings = Settings()
        default_sts_pipe = ImagesPipeline(self.tempdir, settings=default_settings)
        user_sts_pipe = ImagesPipeline.from_settings(Settings(custom_settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            expected_default_value = self.default_pipeline_settings.get(pipe_attr)
            custom_value = custom_settings.get(settings_attr)
            self.assertNotEqual(expected_default_value, custom_value)
            self.assertEqual(getattr(default_sts_pipe, pipe_attr.lower()), expected_default_value)
            self.assertEqual(getattr(user_sts_pipe, pipe_attr.lower()), custom_value)

    def test_subclass_attrs_preserved_default_settings(self):
        """
        If image settings are not defined at all subclass of ImagePipeline takes values
        from class attributes.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        pipeline = pipeline_cls.from_settings(Settings({"IMAGES_STORE": self.tempdir}))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Instance attribute (lowercase) must be equal to class attribute (uppercase).
            attr_value = getattr(pipeline, pipe_attr.lower())
            self.assertNotEqual(attr_value, self.default_pipeline_settings[pipe_attr])
            self.assertEqual(attr_value, getattr(pipeline, pipe_attr))

    def test_subclass_attrs_preserved_custom_settings(self):
        """
        If image settings are defined but they are not defined for subclass default
        values taken from settings should be preserved.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        settings = self._generate_fake_settings()
        pipeline = pipeline_cls.from_settings(Settings(settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Instance attribute (lowercase) must be equal to
            # value defined in settings.
            value = getattr(pipeline, pipe_attr.lower())
            self.assertNotEqual(value, self.default_pipeline_settings[pipe_attr])
            setings_value = settings.get(settings_attr)
            self.assertEqual(value, setings_value)

    def test_no_custom_settings_for_subclasses(self):
        """
        If there are no settings for subclass and no subclass attributes, pipeline should use
        attributes of base class.
        """
        class UserDefinedImagePipeline(ImagesPipeline):
            pass

        user_pipeline = UserDefinedImagePipeline.from_settings(Settings({"IMAGES_STORE": self.tempdir}))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = self.default_pipeline_settings.get(pipe_attr.upper())
            self.assertEqual(getattr(user_pipeline, pipe_attr.lower()), custom_value)

    def test_custom_settings_for_subclasses(self):
        """
        If there are custom settings for subclass and NO class attributes, pipeline should use custom
        settings.
        """
        class UserDefinedImagePipeline(ImagesPipeline):
            pass

        prefix = UserDefinedImagePipeline.__name__.upper()
        settings = self._generate_fake_settings(prefix=prefix)
        user_pipeline = UserDefinedImagePipeline.from_settings(Settings(settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            # Values from settings for custom pipeline should be set on pipeline instance.
            custom_value = settings.get(prefix + "_" + settings_attr)
            self.assertNotEqual(custom_value, self.default_pipeline_settings[pipe_attr])
            self.assertEqual(getattr(user_pipeline, pipe_attr.lower()), custom_value)

    def test_custom_settings_and_class_attrs_for_subclasses(self):
        """
        If there are custom settings for subclass AND class attributes
        setting keys are preferred and override attributes.
        """
        pipeline_cls = self._generate_fake_pipeline_subclass()
        prefix = pipeline_cls.__name__.upper()
        settings = self._generate_fake_settings(prefix=prefix)
        user_pipeline = pipeline_cls.from_settings(Settings(settings))
        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            custom_value = settings.get(prefix + "_" + settings_attr)
            self.assertNotEqual(custom_value, self.default_pipeline_settings[pipe_attr])
            self.assertEqual(getattr(user_pipeline, pipe_attr.lower()), custom_value)

    def test_cls_attrs_with_DEFAULT_prefix(self):
        class UserDefinedImagePipeline(ImagesPipeline):
            DEFAULT_IMAGES_URLS_FIELD = "something"
            DEFAULT_IMAGES_RESULT_FIELD = "something_else"
        pipeline = UserDefinedImagePipeline.from_settings(Settings({"IMAGES_STORE": self.tempdir}))
        self.assertEqual(pipeline.images_result_field, "something_else")
        self.assertEqual(pipeline.images_urls_field, "something")

    def test_user_defined_subclass_default_key_names(self):
        """Test situation when user defines subclass of ImagePipeline,
        but uses attribute names for default pipeline (without prefixing
        them with pipeline class name).
        """
        settings = self._generate_fake_settings()

        class UserPipe(ImagesPipeline):
            pass

        pipeline_cls = UserPipe.from_settings(Settings(settings))

        for pipe_attr, settings_attr in self.img_cls_attribute_names:
            expected_value = settings.get(settings_attr)
            self.assertEqual(getattr(pipeline_cls, pipe_attr.lower()),
                             expected_value)


def _create_image(format, *a, **kw):
    buf = io.BytesIO()
    Image.new(*a, **kw).save(buf, format)
    buf.seek(0)
    return Image.open(buf)


if __name__ == "__main__":
    unittest.main()
