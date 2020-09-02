import os
import shutil
import string

from importlib import import_module
from os.path import join, dirname, abspath, exists, splitext

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.utils.template import render_templatefile, string_camelcase
from scrapy.exceptions import UsageError


def sanitize_module_name(module_name):
    """Sanitize the given module name, by replacing dashes and points
    with underscores and prefixing it with a letter if it doesn't start
    with one
    """
    module_name = module_name.replace('-', '_').replace('.', '_')
    if module_name[0] not in string.ascii_letters:
        module_name = "a" + module_name
    return module_name


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options] <name> <domain>"

    def short_desc(self):
        return "Generate new spider using pre-defined templates"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-l", "--list", dest="list", action="store_true",
                          help="List available templates")
        parser.add_option("-e", "--edit", dest="edit", action="store_true",
                          help="Edit spider after creating it")
        parser.add_option("-d", "--dump", dest="dump", metavar="TEMPLATE",
                          help="Dump template to standard output")
        parser.add_option("-t", "--template", dest="template", default="basic",
                          help="Uses a custom template.")
        parser.add_option("--force", dest="force", action="store_true",
                          help="If the spider already exists, overwrite it with the template")

    def run(self, args, opts):
        if opts.list:
            self._list_templates()
            return
        if opts.dump:
            template_file = self._find_template(opts.dump)
            if template_file:
                with open(template_file, "r") as f:
                    print(f.read())
            return
        if len(args) != 2:
            raise UsageError()

        name, domain = args[0:2]
        module = sanitize_module_name(name)

        if self.settings.get('BOT_NAME') == module:
            print("Cannot create a spider with the same name as your project")
            return

        if not opts.force and self._spider_exists(name):
            return

        template_file = self._find_template(opts.template)
        if template_file:
            self._genspider(module, name, domain, opts.template, template_file)
            if opts.edit:
                self.exitcode = os.system(f'scrapy edit "{name}"')

    def _genspider(self, module, name, domain, template_name, template_file):
        """Generate the spider module, based on the given template"""
        capitalized_module = ''.join(s.capitalize() for s in module.split('_'))
        tvars = {
            'project_name': self.settings.get('BOT_NAME'),
            'ProjectName': string_camelcase(self.settings.get('BOT_NAME')),
            'module': module,
            'name': name,
            'domain': domain,
            'classname': f'{capitalized_module}Spider'
        }
        if self.settings.get('NEWSPIDER_MODULE'):
            spiders_module = import_module(self.settings['NEWSPIDER_MODULE'])
            spiders_dir = abspath(dirname(spiders_module.__file__))
        else:
            spiders_module = None
            spiders_dir = "."
        spider_file = f"{join(spiders_dir, module)}.py"
        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print(f"Created spider {name!r} using template {template_name!r} ",
              end=('' if spiders_module else '\n'))
        if spiders_module:
            print("in module:\n  {spiders_module.__name__}.{module}")

    def _find_template(self, template):
        template_file = join(self.templates_dir, f'{template}.tmpl')
        if exists(template_file):
            return template_file
        print(f"Unable to find template: {template}\n")
        print('Use "scrapy genspider --list" to see all available templates.')

    def _list_templates(self):
        print("Available templates:")
        for filename in sorted(os.listdir(self.templates_dir)):
            if filename.endswith('.tmpl'):
                print(f"  {splitext(filename)[0]}")

    def _spider_exists(self, name):
        if not self.settings.get('NEWSPIDER_MODULE'):
            # if run as a standalone command and file with same filename already exists
            if exists(name + ".py"):
                print(f"{abspath(name + '.py')} already exists")
                return True
            return False

        try:
            spidercls = self.crawler_process.spider_loader.load(name)
        except KeyError:
            pass
        else:
            # if spider with same name exists
            print(f"Spider {name!r} already exists in module:")
            print(f"  {spidercls.__module__}")
            return True

        # a file with the same name exists in the target directory
        spiders_module = import_module(self.settings['NEWSPIDER_MODULE'])
        spiders_dir = dirname(spiders_module.__file__)
        spiders_dir_abs = abspath(spiders_dir)
        if exists(join(spiders_dir_abs, name + ".py")):
            print(f"{join(spiders_dir_abs, (name + '.py'))} already exists")
            return True

        return False

    @property
    def templates_dir(self):
        return join(
            self.settings['TEMPLATES_DIR'] or join(scrapy.__path__[0], 'templates'),
            'spiders'
        )
