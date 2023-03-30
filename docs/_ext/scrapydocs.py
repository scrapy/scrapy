import os
import shutil
import string
from importlib import import_module
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.template import render_templatefile, string_camelcase


def sanitize_module_name(module_name: str) -> str:
    """Sanitizes the given module name, by replacing dashes and dots with underscores and prefixing it with a letter if it doesn't start with one"""
    module_name = module_name.replace("-", "_").replace(".", "_")
    if not module_name[0].isalpha():
        module_name = "a" + module_name
    return module_name


def extract_domain(url: str) -> str:
    """Extracts domain name from URL string"""
    o = urlparse(url)
    if not o.scheme and not o.netloc:
        o = urlparse(f"//{url.lstrip('/')}")
    return o.netloc


def verify_url_scheme(url: str) -> str:
    """Checks url for scheme and inserts https if none found."""
    parsed = urlparse(url)
    if not parsed.scheme and not parsed.netloc:
        parsed = parsed._replace(scheme="https")
    return parsed.geturl()


class NewSpider(ScrapyCommand):
    requires_project = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self):
        return "[options] <name> <domain>"

    def short_desc(self):
        return "Generate new spider using pre-defined templates"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_argument(
            "-l",
            "--list",
            dest="list_templates",
            action="store_true",
            help="List available templates",
        )
        parser.add_argument(
            "-e",
            "--edit",
            dest="edit_spider",
            action="store_true",
            help="Edit spider after creating it",
        )
        parser.add_argument(
            "-d",
            "--dump",
            dest="template",
            metavar="TEMPLATE",
            help="Dump template to standard output",
        )
        parser.add_argument(
            "-t",
            "--template",
            dest="custom_template_name",
            default="basic",
            help="Uses a custom template.",
        )
        parser.add_argument(
            "--force",
            dest="overwrite_spider",
            action="store_true",
            help="If the spider already exists, overwrite it with the template",
        )

    def run(self, args, opts):
        if opts.list_templates:
            self._list_templates()
            return
        if opts.template:
            template_file = self._find_template(opts.template)
            if template_file:
                print(template_file.read_text(encoding="utf-8"))
            return
        if len(args) != 2:
            raise UsageError()

        spider_name, domain = args
        domain = verify_url_scheme(domain)
        module_name = sanitize_module_name(spider_name)

        bot_name = self.settings.get("BOT_NAME")
        if bot_name == module_name:
            print("Cannot create a spider with the same name as your project")
            return

        if not opts.overwrite_spider and self._spider_exists(spider_name):
            return

        template_file = self._find_template(opts.custom_template_name)
        if template_file:
            self._create_spider_module(module_name, spider_name, domain, opts.custom_template_name, template_file)
            if opts.edit_spider:
                self.exitcode = os.system(f'scrapy edit "{spider_name}"')

    def _create_spider_module(self, module_name: str, spider_name: str, domain: str, template_name: str, template_file: Path):
        """Generates the spider module, based on the given template"""
        capitalized_module_name = "".join(s.capitalize() for s in module_name.split("_"))
        tvars = {
            "project_name": self.settings.get("BOT_NAME"),
            "ProjectName": string_camelcase(self.settings.get("BOT_NAME")),
            "module": module_name,
            "name": spider_name,
            "url": domain,
            "domain": extract_domain(domain),
            "classname": f"{capitalized_module_name}Spider",
        }
        if "NEWSPIDER_MODULE" in self.settings:
            spiders_module = import_module(self.settings["NEWSPIDER_MODULE"])
            spiders_dir = Path(spiders_module.__file__).parent.resolve()
        else:
            spiders_module = None
            spiders_dir = Path(".")
        spider_file = spiders_dir / (module_name + ".py")
        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print(f"Created spider {spider_name!r} using template {template_name!r}", end=("" if spiders_module else "\n"))
        if spiders_module:
            print(f"in module:\n  {spiders_module.__name__}.{module_name}")

    def _find_template(self, template_name: str) -> Optional[Path]:
        template_file = Path(self.templates_dir, f"{template_name}.tmpl")
        if template_file.exists():
            return template_file
        print(f"Unable to find template: {template_name}\n")
        print('Use "scrapy genspider --list" to see all available templates.')
        return None

    def _list_templates(self):
        print("Available templates:")
        for file in sorted(Path(self.templates_dir).iterdir()):
            if file.suffix == ".tmpl":
                print(f"  {file.stem}")

    def _spider_exists(self, name: str) -> bool:
        if "NEWSPIDER_MODULE" not in self.settings:
            # if run as a standalone command and file with same filename already exists
            path = Path(f"{name}.py")
            if path.exists():
                print(f"{path.resolve()} already exists")
                return True
            return False

        assert "crawler_process" in self.__dict__, "crawler_process must be set before calling run"

        try:
            spider_class = self.crawler_process.spider_loader.load(name)
        except KeyError:
            pass
        else:
            # if spider with same name exists
            print(f"Spider {name!r} already exists in module:")
            print(f"  {spider_class.__module__}")
            return True

        # a file with the same name exists in the target directory
        spiders_module = import_module(self.settings["NEWSPIDER_MODULE"])
        spiders_dir = Path(spiders_module.__file__).parent
        path = spiders_dir / f"{name}.py"
        if path.exists():
            print(f"{path} already exists")
            return True

        return False

    @property
    def templates_dir(self) -> str:
        templates_dir = self.settings.get("TEMPLATES_DIR", Path(scrapy.__path__[0], "templates"))
        return str(Path(templates_dir, "spiders"))