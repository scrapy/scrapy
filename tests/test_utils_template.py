import unittest
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from scrapy.utils.template import render_templatefile

__doctests__ = ["scrapy.utils.template"]


class UtilsRenderTemplateFileTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_path = mkdtemp()

    def tearDown(self):
        rmtree(self.tmp_path)

    def test_simple_render(self):
        context = {"project_name": "proj", "name": "spi", "classname": "TheSpider"}
        template = "from ${project_name}.spiders.${name} import ${classname}"
        rendered = "from proj.spiders.spi import TheSpider"

        template_path = Path(self.tmp_path, "templ.py.tmpl")
        render_path = Path(self.tmp_path, "templ.py")

        template_path.write_text(template, encoding="utf8")
        assert template_path.is_file()  # Failure of test itself

        render_templatefile(template_path, **context)

        self.assertFalse(template_path.exists())
        self.assertEqual(render_path.read_text(encoding="utf8"), rendered)

        render_path.unlink()
        assert not render_path.exists()  # Failure of test itself


if "__main__" == __name__:
    unittest.main()
