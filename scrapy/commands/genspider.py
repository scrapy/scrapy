from __future__ import annotations

import argparse
import os
import shutil
import string
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.template import render_templatefile, string_camelcase


def sanitize_module_name(module_name: str) -> str:
    """Sanitize the given module name by replacing dashes and periods with underscores,
    and prefixing it with a letter if it doesn't start with one.

    Args:
        module_name (str): The module name to sanitize.

    Returns:
        str: The sanitized module name.

    Example:
        >>> sanitize_module_name('1-test.module')
        'a1_test_module'
    """
    module_name = module_name.replace("-", "_").replace(".", "_")
    if module_name[0] not in string.ascii_letters:
        module_name = "a" + module_name
    return module_name


def extract_domain(url: str) -> str:
    """Extract the domain name from a given URL.

    Args:
        url (str): The URL to extract the domain from.

    Returns:
        str: The domain name extracted from the URL.

    Example:
        >>> extract_domain('https://www.example.com/path')
        'www.example.com'
    """
    o = urlparse(url)
    if o.scheme == "" and o.netloc == "":
        o = urlparse("//" + url.lstrip("/"))
    return o.netloc


def verify_url_scheme(url: str) -> str:
    """Ensure the URL has a scheme and insert 'https' if none is found.

    Args:
        url (str): The URL to verify.

    Returns:
        str: The URL with a scheme.

    Example:
        >>> verify_url_scheme('example.com/path')
        'https://example.com/path'
    """
    parsed = urlparse(url)
    if parsed.scheme == "" and parsed.netloc == "":
        parsed = urlparse("//" + url)._replace(scheme="https")
    return parsed.geturl()


