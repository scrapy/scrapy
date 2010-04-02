import sys
import shutil
import string
from os import listdir
from os.path import join, dirname, abspath, exists

import scrapy
from scrapy.spider import spiders
from scrapy.command import ScrapyCommand
from scrapy.conf import settings
from scrapy.utils.template import render_templatefile, string_camelcase


SPIDER_TEMPLATES_PATH = join(scrapy.__path__[0], 'templates', 'spiders')


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

    def syntax(self):
        return "[options] <name> <domain>"

    def short_desc(self):
        return "Generate new spider based on template passed with -t or --template"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--list", dest="list", action="store_true")
        parser.add_option("--dump", dest="dump", action="store_true")
        parser.add_option("-t", "--template", dest="template", default="crawl",
            help="Uses a custom template.")
        parser.add_option("--force", dest="force", action="store_true",
            help="If the spider already exists, overwrite it with the template")

    def run(self, args, opts):
        if opts.list:
            self._list_templates()
            return

        if opts.dump:
            template_file = self._find_template(opts.template)
            if template_file:
                template = open(template_file, 'r')
                print template.read() 
            return

        if len(args) != 2:
            return False

        name = args[0]
        domain = args[1]

        module = sanitize_module_name(name)

        # if spider already exists and not force option then halt
        try:
            spider = spiders.create(name)
        except KeyError:
            pass
        else:
            if not opts.force:
                print "Spider '%s' already exists in module:" % name
                print "  %s" % spider.__module__
                sys.exit(1)

        template_file = self._find_template(opts.template)
        if template_file:
            self._genspider(module, name, domain, opts.template, template_file)

    def _genspider(self, module, name, domain, template_name, template_file):
        """Generate the spider module, based on the given template"""
        tvars = {
            'project_name': settings.get('BOT_NAME'),
            'ProjectName': string_camelcase(settings.get('BOT_NAME')),
            'module': module,
            'name': name,
            'domain': domain,
            'classname': '%sSpider' % ''.join([s.capitalize() \
                for s in module.split('_')])
        }

        spiders_module = __import__(settings['NEWSPIDER_MODULE'], {}, {}, [''])
        spiders_dir = abspath(dirname(spiders_module.__file__))
        spider_file = "%s.py" % join(spiders_dir, module)

        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print "Created spider %r using template %r in module:" % (name, \
            template_name)
        print "  %s.%s" % (spiders_module.__name__, module)

    def _find_template(self, template):
        template_file = join(settings['TEMPLATES_DIR'], 'spiders', '%s.tmpl' % template)
        if not exists(template_file):
            template_file = join(SPIDER_TEMPLATES_PATH, '%s.tmpl' % template)
            if not exists(template_file):
                print "Unable to find template %r." \
                        % template
                print "Use genspider --list to see all available templates."
                return None
        return template_file

    def _list_templates(self):
        files = set(listdir(SPIDER_TEMPLATES_PATH))
        if exists(settings['TEMPLATES_DIR']):
            files.update(listdir(join(settings['TEMPLATES_DIR'], 'spiders')))

        for filename in sorted(files):
            if filename.endswith('.tmpl'):
                print filename

