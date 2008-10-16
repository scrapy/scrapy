import unittest
from scrapy.contrib.pipeline.images import thumbnail_name, image_path

class ImagesPipelineTestCase(unittest.TestCase):
    def test_image_path(self):
        self.assertEqual(image_path("https://dev.mydeco.com/mydeco.gif"),
                         'dev.mydeco.com/mydeco.gif')
        self.assertEqual(image_path("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.jpg"),
                         'www.maddiebrown.co.uk/catalogue-items/image_54642_12175_95307.jpg')
        self.assertEqual(image_path("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.gif"),
                         'dev.mydeco.com/two/dirs/with spaces+signs.gif')
        self.assertEqual(image_path("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg"),
                         'www.dfsonline.co.uk/4507be485f38b0da8a0be9eb2e1dfab8a19223f2')
        self.assertEqual(image_path("http://www.dorma.co.uk/images/product_details/2532/"),
                         'www.dorma.co.uk/images/product_details/2532.jpg')
        self.assertEqual(image_path("http://www.dorma.co.uk/images/product_details/2532"),
                         'www.dorma.co.uk/images/product_details/2532')

    def test_thumbnail_name(self):
        name = '50'
        self.assertEqual(thumbnail_name("/tmp/foo.jpg", name),  
                         '/tmp/foo_50.jpg')
        self.assertEqual(thumbnail_name("foo.png", name),
                         'foo_50.jpg')
        self.assertEqual(thumbnail_name("/tmp/foo", name),
                         '/tmp/foo_50.jpg')
        self.assertEqual(thumbnail_name("/tmp/some.name/foo", name),
                         '/tmp/some.name/foo_50.jpg')

if __name__ == "__main__":
    unittest.main()