class Command(ScrapyCommand):
    """Scrapy command to generate a new spider using pre-defined templates.

    This command helps automate the creation of spider modules by rendering templates 
    and saving them to the appropriate directory. It can also list available templates 
    and edit created spiders.
    """

    requires_project = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        """Return the syntax for using the command.

        Returns:
            str: The syntax string.
        """
        return "[options] <name> <domain>"

    def short_desc(self) -> str:
        """Return a brief description of the command.

        Returns:
            str: A short description of the command.
        """
        return "Generate new spider using pre-defined templates"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        """Add custom command-line options for the command.

        Args:
            parser (argparse.ArgumentParser): The argument parser instance.
        """
        super().add_options(parser)
        parser.add_argument(
            "-l",
            "--list",
            dest="list",
            action="store_true",
            help="List available templates",
        )
        parser.add_argument(
            "-e",
            "--edit",
            dest="edit",
            action="store_true",
            help="Edit spider after creating it",
        )
        parser.add_argument(
            "-d",
            "--dump",
            dest="dump",
            metavar="TEMPLATE",
            help="Dump template to standard output",
        )
        parser.add_argument(
            "-t",
            "--template",
            dest="template",
            default="basic",
            help="Uses a custom template.",
        )
        parser.add_argument(
            "--force",
            dest="force",
            action="store_true",
            help="If the spider already exists, overwrite it with the template",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Execute the command to generate a new spider.

        Args:
            args (list[str]): List containing the name and domain for the spider.
            opts (argparse.Namespace): Parsed command-line options.

        Raises:
            UsageError: If the number of arguments is incorrect.
        """
        if opts.list:
            self._list_templates()
            return
        if opts.dump:
            template_file = self._find_template(opts.dump)
            if template_file:
                print(template_file.read_text(encoding="utf-8"))
            return
        if len(args) != 2:
            raise UsageError("A spider name and domain must be provided.")

        name, url = args[0:2]
        url = verify_url_scheme(url)
        module = sanitize_module_name(name)

        if self.settings.get("BOT_NAME") == module:
            print("Cannot create a spider with the same name as your project")
            return

        if not opts.force and self._spider_exists(name):
            return

        template_file = self._find_template(opts.template)
        if template_file:
            self._genspider(module, name, url, opts.template, template_file)
            if opts.edit:
                self.exitcode = os.system(f'scrapy edit "{name}"')  # nosec

    def _generate_template_variables(
        self,
        module: str,
        name: str,
        url: str,
        template_name: str,
    ) -> dict[str, Any]:
        """Generate template variables for rendering the spider template.

        Args:
            module (str): The module name.
            name (str): The spider name.
            url (str): The target URL.
            template_name (str): The template being used.

        Returns:
            dict[str, Any]: A dictionary of template variables.
        """
        capitalized_module = "".join(s.capitalize() for s in module.split("_"))
        return {
            "project_name": self.settings.get("BOT_NAME"),
            "ProjectName": string_camelcase(self.settings.get("BOT_NAME")),
            "module": module,
            "name": name,
            "url": url,
            "domain": extract_domain(url),
            "classname": f"{capitalized_module}Spider",
        }

    def _genspider(
        self,
        module: str,
        name: str,
        url: str,
        template_name: str,
        template_file: str | os.PathLike,
    ) -> None:
        """Generate the spider file from the specified template.

        Args:
            module (str): The module name.
            name (str): The spider name.
            url (str): The target URL.
            template_name (str): The template being used.
            template_file (str | os.PathLike): The path to the template file.
        """
        tvars = self._generate_template_variables(module, name, url, template_name)
        if self.settings.get("NEWSPIDER_MODULE"):
            spiders_module = import_module(self.settings["NEWSPIDER_MODULE"])
            assert spiders_module.__file__
            spiders_dir = Path(spiders_module.__file__).parent.resolve()
        else:
            spiders_module = None
            spiders_dir = Path(".")
        spider_file = f"{spiders_dir / module}.py"
        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print(
            f"Created spider {name!r} using template {template_name!r} ",
            end=("" if spiders_module else "\n"),
        )
        if spiders_module:
            print(f"in module:\n  {spiders_module.__name__}.{module}")

    def _find_template(self, template: str) -> Path | None:
        """Find the specified template file.

        Args:
            template (str): The template name.

        Returns:
            Path | None: The path to the template file, or None if not found.
        """
        template_file = Path(self.templates_dir, f"{template}.tmpl")
        if template_file.exists():
            return template_file
        print(f"Unable to find template: {template}\n")
        print('Use "scrapy genspider --list" to see all available templates.')
        return None

    def _list_templates(self) -> None:
        """List all available spider templates."""
        print("Available templates:")
        for file in sorted(Path(self.templates_dir).iterdir()):
            if file.suffix == ".tmpl":
                print(f"  {file.stem}")

    def _spider_exists(self, name: str) -> bool:
        """Check if a spider with the specified name already exists.

        Args:
            name (str): The name of the spider.

        Returns:
            bool: True if the spider exists, False otherwise.
        """
        if not self.settings.get("NEWSPIDER_MODULE"):
            # if run as a standalone command and file with same filename already exists
            path = Path(name + ".py")
            if path.exists():
                print(f"{path.resolve()} already exists")
                return True
            return False

        assert (
            self.crawler_process is not None
        ), "crawler_process must be set before calling run"

        try:
            spidercls = self.crawler_process.spider_loader.load(name)
        except KeyError:
            pass
        else:
            print(f"Spider {name!r} already exists in module:")
            print(f"  {spidercls.__module__}")
            return True

        # a file with the same name exists in the target directory
        spiders_module = import_module(self.settings["NEWSPIDER_MODULE"])
        spiders_dir = Path(cast(str, spiders_module.__file__)).parent
        spiders_dir_abs = spiders_dir.resolve()
        path = spiders_dir_abs / (name + ".py")
        if path.exists():
            print(f"{path} already exists")
            return True

        return False

    @property
    def templates_dir(self) -> str:
        """Return the path to the directory containing spider templates.

        Returns:
            str: The path to the templates directory.
        """
        return str(
            Path(
                self.settings["TEMPLATES_DIR"] or Path(scrapy.__path__[0], "templates"),
                "spiders",
            )
        )
