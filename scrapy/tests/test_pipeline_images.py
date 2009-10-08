import os
from twisted.trial import unittest
from scrapy.conf import settings
from tempfile import mkdtemp
from shutil import rmtree


class ImagesPipelineTestCase(unittest.TestCase):
    def setUp(self):
        try:
            import Image
        except ImportError, e:
            raise unittest.SkipTest(e)

        from scrapy.contrib.pipeline.images import ImagesPipeline
        self.tempdir = mkdtemp()
        self.settings_disabled_before = settings.disabled
        settings.disabled = False
        settings.overrides['IMAGES_STORE'] = self.tempdir
        self.pipeline = ImagesPipeline()

    def tearDown(self):
        del self.pipeline
        rmtree(self.tempdir)
        settings.disabled = self.settings_disabled_before

    def test_image_path(self):
        image_path = self.pipeline.image_key
        self.assertEqual(image_path("https://dev.mydeco.com/mydeco.gif"),
                         'full/3fd165099d8e71b8a48b2683946e64dbfad8b52d.jpg')
        self.assertEqual(image_path("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.jpg"),
                         'full/0ffcd85d563bca45e2f90becd0ca737bc58a00b2.jpg')
        self.assertEqual(image_path("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.gif"),
                         'full/b250e3a74fff2e4703e310048a5b13eba79379d2.jpg')
        self.assertEqual(image_path("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg"),
                         'full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg')
        self.assertEqual(image_path("http://www.dorma.co.uk/images/product_details/2532/"),
                         'full/97ee6f8a46cbbb418ea91502fd24176865cf39b2.jpg')
        self.assertEqual(image_path("http://www.dorma.co.uk/images/product_details/2532"),
                         'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1.jpg')

    def test_thumbnail_name(self):
        thumbnail_name = self.pipeline.thumb_key
        name = '50'
        self.assertEqual(thumbnail_name("/tmp/foo.jpg", name),  
                         'thumbs/50/271f172bb4727281011c80fe763e93a47bb6b3fe.jpg')
        self.assertEqual(thumbnail_name("foo.png", name),
                         'thumbs/50/0945c699b5580b99e4f40dffc009699b2b6830a7.jpg')
        self.assertEqual(thumbnail_name("/tmp/foo", name),
                         'thumbs/50/469150566bd728fc90b4adf6495202fd70ec3537.jpg')
        self.assertEqual(thumbnail_name("/tmp/some.name/foo", name),
                         'thumbs/50/92dac2a6a2072c5695a5dff1f865b3cb70c657bb.jpg')

    def test_fs_store(self):
        from scrapy.contrib.pipeline.images import FSImagesStore
        assert isinstance(self.pipeline.store, FSImagesStore)
        self.assertEqual(self.pipeline.store.basedir, self.tempdir)

        key = 'some/image/key.jpg'
        path = os.path.join(self.tempdir, 'some', 'image', 'key.jpg')
        self.assertEqual(self.pipeline.store._get_filesystem_path(key),
            path)


if __name__ == "__main__":
    unittest.main()
