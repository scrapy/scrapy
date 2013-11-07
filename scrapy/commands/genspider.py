from __future__ import print_function
import os
import shutil
import string

from importlib import import_module
from os.path import join, dirname, abspath, exists, splitext

import scrapy
from scrapy.command import ScrapyCommand
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

    requires_project = True
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
        parser.add_option("-t", "--template", dest="template", default="crawl",
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
                print(open(template_file, 'r').read())
            return
        if len(args) != 2:
            raise UsageError()

        name, domain = args[0:2]
        module = sanitize_module_name(name)

        if self.settings.get('BOT_NAME') == module:
            print("Cannot create a spider with the same name as your project")
            return

        try:
            crawler = self.crawler_process.create_crawler()
            spider = crawler.spiders.create(name)
        except KeyError:
            pass
        else:
            # if spider already exists and not --force then halt
            if not opts.force:
                print("Spider %r already exists in module:" % name)
                print("  %s" % spider.__module__)
                return
        template_file = self._find_template(opts.template)
        if template_file:
            self._genspider(module, name, domain, opts.template, template_file)
            if opts.edit:
                self.exitcode = os.system('scrapy edit "%s"' % name)

    def _genspider(self, module, name, domain, template_name, template_file):
        """Generate the spider module, based on the given template"""
        tvars = {
            'project_name': self.settings.get('BOT_NAME'),
            'ProjectName': string_camelcase(self.settings.get('BOT_NAME')),
            'module': module,
            'name': name,
            'domain': domain,
            'classname': '%sSpider' % ''.join([s.capitalize() \
                for s in module.split('_')])
        }
        spiders_module = import_module(self.settings['NEWSPIDER_MODULE'])
        spiders_dir = abspath(dirname(spiders_module.__file__))
        spider_file = "%s.py" % join(spiders_dir, module)
        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print("Created spider %r using template %r in module:" % (name, \
            template_name))
        print("  %s.%s" % (spiders_module.__name__, module))

    def _find_template(self, template):
        template_file = join(self.templates_dir, '%s.tmpl' % template)
        if exists(template_file):
            return template_file
        print("Unable to find template: %s\n" % template)
        print('Use "scrapy genspider --list" to see all available templates.')

    def _list_templates(self):
        print("Available templates:")
        for filename in sorted(os.listdir(self.templates_dir)):
            if filename.endswith('.tmpl'):
                print("  %s" % splitext(filename)[0])

    @property
    def templates_dir(self):
        _templates_base_dir = self.settings['TEMPLATES_DIR'] or \
            join(scrapy.__path__[0], 'templates')
        return join(_templates_base_dir, 'spiders')
