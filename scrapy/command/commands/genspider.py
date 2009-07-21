import shutil
import string
from os.path import join, dirname, abspath, exists

from scrapy.spider import spiders
from scrapy.command import ScrapyCommand
from scrapy.conf import settings
from scrapy.utils.misc import render_templatefile, string_camelcase


class Command(ScrapyCommand):

    def syntax(self):
        return "[options] <spider_name> <spider_domain_name>"

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

        template_file = join(settings['TEMPLATES_DIR'], 'spider_%s.tmpl' % opts.template)
        if not exists(template_file):
            print "Template '%s.tmpl' not found" % opts.template
            return

        name = self.normalize_name(args[0])
        domain = args[1]
        spiders_dict = spiders.asdict()
        if domain in spiders_dict.keys():
            if opts.force:
                print "Spider '%s' already exists. Overwriting it..." % domain
            else:
                print "Spider '%s' already exists" % domain
                return
        self._genspider(name, domain, template_file)

    def normalize_name(self, name):
        # - are replaced by _, for valid python modules
        name = name.replace('-', '_')
        # name must start with a letter, for valid python modules
        if name[0] not in string.letters:
            name = "a" + name
            print "Spider names must start with a letter; converted to %s." % name
        return name
        
    def _genspider(self, name, domain, template_file):
        """Generate the spider module, based on the given template"""
        tvars = {
            'project_name': settings.get('PROJECT_NAME'),
            'ProjectName': string_camelcase(settings.get('PROJECT_NAME')),
            'name': name,
            'site': domain,
            'classname': '%sSpider' % ''.join([s.capitalize() for s in name.split('_')])
        }

        spiders_module = __import__(settings['NEWSPIDER_MODULE'], {}, {}, [''])
        spiders_dir = abspath(dirname(spiders_module.__file__))
        spider_file = '%s/%s.py' % (spiders_dir, name)

        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)

