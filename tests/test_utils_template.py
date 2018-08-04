import os
from shutil import rmtree
from tempfile import mkdtemp
import unittest
from scrapy.utils.template import render_templatefile


__doctests__ = ['scrapy.utils.template']


class UtilsRenderTemplateFileTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp_path = mkdtemp()

    def tearDown(self):
        rmtree(self.tmp_path)

    def test_simple_render(self):

        context = dict(project_name='proj', name='spi', classname='TheSpider')
        template = u'from ${project_name}.spiders.${name} import ${classname}'
        rendered = u'from proj.spiders.spi import TheSpider'

        template_path = os.path.join(self.tmp_path, 'templ.py.tmpl')
        render_path = os.path.join(self.tmp_path, 'templ.py')

        with open(template_path, 'wb') as tmpl_file:
            tmpl_file.write(template.encode('utf8'))
        assert os.path.isfile(template_path)  # Failure of test itself

        render_templatefile(template_path, **context)

        self.assertFalse(os.path.exists(template_path))
        with open(render_path, 'rb') as result:
            self.assertEqual(result.read().decode('utf8'), rendered)

        os.remove(render_path)
        assert not os.path.exists(render_path)  # Failure of test iself

if '__main__' == __name__:
    unittest.main()
