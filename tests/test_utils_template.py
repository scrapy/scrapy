from scrapy.utils.template import render_templatefile


class TestUtilsRenderTemplateFile:
    def test_simple_render(self, tmp_path):
        context = {"project_name": "proj", "name": "spi", "classname": "TheSpider"}
        template = "from ${project_name}.spiders.${name} import ${classname}"
        rendered = "from proj.spiders.spi import TheSpider"

        template_path = tmp_path / "templ.py.tmpl"
        render_path = tmp_path / "templ.py"

        template_path.write_text(template, encoding="utf8")
        assert template_path.is_file()  # Failure of test itself

        render_templatefile(template_path, **context)

        assert not template_path.exists()
        assert render_path.read_text(encoding="utf8") == rendered

        render_path.unlink()
        assert not render_path.exists()  # Failure of test itself
