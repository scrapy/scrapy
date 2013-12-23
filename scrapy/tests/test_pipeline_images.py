import os
import hashlib
import warnings
from cStringIO import StringIO
from tempfile import mkdtemp
from shutil import rmtree

from twisted.trial import unittest

from scrapy.item import Item, Field
from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.contrib.pipeline.images import ImagesPipeline

skip = False
try:
    from PIL import Image
except ImportError as e:
    skip = 'Missing Python Imaging Library, install https://pypi.python.org/pypi/Pillow'
else:
    encoders = set(('jpeg_encoder', 'jpeg_decoder'))
    if not encoders.issubset(set(Image.core.__dict__)):
        skip = 'Missing JPEG encoders'


def _mocked_download_func(request, info):
    response = request.meta.get('response')
    return response() if callable(response) else response


class ImagesPipelineTestCase(unittest.TestCase):

    skip = skip

    def setUp(self):
        self.tempdir = mkdtemp()
        self.pipeline = ImagesPipeline(self.tempdir, download_func=_mocked_download_func)

    def tearDown(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        file_path = self.pipeline.file_path
        self.assertEqual(file_path(Request("https://dev.mydeco.com/mydeco.gif")),
                         'full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
        self.assertEqual(file_path(Request("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.jpg")),
                         'full/0ffcd85d563bca45e2f90becd0ca737bc58a00b2.jpg')
        self.assertEqual(file_path(Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.gif")),
                         'full/b250e3a74fff2e4703e310048a5b13eba79379d2.jpg')
        self.assertEqual(file_path(Request("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg")),
                         'full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg')
        self.assertEqual(file_path(Request("http://www.dorma.co.uk/images/product_details/2532/")),
                         'full/97ee6f8a46cbbb418ea91502fd24176865cf39b2.jpg')
        self.assertEqual(file_path(Request("http://www.dorma.co.uk/images/product_details/2532")),
                         'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg')
        self.assertEqual(file_path(Request("http://www.dorma.co.uk/images/product_details/2532"),
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
        self.assertEquals(converted.mode, 'RGB')
        self.assertEquals(converted.getcolors(), [(10000, COLOUR)])

        # check that thumbnail keep image ratio
        thumbnail, _ = self.pipeline.convert_image(converted, size=(10, 25))
        self.assertEquals(thumbnail.mode, 'RGB')
        self.assertEquals(thumbnail.size, (10, 10))

        # transparency case: RGBA and PNG
        COLOUR = (0, 127, 255, 50)
        im = _create_image('PNG', 'RGBA', SIZE, COLOUR)
        converted, _ = self.pipeline.convert_image(im)
        self.assertEquals(converted.mode, 'RGB')
        self.assertEquals(converted.getcolors(), [(10000, (205, 230, 255))])


class DeprecatedImagesPipeline(ImagesPipeline):
    def file_key(self, url):
        return self.image_key(url)

    def image_key(self, url):
        image_guid = hashlib.sha1(url).hexdigest()
        return 'empty/%s.jpg' % (image_guid)

    def thumb_key(self, url, thumb_id):
        thumb_guid = hashlib.sha1(url).hexdigest()
        return 'thumbsup/%s/%s.jpg' % (thumb_id, thumb_guid)


class DeprecatedImagesPipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = mkdtemp()

    def init_pipeline(self, pipeline_class):
        self.pipeline = pipeline_class(self.tempdir, download_func=_mocked_download_func)
        self.pipeline.open_spider(None)

    def test_default_file_key_method(self):
        self.init_pipeline(ImagesPipeline)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            self.assertEqual(self.pipeline.file_key("https://dev.mydeco.com/mydeco.gif"),
                             'full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
            self.assertEqual(len(w), 1)
            self.assertTrue('image_key(url) and file_key(url) methods are deprecated' in str(w[-1].message))

    def test_default_image_key_method(self):
        self.init_pipeline(ImagesPipeline)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            self.assertEqual(self.pipeline.image_key("https://dev.mydeco.com/mydeco.gif"),
                             'full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
            self.assertEqual(len(w), 1)
            self.assertTrue('image_key(url) and file_key(url) methods are deprecated' in str(w[-1].message))

    def test_overridden_file_key_method(self):
        self.init_pipeline(DeprecatedImagesPipeline)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            self.assertEqual(self.pipeline.file_path(Request("https://dev.mydeco.com/mydeco.gif")),
                             'empty/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
            self.assertEqual(len(w), 1)
            self.assertTrue('image_key(url) and file_key(url) methods are deprecated' in str(w[-1].message))

    def test_default_thumb_key_method(self):
        self.init_pipeline(ImagesPipeline)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            self.assertEqual(self.pipeline.thumb_key("file:///tmp/foo.jpg", 50),
                             'thumbs/50/38a86208c36e59d4404db9e37ce04be863ef0335.jpg')
            self.assertEqual(len(w), 1)
            self.assertTrue('thumb_key(url) method is deprecated' in str(w[-1].message))

    def test_overridden_thumb_key_method(self):
        self.init_pipeline(DeprecatedImagesPipeline)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            self.assertEqual(self.pipeline.thumb_path(Request("file:///tmp/foo.jpg"), 50),
                             'thumbsup/50/38a86208c36e59d4404db9e37ce04be863ef0335.jpg')
            self.assertEqual(len(w), 1)
            self.assertTrue('thumb_key(url) method is deprecated' in str(w[-1].message))

    def tearDown(self):
        rmtree(self.tempdir)


class ImagesPipelineTestCaseFields(unittest.TestCase):

    def test_item_fields_default(self):
        from scrapy.contrib.pipeline.images import ImagesPipeline
        class TestItem(Item):
            name = Field()
            image_urls = Field()
            images = Field()
        url = 'http://www.example.com/images/1.jpg'
        item = TestItem({'name': 'item1', 'image_urls': [url]})
        pipeline = ImagesPipeline.from_settings(Settings({'IMAGES_STORE': 's3://example/images/'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        pipeline.item_completed(results, item, None)
        self.assertEqual(item['images'], [results[0][1]])

    def test_item_fields_override_settings(self):
        from scrapy.contrib.pipeline.images import ImagesPipeline
        class TestItem(Item):
            name = Field()
            image = Field()
            stored_image = Field()
        url = 'http://www.example.com/images/1.jpg'
        item = TestItem({'name': 'item1', 'image': [url]})
        pipeline = ImagesPipeline.from_settings(Settings({'IMAGES_STORE': 's3://example/images/',
                'IMAGES_URLS_FIELD': 'image', 'IMAGES_RESULT_FIELD': 'stored_image'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        pipeline.item_completed(results, item, None)
        self.assertEqual(item['stored_image'], [results[0][1]])


def _create_image(format, *a, **kw):
    buf = StringIO()
    Image.new(*a, **kw).save(buf, format)
    buf.seek(0)
    return Image.open(buf)


if __name__ == "__main__":
    unittest.main()
