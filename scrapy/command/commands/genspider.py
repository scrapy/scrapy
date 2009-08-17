import shutil
import string
from os.path import join, dirname, abspath, exists

from scrapy.spider import spiders
from scrapy.command import ScrapyCommand
from scrapy.conf import settings
from scrapy.utils.template import render_templatefile, string_camelcase

def sanitize_module_name(module_name):
    """Sanitize the given module name, by replacing dashes with underscores and
    prefixing it with a letter if it doesn't start with one
    """
    module_name = module_name.replace('-', '_')
    if module_name[0] not in string.letters:
        module_name = "a" + module_name
    return module_name

class Command(ScrapyCommand):

    def syntax(self):
        return "[options] <spider_module_name> <spider_domain_name>"

    def short_desc(self):
        return "Generate new spider based on template passed with --template"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--template", dest="template", default="crawl",
            help="Uses a custom template.")
        parser.add_option("--force", dest="force", action="store_true",
            help="If the spider already exists, overwrite it with the template")

    def run(self, args, opts):
        if len(args) < 2:
            return False

        template_file = join(settings['TEMPLATES_DIR'], 'spider_%s.tmpl' % \
            opts.template)
        if not exists(template_file):
            print "Unable to create spider: template %r not found." % opts.template
            print "Use genspider --list to see all available templates."
            return

        module = sanitize_module_name(args[0])
        domain = args[1]
        spider = spiders.fromdomain(domain)
        if spider and not opts.force:
            print "Spider '%s' already exists in module:" % domain
            print "  %s" % spider.__module__
            return
        self._genspider(module, domain, opts.template, template_file)

    def _genspider(self, module, domain, template_name, template_file):
        """Generate the spider module, based on the given template"""
        tvars = {
            'project_name': settings.get('PROJECT_NAME'),
            'ProjectName': string_camelcase(settings.get('PROJECT_NAME')),
            'module': module,
            'site': domain,
            'classname': '%sSpider' % ''.join([s.capitalize() \
                for s in module.split('_')])
        }

        spiders_module = __import__(settings['NEWSPIDER_MODULE'], {}, {}, [''])
        spiders_dir = abspath(dirname(spiders_module.__file__))
        spider_file = "%s.py" % join(spiders_dir, module)

        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)
        print "Created spider %r using template %r in module:" % (domain, \
            template_name)
        print "  %s.%s" % (spiders_module.__name__, module)
