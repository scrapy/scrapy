from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from scrapy.utils.template import render_templatefile


class TestUtilsRenderTemplateFile:
    def setup_method(self):
        self.tmp_path = mkdtemp()

    def teardown_method(self):
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

        assert not template_path.exists()
        assert render_path.read_text(encoding="utf8") == rendered

        render_path.unlink()
        assert not render_path.exists()  # Failure of test itself
